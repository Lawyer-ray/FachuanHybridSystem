"""
法院短信任务恢复服务

提供任务恢复和监控功能，可以被定时任务调用。
"""
import logging
from datetime import datetime, timedelta
from typing import List, Dict, Any
from django.utils import timezone
from django_q.tasks import async_task

from apps.automation.models import CourtSMS, CourtSMSStatus, ScraperTaskStatus

logger = logging.getLogger("apps.automation")


class TaskRecoveryService:
    """任务恢复服务"""
    
    def __init__(self):
        self.stuck_timeout_minutes = 30  # 任务卡住超时时间（分钟）
        self.max_retry_count = 3  # 最大重试次数
        self.recovery_max_age_hours = 24  # 恢复任务的最大年龄（小时）
    
    def recover_all_tasks(self, dry_run: bool = False) -> Dict[str, Any]:
        """
        恢复所有未完成的任务
        
        Args:
            dry_run: 是否只是预览，不实际执行
            
        Returns:
            Dict: 恢复结果统计
        """
        logger.info(f"开始任务恢复 (dry_run={dry_run})")
        
        result = {
            "recovered_count": 0,
            "reset_count": 0,
            "failed_count": 0,
            "skipped_count": 0,
            "tasks": []
        }
        
        try:
            # 获取需要恢复的任务
            tasks_to_recover = self._get_tasks_to_recover()
            stuck_tasks = self._get_stuck_tasks()
            
            logger.info(f"找到 {len(tasks_to_recover)} 个待恢复任务，{len(stuck_tasks)} 个卡住任务")
            
            if dry_run:
                result["tasks"] = [
                    {
                        "id": task.id,
                        "status": task.status,
                        "action": "recover",
                        "created_at": task.created_at.isoformat(),
                        "updated_at": task.updated_at.isoformat()
                    }
                    for task in tasks_to_recover
                ]
                result["tasks"].extend([
                    {
                        "id": task.id,
                        "status": task.status,
                        "action": "reset",
                        "created_at": task.created_at.isoformat(),
                        "updated_at": task.updated_at.isoformat()
                    }
                    for task in stuck_tasks
                ])
                return result
            
            # 重置卡住的任务
            for task in stuck_tasks:
                try:
                    self._reset_stuck_task(task)
                    result["reset_count"] += 1
                except Exception as e:
                    logger.error(f"重置卡住任务失败: SMS ID={task.id}, 错误: {str(e)}")
                    result["failed_count"] += 1
            
            # 恢复未完成的任务
            for task in tasks_to_recover:
                try:
                    if self._recover_task(task):
                        result["recovered_count"] += 1
                    else:
                        result["skipped_count"] += 1
                except Exception as e:
                    logger.error(f"恢复任务失败: SMS ID={task.id}, 错误: {str(e)}")
                    result["failed_count"] += 1
            
            logger.info(f"任务恢复完成: 恢复={result['recovered_count']}, "
                       f"重置={result['reset_count']}, 失败={result['failed_count']}")
            
        except Exception as e:
            logger.error(f"任务恢复过程失败: {str(e)}")
            result["error"] = str(e)
        
        return result
    
    def get_recovery_status(self) -> Dict[str, Any]:
        """
        获取当前恢复状态统计
        
        Returns:
            Dict: 状态统计信息
        """
        max_age = timezone.now() - timedelta(hours=self.recovery_max_age_hours)
        
        # 统计各状态任务数量
        status_counts = {}
        for status in CourtSMSStatus:
            count = CourtSMS.objects.filter(
                status=status.value,
                created_at__gte=max_age
            ).count()
            status_counts[status.value] = {
                "label": status.label,
                "count": count
            }
        
        # 统计需要恢复的任务
        tasks_to_recover = self._get_tasks_to_recover()
        stuck_tasks = self._get_stuck_tasks()
        
        return {
            "status_counts": status_counts,
            "recovery_needed": len(tasks_to_recover),
            "stuck_tasks": len(stuck_tasks),
            "max_age_hours": self.recovery_max_age_hours,
            "stuck_timeout_minutes": self.stuck_timeout_minutes
        }
    
    def _get_tasks_to_recover(self) -> List[CourtSMS]:
        """获取需要恢复的任务"""
        max_age = timezone.now() - timedelta(hours=self.recovery_max_age_hours)
        
        incomplete_statuses = [
            CourtSMSStatus.PENDING,
            CourtSMSStatus.PARSING,
            CourtSMSStatus.DOWNLOADING,
            CourtSMSStatus.DOWNLOAD_FAILED,
            CourtSMSStatus.MATCHING,
            CourtSMSStatus.RENAMING,
            CourtSMSStatus.NOTIFYING,
        ]
        
        return list(CourtSMS.objects.filter(
            status__in=incomplete_statuses,
            created_at__gte=max_age
        ).order_by('-created_at'))
    
    def _get_stuck_tasks(self) -> List[CourtSMS]:
        """获取卡住的任务"""
        max_age = timezone.now() - timedelta(hours=self.recovery_max_age_hours)
        stuck_cutoff = timezone.now() - timedelta(minutes=self.stuck_timeout_minutes)
        
        stuck_statuses = [
            CourtSMSStatus.PARSING,
            CourtSMSStatus.DOWNLOADING,
            CourtSMSStatus.MATCHING,
            CourtSMSStatus.RENAMING,
            CourtSMSStatus.NOTIFYING,
        ]
        
        return list(CourtSMS.objects.filter(
            status__in=stuck_statuses,
            updated_at__lt=stuck_cutoff,
            created_at__gte=max_age
        ))
    
    def _reset_stuck_task(self, sms: CourtSMS) -> bool:
        """重置卡住的任务"""
        logger.info(f"重置卡住任务: SMS ID={sms.id}, 状态={sms.status}")
        
        sms.status = CourtSMSStatus.PENDING
        sms.error_message = f"系统恢复：任务卡住超过{self.stuck_timeout_minutes}分钟，已重置"
        sms.save()
        
        return True
    
    def _recover_task(self, sms: CourtSMS) -> bool:
        """
        恢复单个任务
        
        Args:
            sms: 短信记录
            
        Returns:
            bool: 是否成功提交恢复任务
        """
        logger.info(f"恢复任务: SMS ID={sms.id}, 状态={sms.status}")
        
        # 根据当前状态决定恢复策略
        if sms.status == CourtSMSStatus.PENDING:
            # 待处理状态，直接提交处理任务
            task_id = async_task(
                'apps.automation.services.sms.court_sms_service.process_sms_async',
                sms.id,
                task_name=f"court_sms_recovery_{sms.id}"
            )
            
        elif sms.status == CourtSMSStatus.DOWNLOAD_FAILED:
            # 下载失败，检查是否可以重试
            if sms.retry_count < self.max_retry_count:
                task_id = async_task(
                    'apps.automation.services.sms.court_sms_service.retry_download_task',
                    sms.id,
                    task_name=f"court_sms_retry_recovery_{sms.id}"
                )
            else:
                # 重试次数用完，标记为失败
                sms.status = CourtSMSStatus.FAILED
                sms.error_message = "恢复时发现重试次数已用完"
                sms.save()
                return False
        
        elif sms.status in [CourtSMSStatus.MATCHING, CourtSMSStatus.RENAMING, CourtSMSStatus.NOTIFYING]:
            # 处理中状态，继续处理
            task_id = async_task(
                'apps.automation.services.sms.court_sms_service.process_sms_async',
                sms.id,
                task_name=f"court_sms_continue_recovery_{sms.id}"
            )
        
        elif sms.status == CourtSMSStatus.DOWNLOADING:
            # 下载中状态，检查关联的 ScraperTask
            if sms.scraper_task:
                if sms.scraper_task.status == ScraperTaskStatus.SUCCESS:
                    # 下载已完成，继续后续处理
                    sms.status = CourtSMSStatus.MATCHING
                    sms.save()
                    
                    task_id = async_task(
                        'apps.automation.services.sms.court_sms_service.process_sms_async',
                        sms.id,
                        task_name=f"court_sms_download_complete_recovery_{sms.id}"
                    )
                elif sms.scraper_task.status == ScraperTaskStatus.FAILED:
                    # 下载失败，触发重试逻辑
                    sms.status = CourtSMSStatus.DOWNLOAD_FAILED
                    sms.save()
                    
                    if sms.retry_count < self.max_retry_count:
                        task_id = async_task(
                            'apps.automation.services.sms.court_sms_service.retry_download_task',
                            sms.id,
                            task_name=f"court_sms_download_retry_recovery_{sms.id}"
                        )
                    else:
                        sms.status = CourtSMSStatus.FAILED
                        sms.error_message = "下载重试次数已用完"
                        sms.save()
                        return False
                else:
                    # 还在下载中，不做处理
                    return False
            else:
                # 没有关联的下载任务，重新创建
                sms.status = CourtSMSStatus.PARSING
                sms.save()
                
                task_id = async_task(
                    'apps.automation.services.sms.court_sms_service.process_sms_async',
                    sms.id,
                    task_name=f"court_sms_reparse_recovery_{sms.id}"
                )
        
        else:
            # 其他状态，重新处理
            task_id = async_task(
                'apps.automation.services.sms.court_sms_service.process_sms_async',
                sms.id,
                task_name=f"court_sms_general_recovery_{sms.id}"
            )
        
        return True
    
    def schedule_periodic_recovery(self, interval_minutes: int = 60):
        """
        安排定期恢复任务
        
        Args:
            interval_minutes: 检查间隔（分钟）
        """
        from django_q.tasks import schedule
        
        # 删除已存在的定期任务
        from django_q.models import Schedule
        Schedule.objects.filter(
            func='apps.automation.services.sms.task_recovery_service.periodic_recovery_task'
        ).delete()
        
        # 创建新的定期任务
        schedule(
            'apps.automation.services.sms.task_recovery_service.periodic_recovery_task',
            schedule_type='I',  # 间隔执行
            minutes=interval_minutes,
            name='court_sms_periodic_recovery'
        )
        
        logger.info(f"已安排定期恢复任务，间隔 {interval_minutes} 分钟")


def periodic_recovery_task():
    """定期恢复任务的入口函数"""
    service = TaskRecoveryService()
    result = service.recover_all_tasks(dry_run=False)
    
    logger.info(f"定期恢复任务完成: {result}")
    return result