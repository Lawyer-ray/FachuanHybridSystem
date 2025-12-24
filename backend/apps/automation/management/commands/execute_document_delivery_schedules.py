"""
管理命令：执行文书送达定时任务

定期执行到期的文书送达定时任务，查询并下载新的司法文书。

使用方法:
    python manage.py execute_document_delivery_schedules           # 执行所有到期任务
    python manage.py execute_document_delivery_schedules --dry-run # 只显示，不执行
    python manage.py execute_document_delivery_schedules --schedule-id 123 # 执行指定任务
"""
import logging
from django.core.management.base import BaseCommand
from django.utils import timezone

logger = logging.getLogger("apps.automation")


class Command(BaseCommand):
    help = '执行到期的文书送达定时任务'

    def add_arguments(self, parser):
        parser.add_argument(
            '--dry-run',
            action='store_true',
            help='只显示到期任务，不实际执行',
        )
        parser.add_argument(
            '--schedule-id',
            type=int,
            help='执行指定的定时任务ID',
        )
        parser.add_argument(
            '--force',
            action='store_true',
            help='强制执行指定任务（忽略是否到期）',
        )

    def handle(self, *args, **options):
        from apps.automation.services.document_delivery.document_delivery_schedule_service import DocumentDeliveryScheduleService
        
        # 只在详细模式下显示完整输出
        verbose = options.get('verbosity', 1) > 0
        
        if verbose:
            self.stdout.write("=" * 60)
            self.stdout.write(self.style.SUCCESS("文书送达定时任务执行"))
            self.stdout.write("=" * 60)
        
        schedule_service = DocumentDeliveryScheduleService()
        
        # 获取要执行的任务
        if options['schedule_id']:
            # 执行指定任务
            schedules = self._get_specific_schedule(options['schedule_id'], options['force'])
        else:
            # 获取所有到期任务
            schedules = schedule_service.get_due_schedules()
        
        if not schedules:
            if verbose:
                self.stdout.write(self.style.WARNING("没有找到需要执行的定时任务"))
            return
        
        # 显示任务信息
        if verbose:
            self._show_schedule_info(schedules)
        
        if options['dry_run']:
            if verbose:
                self.stdout.write(self.style.WARNING("\n[DRY RUN] 只显示，不执行"))
            return
        
        # 执行任务
        total_processed = 0
        total_failed = 0
        
        for schedule in schedules:
            try:
                if verbose:
                    self.stdout.write(f"\n执行任务 [{schedule.id}] - 凭证 {schedule.credential_id}...")
                
                result = schedule_service.execute_scheduled_task(schedule.id)
                
                total_processed += result.processed_count
                total_failed += result.failed_count
                
                if verbose:
                    self._show_execution_result(schedule, result)
                
                logger.info(f"定时任务执行完成: schedule_id={schedule.id}, "
                           f"processed={result.processed_count}, failed={result.failed_count}")
                
            except Exception as e:
                error_msg = f"执行定时任务失败: schedule_id={schedule.id}, 错误: {str(e)}"
                logger.error(error_msg)
                total_failed += 1
                
                if verbose:
                    self.stdout.write(
                        self.style.ERROR(f"任务 [{schedule.id}] 执行失败: {str(e)}")
                    )
        
        if verbose:
            self.stdout.write("=" * 60)
            self.stdout.write(self.style.SUCCESS(
                f"完成！共处理 {total_processed} 个文书，失败 {total_failed} 个"
            ))
            self.stdout.write("=" * 60)
        elif total_processed > 0 or total_failed > 0:
            # 静默模式下只在有实际操作时输出简要信息
            logger.info(f"文书送达定时任务执行完成: 处理 {total_processed} 个，失败 {total_failed} 个")
    
    def _get_specific_schedule(self, schedule_id, force=False):
        """获取指定的定时任务"""
        from apps.automation.models import DocumentDeliverySchedule
        from apps.core.exceptions import NotFoundError
        
        try:
            schedule = DocumentDeliverySchedule.objects.get(id=schedule_id)
        except DocumentDeliverySchedule.DoesNotExist:
            raise NotFoundError(f"定时任务不存在: {schedule_id}")
        
        # 检查任务是否启用
        if not schedule.is_active and not force:
            self.stdout.write(
                self.style.WARNING(f"任务 [{schedule_id}] 已禁用，使用 --force 强制执行")
            )
            return []
        
        # 检查任务是否到期
        if not force and schedule.next_run_at and schedule.next_run_at > timezone.now():
            self.stdout.write(
                self.style.WARNING(
                    f"任务 [{schedule_id}] 尚未到期 ({schedule.next_run_at})，使用 --force 强制执行"
                )
            )
            return []
        
        return [schedule]
    
    def _show_schedule_info(self, schedules):
        """显示定时任务信息"""
        self.stdout.write(f"\n找到 {len(schedules)} 个需要执行的定时任务:")
        
        for schedule in schedules:
            # 获取凭证信息
            credential_info = self._get_credential_info(schedule.credential_id)
            
            self.stdout.write(
                f"  - [{schedule.id}] {credential_info} - "
                f"每天{schedule.runs_per_day}次，间隔{schedule.hour_interval}小时 - "
                f"截止{schedule.cutoff_hours}小时内"
            )
            
            if schedule.last_run_at:
                self.stdout.write(
                    f"    上次运行: {schedule.last_run_at.strftime('%Y-%m-%d %H:%M:%S')}"
                )
            
            if schedule.next_run_at:
                self.stdout.write(
                    f"    下次运行: {schedule.next_run_at.strftime('%Y-%m-%d %H:%M:%S')}"
                )
    
    def _get_credential_info(self, credential_id):
        """获取凭证信息"""
        try:
            from apps.core.interfaces import ServiceLocator
            organization_service = ServiceLocator.get_organization_service()
            credential = organization_service.get_credential_internal(credential_id)
            return f"凭证{credential_id}({credential.username})"
        except Exception:
            return f"凭证{credential_id}"
    
    def _show_execution_result(self, schedule, result):
        """显示执行结果"""
        self.stdout.write(
            f"  结果: 发现 {result.total_found} 个文书，"
            f"处理 {result.processed_count} 个，"
            f"跳过 {result.skipped_count} 个，"
            f"失败 {result.failed_count} 个"
        )
        
        if result.case_log_ids:
            self.stdout.write(f"  创建案件日志: {len(result.case_log_ids)} 个")
        
        if result.errors:
            for error in result.errors[:3]:  # 只显示前3个错误
                self.stdout.write(f"  错误: {error}")
            if len(result.errors) > 3:
                self.stdout.write(f"  ... 还有 {len(result.errors) - 3} 个错误")