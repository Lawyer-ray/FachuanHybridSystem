from __future__ import annotations

import logging
from typing import Any
from datetime import timedelta

from django.core.management.base import BaseCommand
from django.utils import timezone

from apps.doc_converter.models import DocConverterJob, DocConverterJobStatus

logger = logging.getLogger("apps.doc_converter")


class Command(BaseCommand):
    help = "清理过期的 DOC 转换任务及其文件"

    def add_arguments(self, parser: Any) -> None:
        parser.add_argument(
            "--completed-max-age",
            type=int,
            default=60,
            help="已完成任务的最大保留时间（分钟），默认 60",
        )
        parser.add_argument(
            "--stale-max-age",
            type=int,
            default=30,
            help="卡住任务（pending/converting/packing）的最大保留时间（分钟），默认 30",
        )
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="仅打印，不实际删除",
        )

    def handle(self, *args: Any, **options: Any) -> None:
        completed_max_age = options["completed_max_age"]
        stale_max_age = options["stale_max_age"]
        dry_run = options["dry_run"]

        now = timezone.now()
        deleted = 0

        # 1. 已完成/失败/取消的任务，超过 completed_max_age 分钟
        terminal_cutoff = now - timedelta(minutes=completed_max_age)
        terminal_jobs = DocConverterJob.objects.filter(
            status__in=[
                DocConverterJobStatus.COMPLETED,
                DocConverterJobStatus.FAILED,
                DocConverterJobStatus.CANCELLED,
            ],
            finished_at__lt=terminal_cutoff,
        )
        for job in terminal_jobs:
            if dry_run:
                self.stdout.write(f"[dry-run] 将删除任务 {job.id} (状态={job.status}, 完成于 {job.finished_at})")
            else:
                logger.info("cleanup_stale_job: %s status=%s", job.id, job.status)
                job.delete()
            deleted += 1

        # 2. 卡住的任务（pending/converting/packing 超过 stale_max_age 分钟）
        stale_cutoff = now - timedelta(minutes=stale_max_age)
        stale_jobs = DocConverterJob.objects.filter(
            status__in=[
                DocConverterJobStatus.PENDING,
                DocConverterJobStatus.CONVERTING,
                DocConverterJobStatus.PACKING,
            ],
            created_at__lt=stale_cutoff,
        )
        for job in stale_jobs:
            if dry_run:
                self.stdout.write(f"[dry-run] 将删除卡住任务 {job.id} (状态={job.status}, 创建于 {job.created_at})")
            else:
                logger.info("cleanup_stuck_job: %s status=%s", job.id, job.status)
                job.delete()
            deleted += 1

        if dry_run:
            self.stdout.write(self.style.WARNING(f"[dry-run] 共 {deleted} 个任务待清理"))
        else:
            self.stdout.write(self.style.SUCCESS(f"已清理 {deleted} 个过期任务"))
