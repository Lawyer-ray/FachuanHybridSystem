"""回收没有材料包引用的拆分任务（及其磁盘目录 / OCR 缓存）。

用于清理两批历史残留：

* 本清理功能上线前**已被删掉材料包**、但 ``PdfSplitJob`` 与任务目录还在的；
* 删除材料包时派生数据清理中途失败留下的孤儿。

判据保守：任务的 ``source_original_name`` 在任何 manual_upload 材料包的附件里
都找不到，才认定为孤儿；只要还有材料包引用就保留。

用法::

    python manage.py purge_orphan_split_jobs --dry-run   # 先看会删多少
    python manage.py purge_orphan_split_jobs             # 实删
"""

from __future__ import annotations

from typing import Any

from django.core.management.base import BaseCommand

from apps.pdf_splitting.services.cleanup_service import purge_orphan_split_jobs


class Command(BaseCommand):
    help = "回收没有材料包引用的拆分任务、任务目录与 OCR 缓存（可 --dry-run）"

    def add_arguments(self, parser: Any) -> None:
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="只统计不动手",
        )

    def handle(self, *args: Any, **options: Any) -> None:  # pragma: no cover
        dry_run = bool(options.get("dry_run"))
        if dry_run:
            self.stdout.write(self.style.WARNING("=== 试运行：只统计，不删除 ===\n"))

        stats = purge_orphan_split_jobs(dry_run=dry_run)

        self.stdout.write(f"扫描任务: {stats['scanned']}")
        self.stdout.write(f"孤儿任务: {stats['jobs']}")
        if not dry_run:
            self.stdout.write(f"已删目录: {stats['dirs']}")
            self.stdout.write(f"已删 OCR 缓存: {stats['ocr_cache']}")
        self.stdout.write(self.style.SUCCESS("\n完成"))
