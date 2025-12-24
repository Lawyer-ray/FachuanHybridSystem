"""
管理命令：初始化文书送达系统

一键设置文书送达系统的 Django Q 调度和相关配置。

使用方法:
    python manage.py init_document_delivery                    # 使用默认配置初始化
    python manage.py init_document_delivery --interval 10     # 设置10分钟检查间隔
    python manage.py init_document_delivery --reset           # 重置所有配置
"""
import logging
from django.core.management.base import BaseCommand

logger = logging.getLogger("apps.automation")


class Command(BaseCommand):
    help = '初始化文书送达系统的 Django Q 调度'

    def add_arguments(self, parser):
        parser.add_argument(
            '--interval',
            type=int,
            default=5,
            help='Django Q 检查间隔（分钟），默认5分钟',
        )
        parser.add_argument(
            '--reset',
            action='store_true',
            help='重置所有文书送达相关的调度任务',
        )
        parser.add_argument(
            '--dry-run',
            action='store_true',
            help='只显示将要执行的操作，不实际执行',
        )

    def handle(self, *args, **options):
        from apps.automation.services.document_delivery.document_delivery_schedule_service import DocumentDeliveryScheduleService
        
        interval_minutes = options['interval']
        is_reset = options['reset']
        is_dry_run = options['dry_run']
        
        self.stdout.write("=" * 60)
        self.stdout.write(self.style.SUCCESS("文书送达系统初始化"))
        self.stdout.write("=" * 60)
        
        if is_dry_run:
            self.stdout.write(self.style.WARNING("[DRY RUN] 只显示操作，不实际执行\n"))
        
        schedule_service = DocumentDeliveryScheduleService()
        
        try:
            if is_reset:
                self._reset_schedules(schedule_service, is_dry_run)
            else:
                self._setup_schedules(schedule_service, interval_minutes, is_dry_run)
            
            if not is_dry_run:
                self._show_status()
            
        except Exception as e:
            error_msg = f"初始化失败: {str(e)}"
            self.stdout.write(self.style.ERROR(error_msg))
            logger.error(error_msg)
            raise
        
        self.stdout.write("=" * 60)
        if is_reset:
            self.stdout.write(self.style.SUCCESS("重置完成！"))
        else:
            self.stdout.write(self.style.SUCCESS("初始化完成！"))
            if not is_dry_run:
                self.stdout.write("提示: 确保 Django Q 集群正在运行 (python manage.py qcluster)")
        self.stdout.write("=" * 60)
    
    def _setup_schedules(self, schedule_service, interval_minutes, is_dry_run):
        """设置调度任务"""
        schedule_name = "document_delivery_periodic_check"
        
        self.stdout.write(f"设置 Django Q 调度任务:")
        self.stdout.write(f"  - 任务名称: {schedule_name}")
        self.stdout.write(f"  - 检查间隔: {interval_minutes} 分钟")
        self.stdout.write(f"  - 执行命令: execute_document_delivery_schedules")
        
        if not is_dry_run:
            task_id = schedule_service.setup_django_q_schedule(
                interval_minutes=interval_minutes,
                schedule_name=schedule_name
            )
            
            self.stdout.write(self.style.SUCCESS(f"✓ Django Q 调度任务已创建: {task_id}"))
            logger.info(f"文书送达系统初始化完成: task_id={task_id}, interval={interval_minutes}分钟")
    
    def _reset_schedules(self, schedule_service, is_dry_run):
        """重置调度任务"""
        schedule_name = "document_delivery_periodic_check"
        
        self.stdout.write(f"重置文书送达调度任务:")
        self.stdout.write(f"  - 移除调度: {schedule_name}")
        
        if not is_dry_run:
            count = schedule_service.remove_django_q_schedule(schedule_name)
            
            if count > 0:
                self.stdout.write(self.style.SUCCESS(f"✓ 已移除 {count} 个调度任务"))
            else:
                self.stdout.write(self.style.WARNING("没有找到需要移除的调度任务"))
            
            logger.info(f"文书送达调度任务已重置: 移除 {count} 个任务")
    
    def _show_status(self):
        """显示当前状态"""
        from django_q.models import Schedule
        from apps.automation.models import DocumentDeliverySchedule
        
        self.stdout.write("\n当前系统状态:")
        
        # Django Q 调度状态
        django_q_schedules = Schedule.objects.filter(
            name__icontains='document_delivery'
        ).count()
        self.stdout.write(f"  - Django Q 调度任务: {django_q_schedules} 个")
        
        # 用户定时任务状态
        user_schedules = DocumentDeliverySchedule.objects.filter(is_active=True).count()
        total_schedules = DocumentDeliverySchedule.objects.count()
        self.stdout.write(f"  - 用户定时任务: {user_schedules}/{total_schedules} 个启用")
        
        if django_q_schedules == 0:
            self.stdout.write(
                self.style.WARNING("  ⚠ 没有 Django Q 调度任务，系统不会自动执行")
            )
        
        if user_schedules == 0:
            self.stdout.write(
                self.style.WARNING("  ⚠ 没有启用的用户定时任务，不会查询文书")
            )