"""
管理命令：恢复法院短信处理任务

系统启动时或手动执行，检查未完成的法院短信处理任务并自动恢复处理。

使用方法:
    python manage.py recover_court_sms_tasks           # 恢复所有未完成任务
    python manage.py recover_court_sms_tasks --dry-run # 只显示，不执行
    python manage.py recover_court_sms_tasks --reset   # 重置卡住的任务
"""

import logging
from datetime import timedelta
from typing import Any

from django.core.management.base import BaseCommand
from django.utils import timezone

logger = logging.getLogger("apps.automation")


class Command(BaseCommand):
    help = "恢复未完成的法院短信处理任务"

    def add_arguments(self, parser: Any) -> None:
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="只显示待恢复任务，不实际执行",
        )
        parser.add_argument(
            "--reset",
            action="store_true",
            help="重置卡住的处理中任务（超过30分钟未更新）",
        )
        parser.add_argument(
            "--max-age-hours",
            type=int,
            default=24,
            help="只恢复指定小时内的任务（默认24小时）",
        )

    def handle(self, *args: Any, **options: Any) -> None:

        # 只在详细模式下显示完整输出
        verbose = options.get("verbosity", 1) > 0

        if verbose:
            self.stdout.write("=" * 60)
            self.stdout.write(self.style.SUCCESS("法院短信任务恢复"))
            self.stdout.write("=" * 60)

        # 计算时间范围
        max_age = timezone.now() - timedelta(hours=options["max_age_hours"])

        # 显示当前状态
        if verbose:
            self._show_current_status(max_age)

        if options["dry_run"]:
            if verbose:
                self.stdout.write(self.style.WARNING("\n[DRY RUN] 只显示，不执行"))
                self._show_recovery_plan(max_age, options["reset"])
            return

        # 执行恢复
        recovered_count = 0
        reset_count = 0

        # 重置卡住的任务
        if options["reset"]:
            reset_count = self._reset_stuck_tasks(max_age, verbose)
            if verbose and reset_count > 0:
                self.stdout.write(self.style.SUCCESS(f"已重置 {reset_count} 个卡住的任务"))

        # 恢复未完成的任务
        recovered_count = self._recover_incomplete_tasks(max_age, verbose)

        if verbose:
            self.stdout.write("=" * 60)
            self.stdout.write(
                self.style.SUCCESS(f"完成！已恢复 {recovered_count} 个任务，重置 {reset_count} 个卡住任务")
            )
            self.stdout.write("=" * 60)
        elif recovered_count > 0 or reset_count > 0:
            # 静默模式下只在有实际操作时输出简要信息
            logger.info(f"法院短信任务恢复完成: 恢复 {recovered_count} 个，重置 {reset_count} 个")

    def _show_current_status(self, max_age: Any) -> None:
        """显示当前任务状态"""
        from apps.automation.models import CourtSMS, CourtSMSStatus

        # 统计各状态任务数量
        status_counts = {}
        for status in CourtSMSStatus:
            count = CourtSMS.objects.filter(status=status.value, created_at__gte=max_age).count()
            status_counts[status.label] = count

        self.stdout.write(f"\n当前任务状态（最近{max_age.strftime('%Y-%m-%d %H:%M')}以来）:")
        for status_label, count in status_counts.items():
            if count > 0:
                self.stdout.write(f"  - {status_label}: {count}")

    def _show_recovery_plan(self, max_age: Any, reset_stuck: bool) -> None:
        """显示恢复计划"""
        from apps.automation.models import CourtSMS, CourtSMSStatus

        # 查找需要恢复的任务
        incomplete_statuses = [
            CourtSMSStatus.PENDING,
            CourtSMSStatus.PARSING,
            CourtSMSStatus.DOWNLOADING,
            CourtSMSStatus.DOWNLOAD_FAILED,
            CourtSMSStatus.MATCHING,
            CourtSMSStatus.RENAMING,
            CourtSMSStatus.NOTIFYING,
        ]

        incomplete_tasks = CourtSMS.objects.filter(status__in=incomplete_statuses, created_at__gte=max_age).order_by(
            "-created_at"
        )

        if incomplete_tasks.exists():
            self.stdout.write(f"\n将恢复 {incomplete_tasks.count()} 个未完成任务:")
            for sms in incomplete_tasks[:10]:  # 只显示前10个
                self.stdout.write(
                    f"  - [{sms.id}] {sms.get_status_display()} - "
                    f"{sms.created_at.strftime('%m-%d %H:%M')} - "
                    f"{sms.content[:30]}..."
                )

            if incomplete_tasks.count() > 10:
                self.stdout.write(f"  ... 还有 {incomplete_tasks.count() - 10} 个任务")

        # 查找卡住的任务
        if reset_stuck:
            stuck_cutoff = timezone.now() - timedelta(minutes=30)
            stuck_statuses = [
                CourtSMSStatus.PARSING,
                CourtSMSStatus.DOWNLOADING,
                CourtSMSStatus.MATCHING,
                CourtSMSStatus.RENAMING,
                CourtSMSStatus.NOTIFYING,
            ]

            stuck_tasks = CourtSMS.objects.filter(
                status__in=stuck_statuses, updated_at__lt=stuck_cutoff, created_at__gte=max_age
            )

            if stuck_tasks.exists():
                self.stdout.write(f"\n将重置 {stuck_tasks.count()} 个卡住的任务:")
                for sms in stuck_tasks[:5]:
                    self.stdout.write(
                        f"  - [{sms.id}] {sms.get_status_display()} - "
                        f"卡住时间: {sms.updated_at.strftime('%m-%d %H:%M')}"
                    )

    def _reset_stuck_tasks(self, max_age: Any, verbose: bool = True) -> int:
        """重置卡住的任务"""
        from apps.automation.models import CourtSMS, CourtSMSStatus

        # 定义卡住的条件：处理中状态且30分钟未更新
        stuck_cutoff = timezone.now() - timedelta(minutes=30)
        stuck_statuses = [
            CourtSMSStatus.PARSING,
            CourtSMSStatus.DOWNLOADING,
            CourtSMSStatus.MATCHING,
            CourtSMSStatus.RENAMING,
            CourtSMSStatus.NOTIFYING,
        ]

        stuck_tasks = CourtSMS.objects.filter(
            status__in=stuck_statuses, updated_at__lt=stuck_cutoff, created_at__gte=max_age
        )

        reset_count = 0
        for sms in stuck_tasks:
            try:
                # 重置为待处理状态
                sms.status = CourtSMSStatus.PENDING
                sms.error_message = "系统恢复：任务卡住超过30分钟，已重置"
                sms.save()

                reset_count += 1
                logger.info(f"重置卡住任务: SMS ID={sms.id}, 原状态={sms.status}")

            except Exception as e:
                logger.error(f"重置任务失败: SMS ID={sms.id}, 错误: {e!s}")
                if verbose:
                    self.stdout.write(self.style.ERROR(f"重置任务 {sms.id} 失败: {e!s}"))

        return reset_count

    def _recover_single_downloading(self, sms: Any, async_task: Any) -> bool:
        """处理 DOWNLOADING 状态的恢复，返回是否继续"""
        from apps.automation.models import CourtSMSStatus, ScraperTaskStatus

        if not sms.scraper_task:
            sms.status = CourtSMSStatus.PARSING
            sms.save()
            async_task(
                "apps.automation.services.sms.court_sms_service.process_sms_async",
                sms.id,
                task_name=f"court_sms_reparse_recovery_{sms.id}",
            )
            return True

        scraper_status = sms.scraper_task.status
        if scraper_status == ScraperTaskStatus.SUCCESS:
            sms.status = CourtSMSStatus.MATCHING
            sms.save()
            async_task(
                "apps.automation.services.sms.court_sms_service.process_sms_async",
                sms.id,
                task_name=f"court_sms_download_complete_recovery_{sms.id}",
            )
            return True
        if scraper_status == ScraperTaskStatus.FAILED:
            sms.status = CourtSMSStatus.DOWNLOAD_FAILED
            sms.save()
            if sms.retry_count < 3:
                async_task(
                    "apps.automation.services.sms.court_sms_service.retry_download_task",
                    sms.id,
                    task_name=f"court_sms_download_retry_recovery_{sms.id}",
                )
            return True
        # 还在下载中，跳过
        return False

    def _recover_single_sms(self, sms: Any, async_task: Any) -> bool:
        """恢复单条 SMS，返回是否成功提交恢复任务"""
        from apps.automation.models import CourtSMSStatus

        if sms.status == CourtSMSStatus.PENDING:
            async_task(
                "apps.automation.services.sms.court_sms_service.process_sms_async",
                sms.id,
                task_name=f"court_sms_recovery_{sms.id}",
            )
        elif sms.status == CourtSMSStatus.DOWNLOAD_FAILED:
            if sms.retry_count < 3:
                async_task(
                    "apps.automation.services.sms.court_sms_service.retry_download_task",
                    sms.id,
                    task_name=f"court_sms_retry_recovery_{sms.id}",
                )
            else:
                sms.status = CourtSMSStatus.FAILED
                sms.error_message = "恢复时发现重试次数已用完"
                sms.save()
                return False
        elif sms.status in [CourtSMSStatus.MATCHING, CourtSMSStatus.RENAMING, CourtSMSStatus.NOTIFYING]:
            async_task(
                "apps.automation.services.sms.court_sms_service.process_sms_async",
                sms.id,
                task_name=f"court_sms_continue_recovery_{sms.id}",
            )
        elif sms.status == CourtSMSStatus.DOWNLOADING:
            return self._recover_single_downloading(sms, async_task)
        else:
            async_task(
                "apps.automation.services.sms.court_sms_service.process_sms_async",
                sms.id,
                task_name=f"court_sms_general_recovery_{sms.id}",
            )
        return True

    def _recover_incomplete_tasks(self, max_age: Any, verbose: bool = True) -> int:
        """恢复未完成的任务"""
        from django_q.tasks import async_task

        from apps.automation.models import CourtSMS, CourtSMSStatus

        incomplete_statuses = [
            CourtSMSStatus.PENDING,
            CourtSMSStatus.PARSING,
            CourtSMSStatus.DOWNLOADING,
            CourtSMSStatus.DOWNLOAD_FAILED,
            CourtSMSStatus.MATCHING,
            CourtSMSStatus.RENAMING,
            CourtSMSStatus.NOTIFYING,
        ]

        incomplete_tasks = CourtSMS.objects.filter(
            status__in=incomplete_statuses, created_at__gte=max_age
        ).order_by("-created_at")

        recovered_count = 0
        for sms in incomplete_tasks:
            try:
                if self._recover_single_sms(sms, async_task):
                    recovered_count += 1
                    logger.info(f"恢复任务: SMS ID={sms.id}, 状态={sms.status}")
            except Exception as e:
                logger.error(f"恢复任务失败: SMS ID={sms.id}, 错误: {e!s}")
                if verbose:
                    self.stdout.write(self.style.ERROR(f"恢复任务 {sms.id} 失败: {e!s}"))

        return recovered_count
