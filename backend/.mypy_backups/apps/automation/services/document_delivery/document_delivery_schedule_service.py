"""
文书送达定时任务管理服务

负责管理文书送达的定时任务配置和执行
"""
import logging
from datetime import datetime, timedelta
from typing import Optional, List
from django.utils import timezone

from apps.core.exceptions import ValidationException, NotFoundError
from apps.automation.models import DocumentDeliverySchedule
from .document_delivery_service import DocumentDeliveryService
from .data_classes import DocumentQueryResult

logger = logging.getLogger("apps.automation")


class DocumentDeliveryScheduleService:
    """文书送达定时任务服务"""
    
    def __init__(self, document_delivery_service: Optional[DocumentDeliveryService] = None):
        """
        初始化定时任务服务
        
        Args:
            document_delivery_service: 文书送达服务实例（可选，用于依赖注入）
        """
        self._document_delivery_service = document_delivery_service
        logger.debug("DocumentDeliveryScheduleService 初始化完成")
    
    @property
    def document_delivery_service(self) -> DocumentDeliveryService:
        """延迟加载文书送达服务"""
        if self._document_delivery_service is None:
            self._document_delivery_service = DocumentDeliveryService()
        return self._document_delivery_service
    
    def create_schedule(
        self,
        credential_id: int,
        runs_per_day: int = 1,
        hour_interval: int = 24,
        cutoff_hours: int = 24,
        is_active: bool = True
    ) -> DocumentDeliverySchedule:
        """
        创建定时任务
        
        Args:
            credential_id: 账号凭证ID
            runs_per_day: 每天运行次数
            hour_interval: 运行间隔（小时）
            cutoff_hours: 截止时间（小时）
            is_active: 是否启用
            
        Returns:
            DocumentDeliverySchedule: 创建的定时任务
            
        Raises:
            ValidationException: 参数验证失败
        """
        logger.info(f"创建文书送达定时任务: credential_id={credential_id}, runs_per_day={runs_per_day}")
        
        # 验证参数
        self._validate_schedule_config(runs_per_day, hour_interval, cutoff_hours)
        
        # 验证凭证是否存在
        from apps.core.interfaces import ServiceLocator
        organization_service = ServiceLocator.get_organization_service()
        credential = organization_service.get_credential_internal(credential_id)
        
        # 检查是否已存在该凭证的定时任务
        existing_schedule = DocumentDeliverySchedule.objects.filter(
            credential_id=credential_id
        ).first()
        
        if existing_schedule:
            raise ValidationException(f"凭证 {credential_id} 已存在定时任务")
        
        # 计算初始的下次运行时间
        next_run_at = self._calculate_next_run_time(runs_per_day, hour_interval)
        
        # 创建定时任务
        schedule = DocumentDeliverySchedule.objects.create(
            credential_id=credential_id,
            runs_per_day=runs_per_day,
            hour_interval=hour_interval,
            cutoff_hours=cutoff_hours,
            is_active=is_active,
            next_run_at=next_run_at
        )
        
        logger.info(f"定时任务创建成功: id={schedule.id}, next_run_at={next_run_at}")
        return schedule
    
    def _validate_schedule_config(self, runs_per_day: int, hour_interval: int, cutoff_hours: int) -> None:
        """验证定时任务配置参数"""
        if runs_per_day <= 0:
            raise ValidationException("每天运行次数必须大于0")
        
        if hour_interval <= 0 or hour_interval > 24:
            raise ValidationException("运行间隔必须在1-24小时之间")
        
        if cutoff_hours <= 0:
            raise ValidationException("截止时间必须大于0小时")
        
        # 检查运行频率是否合理
        if runs_per_day > 1 and hour_interval * runs_per_day > 24:
            raise ValidationException("运行频率配置不合理：每天运行次数 × 间隔时间不能超过24小时")
    
    def _calculate_next_run_time(self, runs_per_day: int, hour_interval: int) -> datetime:
        """
        计算下次运行时间
        
        Args:
            runs_per_day: 每天运行次数
            hour_interval: 运行间隔（小时）
            
        Returns:
            datetime: 下次运行时间
        """
        now = timezone.now()
        
        if runs_per_day == 1:
            # 每天运行一次，设置为明天的同一时间
            next_run = now + timedelta(hours=hour_interval)
        else:
            # 每天运行多次，按间隔时间计算
            next_run = now + timedelta(hours=hour_interval)
        
        return next_run
    
    def update_schedule(
        self,
        schedule_id: int,
        **kwargs
    ) -> DocumentDeliverySchedule:
        """
        更新定时任务
        
        Args:
            schedule_id: 定时任务ID
            **kwargs: 要更新的字段
            
        Returns:
            DocumentDeliverySchedule: 更新后的定时任务
            
        Raises:
            NotFoundError: 定时任务不存在
            ValidationException: 参数验证失败
        """
        logger.info(f"更新文书送达定时任务: schedule_id={schedule_id}")
        
        # 获取定时任务
        try:
            schedule = DocumentDeliverySchedule.objects.get(id=schedule_id)
        except DocumentDeliverySchedule.DoesNotExist:
            raise NotFoundError(f"定时任务不存在: {schedule_id}")
        
        # 验证更新参数
        runs_per_day = kwargs.get('runs_per_day', schedule.runs_per_day)
        hour_interval = kwargs.get('hour_interval', schedule.hour_interval)
        cutoff_hours = kwargs.get('cutoff_hours', schedule.cutoff_hours)
        
        self._validate_schedule_config(runs_per_day, hour_interval, cutoff_hours)
        
        # 检查是否需要重新计算下次运行时间
        need_recalculate = (
            'runs_per_day' in kwargs or 
            'hour_interval' in kwargs or
            'is_active' in kwargs
        )
        
        # 更新字段
        for field, value in kwargs.items():
            if hasattr(schedule, field):
                setattr(schedule, field, value)
        
        # 重新计算下次运行时间（如果需要）
        if need_recalculate and schedule.is_active:
            schedule.next_run_at = self._calculate_next_run_time(
                schedule.runs_per_day, 
                schedule.hour_interval
            )
        elif not schedule.is_active:
            # 如果禁用了任务，清空下次运行时间
            schedule.next_run_at = None
        
        schedule.save()
        
        logger.info(f"定时任务更新成功: id={schedule.id}, next_run_at={schedule.next_run_at}")
        return schedule
    
    def get_due_schedules(self) -> List[DocumentDeliverySchedule]:
        """
        获取到期的定时任务
        
        Returns:
            List[DocumentDeliverySchedule]: 到期的定时任务列表
        """
        now = timezone.now()
        
        due_schedules = DocumentDeliverySchedule.objects.filter(
            is_active=True,
            next_run_at__lte=now
        ).order_by('next_run_at')
        
        logger.info(f"找到 {due_schedules.count()} 个到期的定时任务")
        return list(due_schedules)
    
    def execute_scheduled_task(self, schedule_id: int) -> DocumentQueryResult:
        """
        执行定时任务
        
        Args:
            schedule_id: 定时任务ID
            
        Returns:
            DocumentQueryResult: 查询结果
            
        Raises:
            NotFoundError: 定时任务不存在
        """
        logger.info(f"执行定时任务: schedule_id={schedule_id}")
        
        # 获取定时任务
        try:
            schedule = DocumentDeliverySchedule.objects.get(id=schedule_id)
        except DocumentDeliverySchedule.DoesNotExist:
            raise NotFoundError(f"定时任务不存在: {schedule_id}")
        
        if not schedule.is_active:
            logger.warning(f"定时任务已禁用: {schedule_id}")
            return DocumentQueryResult(
                total_found=0,
                processed_count=0,
                skipped_count=0,
                failed_count=0,
                case_log_ids=[],
                errors=["定时任务已禁用"]
            )
        
        # 在新线程中执行，避免异步上下文污染
        import threading
        import queue
        
        result_queue = queue.Queue()
        exception_queue = queue.Queue()
        
        def run_in_thread():
            """在独立线程中执行任务"""
            try:
                # 计算截止时间
                cutoff_time = timezone.now() - timedelta(hours=schedule.cutoff_hours)
                
                # 执行文书查询
                result = self.document_delivery_service.query_and_download(
                    credential_id=schedule.credential_id,
                    cutoff_time=cutoff_time,
                    tab="reviewed"  # 测试：查询已查阅标签页
                )
                
                result_queue.put(result)
                
            except Exception as e:
                exception_queue.put(e)
        
        # 启动线程执行任务
        thread = threading.Thread(target=run_in_thread)
        thread.start()
        thread.join(timeout=300)  # 5分钟超时
        
        # 获取结果
        if not result_queue.empty():
            result = result_queue.get()
            
            # 更新任务执行时间（在主线程中，避免异步上下文问题）
            try:
                now = timezone.now()
                schedule.last_run_at = now
                schedule.next_run_at = self._calculate_next_run_time(
                    schedule.runs_per_day,
                    schedule.hour_interval
                )
                schedule.save()
                
                logger.info(f"定时任务执行完成: schedule_id={schedule_id}, "
                           f"processed={result.processed_count}, next_run_at={schedule.next_run_at}")
                
            except Exception as save_error:
                logger.error(f"更新任务执行时间失败: {str(save_error)}")
            
            return result
            
        elif not exception_queue.empty():
            e = exception_queue.get()
            error_msg = f"执行定时任务失败: {str(e)}"
            logger.error(error_msg)
            
            # 仍然更新下次运行时间，避免任务卡住
            try:
                schedule.last_run_at = timezone.now()
                schedule.next_run_at = self._calculate_next_run_time(
                    schedule.runs_per_day,
                    schedule.hour_interval
                )
                schedule.save()
            except Exception as save_error:
                logger.error(f"更新任务执行时间失败: {str(save_error)}")
            
            return DocumentQueryResult(
                total_found=0,
                processed_count=0,
                skipped_count=0,
                failed_count=1,
                case_log_ids=[],
                errors=[error_msg]
            )
        
        else:
            # 线程超时
            error_msg = "执行定时任务超时"
            logger.error(error_msg)
            
            try:
                schedule.last_run_at = timezone.now()
                schedule.next_run_at = self._calculate_next_run_time(
                    schedule.runs_per_day,
                    schedule.hour_interval
                )
                schedule.save()
            except Exception as save_error:
                logger.error(f"更新任务执行时间失败: {str(save_error)}")
            
            return DocumentQueryResult(
                total_found=0,
                processed_count=0,
                skipped_count=0,
                failed_count=1,
                case_log_ids=[],
                errors=[error_msg]
            )
    
    def setup_django_q_schedule(self, interval_minutes: int = 5, schedule_name: str = "document_delivery_periodic_check") -> str:
        """
        设置 Django Q 定时调度
        
        Args:
            interval_minutes: 执行间隔（分钟）
            schedule_name: 调度任务名称
            
        Returns:
            str: 创建的任务ID
        """
        from django_q.models import Schedule
        from django_q.tasks import schedule
        
        logger.info(f"设置文书送达 Django Q 调度: interval={interval_minutes}分钟, name={schedule_name}")
        
        # 移除现有调度
        existing_schedules = Schedule.objects.filter(name=schedule_name)
        if existing_schedules.exists():
            count = existing_schedules.count()
            existing_schedules.delete()
            logger.info(f"已移除 {count} 个现有的调度任务: {schedule_name}")
        
        # 创建新的调度任务
        task_id = schedule(
            'django.core.management.call_command',
            'execute_document_delivery_schedules',
            schedule_type='I',  # 间隔执行
            minutes=interval_minutes,
            name=schedule_name,
            repeats=-1,  # 无限重复
        )
        
        logger.info(f"Django Q 调度任务已创建: name={schedule_name}, interval={interval_minutes}分钟, task_id={task_id}")
        return task_id
    
    def remove_django_q_schedule(self, schedule_name: str = "document_delivery_periodic_check") -> int:
        """
        移除 Django Q 定时调度
        
        Args:
            schedule_name: 调度任务名称
            
        Returns:
            int: 移除的任务数量
        """
        from django_q.models import Schedule
        
        logger.info(f"移除文书送达 Django Q 调度: name={schedule_name}")
        
        # 移除调度任务
        schedules = Schedule.objects.filter(name=schedule_name)
        count = schedules.count()
        schedules.delete()
        
        logger.info(f"已移除 {count} 个调度任务: {schedule_name}")
        return count
    
    def list_schedules(
        self,
        credential_id: Optional[int] = None,
        is_active: Optional[bool] = None
    ) -> List[DocumentDeliverySchedule]:
        """
        查询定时任务列表
        
        Args:
            credential_id: 账号凭证ID（可选）
            is_active: 是否启用（可选）
            
        Returns:
            List[DocumentDeliverySchedule]: 定时任务列表
        """
        logger.debug(f"查询定时任务列表: credential_id={credential_id}, is_active={is_active}")
        
        queryset = DocumentDeliverySchedule.objects.all()
        
        if credential_id is not None:
            queryset = queryset.filter(credential_id=credential_id)
        
        if is_active is not None:
            queryset = queryset.filter(is_active=is_active)
        
        queryset = queryset.order_by('-created_at')
        
        schedules = list(queryset)
        logger.debug(f"找到 {len(schedules)} 个定时任务")
        return schedules
    
    def get_schedule(self, schedule_id: int) -> DocumentDeliverySchedule:
        """
        获取单个定时任务
        
        Args:
            schedule_id: 定时任务ID
            
        Returns:
            DocumentDeliverySchedule: 定时任务实例
            
        Raises:
            NotFoundError: 定时任务不存在
        """
        logger.debug(f"获取定时任务: schedule_id={schedule_id}")
        
        try:
            schedule = DocumentDeliverySchedule.objects.get(id=schedule_id)
            logger.debug(f"找到定时任务: {schedule_id}")
            return schedule
        except DocumentDeliverySchedule.DoesNotExist:
            logger.warning(f"定时任务不存在: {schedule_id}")
            raise NotFoundError(f"定时任务 {schedule_id} 不存在")
    
    def delete_schedule(self, schedule_id: int) -> None:
        """
        删除定时任务
        
        Args:
            schedule_id: 定时任务ID
            
        Raises:
            NotFoundError: 定时任务不存在
        """
        logger.info(f"删除定时任务: schedule_id={schedule_id}")
        
        try:
            schedule = DocumentDeliverySchedule.objects.get(id=schedule_id)
            schedule.delete()
            logger.info(f"定时任务删除成功: {schedule_id}")
        except DocumentDeliverySchedule.DoesNotExist:
            logger.warning(f"定时任务不存在: {schedule_id}")
            raise NotFoundError(f"定时任务 {schedule_id} 不存在")