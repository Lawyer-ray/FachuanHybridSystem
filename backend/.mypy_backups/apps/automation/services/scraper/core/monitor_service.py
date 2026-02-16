"""
任务监控和告警服务
"""
import logging
from datetime import datetime, timedelta
from typing import Dict, Any, List, Optional
from django.utils import timezone
from django.db.models import Count, Q

from apps.core.interfaces import IMonitorService
from ....models import ScraperTask, ScraperTaskStatus

logger = logging.getLogger("apps.automation")


class MonitorService:
    """任务监控服务"""
    
    def __init__(self, task_service=None, alert_service=None):
        """
        初始化监控服务
        
        Args:
            task_service: 任务服务（可选，支持依赖注入）
            alert_service: 告警服务（可选，支持依赖注入）
        """
        self._task_service = task_service
        self._alert_service = alert_service
    
    @property
    def task_service(self):
        """延迟加载任务服务"""
        if self._task_service is None:
            # 通过ServiceLocator获取任务服务
            from apps.core.interfaces import ServiceLocator
            try:
                self._task_service = ServiceLocator.get_task_service()
            except AttributeError:
                # 如果ServiceLocator还没有task_service，直接使用Model
                from ....models import ScraperTask
                self._task_service = ScraperTask
        return self._task_service
    
    @property
    def alert_service(self):
        """延迟加载告警服务"""
        if self._alert_service is None:
            # 使用logger作为默认告警服务
            self._alert_service = logger
        return self._alert_service
    
    def get_task_statistics(self, hours: int = 24) -> Dict[str, Any]:
        """
        获取任务统计信息
        
        Args:
            hours: 统计最近多少小时的数据
            
        Returns:
            统计信息字典
        """
        since = timezone.now() - timedelta(hours=hours)
        
        # 使用注入的任务服务或直接使用Model
        if hasattr(self.task_service, 'objects'):
            tasks = self.task_service.objects.filter(created_at__gte=since)
        else:
            # 如果是通过ServiceLocator获取的服务，调用其方法
            tasks = self.task_service.get_tasks_since(since)
        
        stats = {
            "total": tasks.count(),
            "pending": tasks.filter(status=ScraperTaskStatus.PENDING).count(),
            "running": tasks.filter(status=ScraperTaskStatus.RUNNING).count(),
            "success": tasks.filter(status=ScraperTaskStatus.SUCCESS).count(),
            "failed": tasks.filter(status=ScraperTaskStatus.FAILED).count(),
        }
        
        # 计算成功率
        completed = stats["success"] + stats["failed"]
        stats["success_rate"] = (
            (stats["success"] / completed * 100) if completed > 0 else 0
        )
        
        # 按类型统计
        stats["by_type"] = dict(
            tasks.values("task_type")
            .annotate(count=Count("id"))
            .values_list("task_type", "count")
        )
        
        return stats
    
    def check_stuck_tasks(self, timeout_minutes: int = 30) -> List[ScraperTask]:
        """
        检查卡住的任务（执行时间过长）
        
        Args:
            timeout_minutes: 超时时间（分钟）
            
        Returns:
            卡住的任务列表
        """
        timeout = timezone.now() - timedelta(minutes=timeout_minutes)
        
        # 使用注入的任务服务或直接使用Model
        if hasattr(self.task_service, 'objects'):
            stuck_tasks = self.task_service.objects.filter(
                status=ScraperTaskStatus.RUNNING,
                started_at__lte=timeout
            )
        else:
            # 如果是通过ServiceLocator获取的服务，调用其方法
            stuck_tasks = self.task_service.get_stuck_tasks(timeout)
        
        if stuck_tasks.exists():
            logger.warning(f"发现 {stuck_tasks.count()} 个卡住的任务")
        
        return list(stuck_tasks)
    
    def check_high_failure_rate(self, threshold: float = 0.5, min_tasks: int = 10) -> Dict[str, float]:
        """
        检查高失败率的任务类型
        
        Args:
            threshold: 失败率阈值（0-1）
            min_tasks: 最小任务数（少于此数不统计）
            
        Returns:
            {task_type: failure_rate}
        """
        since = timezone.now() - timedelta(hours=24)
        
        high_failure = {}
        
        # 获取任务类型选项
        if hasattr(self.task_service, '_meta'):
            task_type_choices = self.task_service._meta.get_field("task_type").choices
        else:
            # 如果是服务，获取任务类型
            task_type_choices = getattr(self.task_service, 'get_task_type_choices', lambda: [])()
        
        for task_type, _ in task_type_choices:
            if hasattr(self.task_service, 'objects'):
                tasks = self.task_service.objects.filter(
                    task_type=task_type,
                    created_at__gte=since,
                    status__in=[ScraperTaskStatus.SUCCESS, ScraperTaskStatus.FAILED]
                )
            else:
                # 如果是通过ServiceLocator获取的服务，调用其方法
                tasks = self.task_service.get_tasks_by_type_and_status(
                    task_type, [ScraperTaskStatus.SUCCESS, ScraperTaskStatus.FAILED], since
                )
            
            if hasattr(tasks, 'count'):
                total = tasks.count()
                if total < min_tasks:
                    continue
                failed = tasks.filter(status=ScraperTaskStatus.FAILED).count()
            else:
                # 如果是列表或其他类型
                total = len(tasks) if tasks else 0
                if total < min_tasks:
                    continue
                failed = len([t for t in tasks if getattr(t, 'status', None) == ScraperTaskStatus.FAILED])
            failure_rate = failed / total
            
            if failure_rate >= threshold:
                high_failure[task_type] = failure_rate
                logger.warning(
                    f"任务类型 {task_type} 失败率过高: {failure_rate:.1%} ({failed}/{total})"
                )
        
        return high_failure
    
    def send_alert(self, title: str, message: str, level: str = "warning"):
        """
        发送告警（预留接口）
        
        Args:
            title: 告警标题
            message: 告警内容
            level: 告警级别 (info/warning/error)
        """
        # TODO: 集成钉钉/企业微信/邮件等告警渠道
        self.alert_service.log(
            logging.WARNING if level == "warning" else logging.ERROR,
            f"[告警] {title}: {message}"
        )
        
        # 示例：发送到钉钉
        # if settings.DINGTALK_WEBHOOK:
        #     requests.post(settings.DINGTALK_WEBHOOK, json={
        #         "msgtype": "text",
        #         "text": {"content": f"{title}\n{message}"}
        #     })


