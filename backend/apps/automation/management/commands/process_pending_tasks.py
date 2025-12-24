"""
管理命令：处理待处理的爬虫任务

使用方法:
    python manage.py process_pending_tasks           # 处理所有待处理任务
    python manage.py process_pending_tasks --reset   # 同时重置卡住的任务
    python manage.py process_pending_tasks --dry-run # 只显示，不执行
"""
from django.core.management.base import BaseCommand


class Command(BaseCommand):
    help = '处理所有待处理的爬虫任务'

    def add_arguments(self, parser):
        parser.add_argument(
            '--reset',
            action='store_true',
            help='同时重置卡住的 running 任务',
        )
        parser.add_argument(
            '--dry-run',
            action='store_true',
            help='只显示待处理任务，不实际执行',
        )

    def handle(self, *args, **options):
        from apps.automation.models import ScraperTask, ScraperTaskStatus
        from apps.automation.tasks import process_pending_tasks, reset_running_tasks
        
        self.stdout.write("=" * 60)
        self.stdout.write(self.style.SUCCESS("爬虫任务处理"))
        self.stdout.write("=" * 60)
        
        # 显示当前状态
        pending_count = ScraperTask.objects.filter(status=ScraperTaskStatus.PENDING).count()
        running_count = ScraperTask.objects.filter(status=ScraperTaskStatus.RUNNING).count()
        success_count = ScraperTask.objects.filter(status=ScraperTaskStatus.SUCCESS).count()
        failed_count = ScraperTask.objects.filter(status=ScraperTaskStatus.FAILED).count()
        
        self.stdout.write(f"\n当前任务状态:")
        self.stdout.write(f"  - 待处理 (pending): {pending_count}")
        self.stdout.write(f"  - 执行中 (running): {running_count}")
        self.stdout.write(f"  - 成功 (success): {success_count}")
        self.stdout.write(f"  - 失败 (failed): {failed_count}")
        
        if options['dry_run']:
            self.stdout.write(self.style.WARNING("\n[DRY RUN] 只显示，不执行"))
            
            if options['reset'] and running_count > 0:
                self.stdout.write(f"\n将重置 {running_count} 个卡住的任务")
            
            if pending_count > 0:
                self.stdout.write(f"\n将提交 {pending_count} 个待处理任务:")
                pending_tasks = ScraperTask.objects.filter(
                    status=ScraperTaskStatus.PENDING
                ).order_by('priority', '-created_at')[:10]
                
                for task in pending_tasks:
                    self.stdout.write(f"  - [{task.id}] {task.get_task_type_display()} - {task.url[:50]}...")
                
                if pending_count > 10:
                    self.stdout.write(f"  ... 还有 {pending_count - 10} 个任务")
            
            return
        
        # 重置卡住的任务
        if options['reset']:
            self.stdout.write("\n重置卡住的任务...")
            reset_count = reset_running_tasks()
            self.stdout.write(self.style.SUCCESS(f"已重置 {reset_count} 个任务"))
        
        # 处理待处理的任务
        self.stdout.write("\n提交待处理任务到队列...")
        submitted_count = process_pending_tasks()
        
        self.stdout.write("=" * 60)
        self.stdout.write(self.style.SUCCESS(f"完成！已提交 {submitted_count} 个任务到队列"))
        self.stdout.write("=" * 60)
