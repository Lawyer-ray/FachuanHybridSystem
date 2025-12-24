"""
管理命令：设置文书送达定时任务的 Django Q 调度

设置 Django Q 定时任务，定期执行文书送达查询。

使用方法:
    python manage.py setup_document_delivery_schedule                    # 设置默认调度（每5分钟）
    python manage.py setup_document_delivery_schedule --interval 10     # 设置10分钟间隔
    python manage.py setup_document_delivery_schedule --remove          # 移除调度
"""
import logging
from django.core.management.base import BaseCommand

logger = logging.getLogger("apps.automation")


class Command(BaseCommand):
    help = '设置文书送达定时任务的 Django Q 调度'

    def add_arguments(self, parser):
        parser.add_argument(
            '--interval',
            type=int,
            default=5,
            help='执行间隔（分钟），默认5分钟',
        )
        parser.add_argument(
            '--remove',
            action='store_true',
            help='移除现有的调度任务',
        )
        parser.add_argument(
            '--name',
            type=str,
            default='document_delivery_periodic_check',
            help='调度任务名称',
        )
        parser.add_argument(
            '--dry-run',
            action='store_true',
            help='只显示将要执行的操作，不实际执行',
        )

    def handle(self, *args, **options):
        from django_q.models import Schedule
        from django_q.tasks import schedule
        
        schedule_name = options['name']
        interval_minutes = options['interval']
        is_dry_run = options['dry_run']
        
        self.stdout.write("=" * 60)
        self.stdout.write(self.style.SUCCESS("文书送达定时任务调度设置"))
        self.stdout.write("=" * 60)
        
        if is_dry_run:
            self.stdout.write(self.style.WARNING("[DRY RUN] 只显示操作，不实际执行\n"))
        
        # 移除现有调度
        existing_schedules = Schedule.objects.filter(name=schedule_name)
        if existing_schedules.exists():
            count = existing_schedules.count()
            existing_schedules.delete()
            self.stdout.write(
                self.style.WARNING(f"已移除 {count} 个现有的调度任务: {schedule_name}")
            )
        
        if options['remove']:
            if not is_dry_run:
                self.stdout.write(self.style.SUCCESS("调度任务已移除"))
                logger.info(f"文书送达调度任务已移除: {schedule_name}")
            else:
                self.stdout.write("将移除调度任务")
            return
        
        # 创建新的调度任务
        if is_dry_run:
            self.stdout.write(
                f"将创建调度任务: {schedule_name}\n"
                f"  - 执行间隔: {interval_minutes} 分钟\n"
                f"  - 执行命令: execute_document_delivery_schedules"
            )
        else:
            try:
                # 使用 Django Q 的 schedule 函数创建定时任务
                task_id = schedule(
                    'django.core.management.call_command',
                    'execute_document_delivery_schedules',
                    schedule_type='I',  # 间隔执行
                    minutes=interval_minutes,
                    name=schedule_name,
                    repeats=-1,  # 无限重复
                )
                
                self.stdout.write(
                    self.style.SUCCESS(
                        f"成功创建调度任务: {schedule_name}\n"
                        f"  - 执行间隔: {interval_minutes} 分钟\n"
                        f"  - 任务ID: {task_id}\n"
                        f"  - 执行命令: execute_document_delivery_schedules"
                    )
                )
                
                logger.info(
                    f"文书送达调度任务已创建: name={schedule_name}, "
                    f"interval={interval_minutes}分钟, task_id={task_id}"
                )
                
                # 显示当前所有相关调度
                self._show_current_schedules()
                
            except Exception as e:
                error_msg = f"创建调度任务失败: {str(e)}"
                self.stdout.write(self.style.ERROR(error_msg))
                logger.error(error_msg)
                raise
        
        self.stdout.write("=" * 60)
        self.stdout.write(
            self.style.SUCCESS("设置完成！Django Q 将定期执行文书送达查询任务")
        )
        self.stdout.write(
            "提示: 确保 Django Q 集群正在运行 (python manage.py qcluster)"
        )
        self.stdout.write("=" * 60)
    
    def _show_current_schedules(self):
        """显示当前所有文书送达相关的调度任务"""
        from django_q.models import Schedule
        
        # 查找所有相关的调度任务
        schedules = Schedule.objects.filter(
            name__icontains='document_delivery'
        ).order_by('name')
        
        if schedules.exists():
            self.stdout.write("\n当前文书送达相关调度任务:")
            for schedule in schedules:
                status = "启用" if schedule.repeats != 0 else "禁用"
                next_run = schedule.next_run.strftime('%Y-%m-%d %H:%M:%S') if schedule.next_run else "未设置"
                
                self.stdout.write(
                    f"  - [{schedule.id}] {schedule.name} - {status}\n"
                    f"    间隔: {schedule.minutes}分钟, 下次运行: {next_run}"
                )
        else:
            self.stdout.write("\n当前没有文书送达相关的调度任务")