class MonitorServiceAdapter(IMonitorService):
    """
    监控服务适配器
    
    实现 IMonitorService Protocol，将 MonitorService 适配为标准接口
    """
    
    def __init__(self, service: Optional[MonitorService] = None):
        self._service = service
    
    @property
    def service(self) -> MonitorService:
        """延迟加载服务实例"""
        if self._service is None:
            self._service = MonitorService()
        return self._service
    
    def get_task_statistics(self, hours: int = 24) -> Dict[str, Any]:
        """获取任务统计信息"""
        return self.service.get_task_statistics(hours)
    
    def check_stuck_tasks(self, timeout_minutes: int = 30) -> List[Any]:
        """检查卡住的任务"""
        return self.service.check_stuck_tasks(timeout_minutes)
    
    def check_high_failure_rate(self, threshold: float = 0.5, min_tasks: int = 10) -> Dict[str, float]:
        """检查高失败率的任务类型"""
        return self.service.check_high_failure_rate(threshold, min_tasks)
    
    def send_alert(self, title: str, message: str, level: str = "warning") -> None:
        """发送告警"""
        self.service.send_alert(title, message, level)
    
    # 内部方法版本，供其他模块调用
    def get_task_statistics_internal(self, hours: int = 24) -> Dict[str, Any]:
        """获取任务统计信息（内部接口，无权限检查）"""
        return self.service.get_task_statistics(hours)
    
    def check_stuck_tasks_internal(self, timeout_minutes: int = 30) -> List[Any]:
        """检查卡住的任务（内部接口，无权限检查）"""
        return self.service.check_stuck_tasks(timeout_minutes)
    
    def check_high_failure_rate_internal(self, threshold: float = 0.5, min_tasks: int = 10) -> Dict[str, float]:
        """检查高失败率的任务类型（内部接口，无权限检查）"""
        return self.service.check_high_failure_rate(threshold, min_tasks)
    
    def send_alert_internal(self, title: str, message: str, level: str = "warning") -> None:
        """发送告警（内部接口，无权限检查）"""
        self.service.send_alert(title, message, level)


# 注意：不再使用全局单例，请通过 ServiceLocator.get_monitor_service() 获取服务实例
