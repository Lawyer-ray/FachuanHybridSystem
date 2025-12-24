"""
自动化模块信号处理

处理模型保存、删除等事件，自动触发相关操作。
"""
import logging
from django.db.models.signals import post_save
from django.dispatch import receiver
from django_q.tasks import async_task

from .models import PreservationQuote, QuoteStatus, ScraperTask, ScraperTaskStatus, CourtSMS, CourtSMSStatus

logger = logging.getLogger("apps.automation")


@receiver(post_save, sender=PreservationQuote)
def auto_submit_preservation_quote(sender, instance, created, **kwargs):
    """
    自动提交询价任务到 Django Q 队列
    
    当创建新的询价任务时，自动提交到 Django Q 异步队列执行。
    
    Args:
        sender: 模型类
        instance: 保存的实例
        created: 是否是新创建的
        **kwargs: 其他参数
    """
    # 只处理新创建的任务
    if not created:
        return
    
    # 只处理状态为 PENDING 的任务
    if instance.status != QuoteStatus.PENDING:
        return
    
    try:
        # 提交到 Django Q 异步任务队列
        task_id = async_task(
            'apps.automation.tasks.execute_preservation_quote_task',
            instance.id,
            task_name=f'询价任务 #{instance.id}',
            timeout=600,  # 10分钟超时
        )
        
        logger.info(
            f"✅ 询价任务 #{instance.id} 已自动提交到队列，Task ID: {task_id}",
            extra={
                "action": "auto_submit_quote",
                "quote_id": instance.id,
                "task_id": task_id,
            }
        )
        
    except Exception as e:
        logger.error(
            f"❌ 自动提交询价任务 #{instance.id} 失败: {e}",
            extra={
                "action": "auto_submit_quote_failed",
                "quote_id": instance.id,
                "error": str(e),
            },
            exc_info=True
        )


@receiver(post_save, sender=ScraperTask)
def handle_scraper_task_status_change(sender, instance, created, **kwargs):
    """
    处理 ScraperTask 状态变更，触发法院短信后续处理流程
    
    当 ScraperTask 状态变为 SUCCESS 或 FAILED 时，检查是否有关联的 CourtSMS 记录，
    如果有则触发后续处理流程。
    
    Args:
        sender: 模型类
        instance: ScraperTask 实例
        created: 是否是新创建的
        **kwargs: 其他参数
    """
    # 只处理状态更新，不处理新创建
    if created:
        return
    
    # 只处理已完成的任务（成功或失败）
    if instance.status not in [ScraperTaskStatus.SUCCESS, ScraperTaskStatus.FAILED]:
        return
    
    try:
        # 查找关联的 CourtSMS 记录
        court_sms_records = CourtSMS.objects.filter(scraper_task=instance)
        
        for sms in court_sms_records:
            # 处理正在下载状态或等待下载完成的匹配状态的短信
            if sms.status not in [CourtSMSStatus.DOWNLOADING, CourtSMSStatus.MATCHING]:
                continue
            
            if instance.status == ScraperTaskStatus.SUCCESS:
                # 下载成功，触发后续处理
                if sms.status == CourtSMSStatus.DOWNLOADING:
                    # 从下载状态进入匹配阶段
                    sms.status = CourtSMSStatus.MATCHING
                    sms.save()
                    
                    logger.info(
                        f"✅ 下载任务完成，进入匹配阶段: SMS ID={sms.id}, Task ID={instance.id}",
                        extra={
                            "action": "download_success_to_matching",
                            "sms_id": sms.id,
                            "task_id": instance.id,
                        }
                    )
                elif sms.status == CourtSMSStatus.MATCHING:
                    # 匹配阶段等待下载完成，现在可以继续匹配
                    logger.info(
                        f"✅ 下载任务完成，继续匹配流程: SMS ID={sms.id}, Task ID={instance.id}",
                        extra={
                            "action": "download_success_continue_matching",
                            "sms_id": sms.id,
                            "task_id": instance.id,
                        }
                    )
                
                # 提交后续处理任务
                task_id = async_task(
                    'apps.automation.services.sms.court_sms_service.process_sms_async',
                    sms.id,
                    task_name=f'court_sms_continue_{sms.id}'
                )
                
                logger.info(f"提交后续处理任务: SMS ID={sms.id}, Queue Task ID={task_id}")
                
            elif instance.status == ScraperTaskStatus.FAILED:
                # 下载失败，根据当前状态决定处理方式
                if sms.status == CourtSMSStatus.DOWNLOADING:
                    # 从下载状态失败
                    sms.status = CourtSMSStatus.DOWNLOAD_FAILED
                elif sms.status == CourtSMSStatus.MATCHING:
                    # 匹配阶段等待下载失败，继续匹配流程（不依赖文书）
                    logger.info(f"下载失败但继续匹配流程: SMS ID={sms.id}")
                    # 提交后续处理任务，让匹配流程继续
                    task_id = async_task(
                        'apps.automation.services.sms.court_sms_service.process_sms_async',
                        sms.id,
                        task_name=f'court_sms_continue_after_download_failed_{sms.id}'
                    )
                    logger.info(f"下载失败后继续处理任务: SMS ID={sms.id}, Queue Task ID={task_id}")
                    continue  # 跳过后续的重试逻辑
                
                sms.error_message = instance.error_message or "下载任务失败"
                sms.save()
                
                logger.warning(
                    f"⚠️ 下载任务失败: SMS ID={sms.id}, Task ID={instance.id}, 错误: {instance.error_message}",
                    extra={
                        "action": "download_failed",
                        "sms_id": sms.id,
                        "task_id": instance.id,
                        "error": instance.error_message,
                    }
                )
                
                # 检查是否可以重试
                if sms.retry_count < 3:  # 最多重试3次
                    logger.info(f"准备重试下载: SMS ID={sms.id}, 当前重试次数={sms.retry_count}")
                    
                    # 使用 Schedule 模型实现延迟重试（60秒后）
                    from django_q.models import Schedule
                    from django.utils import timezone
                    from datetime import timedelta
                    
                    next_run = timezone.now() + timedelta(seconds=60)
                    
                    Schedule.objects.create(
                        func='apps.automation.services.sms.court_sms_service.retry_download_task',
                        args=str(sms.id),
                        name=f'court_sms_retry_download_{sms.id}',
                        schedule_type=Schedule.ONCE,
                        next_run=next_run
                    )
                    
                    logger.info(f"提交重试下载任务: SMS ID={sms.id}, 计划执行时间={next_run}")
                else:
                    # 重试次数用完，标记为失败
                    sms.status = CourtSMSStatus.FAILED
                    sms.error_message = f"下载失败，已重试{sms.retry_count}次"
                    sms.save()
                    
                    logger.error(f"下载重试次数用完，标记为失败: SMS ID={sms.id}")
        
    except Exception as e:
        logger.error(
            f"❌ 处理下载完成信号失败: Task ID={instance.id}, 错误: {e}",
            extra={
                "action": "download_signal_failed",
                "task_id": instance.id,
                "error": str(e),
            },
            exc_info=True
        )
