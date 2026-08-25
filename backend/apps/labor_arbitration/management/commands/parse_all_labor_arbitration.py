"""批量解析劳动仲裁文书图片（OCR + Doxify 后处理）。

用法示例::

    # 前台直接解析前 10 篇待解析文书（推荐先小批量验证）
    python manage.py parse_all_labor_arbitration --limit 10

    # 提交全部待解析文书到 Django-Q 后台队列
    python manage.py parse_all_labor_arbitration --limit 1000 --use-queue

    # 指定后端（覆盖来源默认配置）
    python manage.py parse_all_labor_arbitration --backend mineru --use-queue

    # 仅处理某来源
    python manage.py parse_all_labor_arbitration --source 1 --use-queue
"""

from __future__ import annotations

import logging
import time
from typing import Any

from django.core.management.base import BaseCommand

from apps.labor_arbitration.models import ArbitrationDocument
from apps.labor_arbitration.models.document import ParseStatus

logger = logging.getLogger(__name__)


class Command(BaseCommand):
    help = "批量解析劳动仲裁文书图片（OCR + Doxify 清洗）"

    def add_arguments(self, parser: Any) -> None:
        parser.add_argument(
            "--limit",
            type=int,
            default=None,
            help="最大处理篇数（默认不限）",
        )
        parser.add_argument(
            "--backend",
            type=str,
            default=None,
            help="解析后端：local / mineru / textin / auto（默认沿用来源配置）",
        )
        parser.add_argument(
            "--source",
            type=int,
            default=None,
            dest="source_id",
            help="仅处理指定来源 ID 的文书",
        )
        parser.add_argument(
            "--status",
            type=str,
            default="pending",
            choices=["pending", "failed", "all"],
            help="处理哪种解析状态的文书（pending / failed / all）",
        )
        parser.add_argument(
            "--use-queue",
            action="store_true",
            help="提交到 Django-Q 后台队列（默认前台直接执行）",
        )

    def handle(self, *args: Any, **options: Any) -> None:
        limit = options["limit"]
        backend = options["backend"]
        source_id = options["source_id"]
        status_filter = options["status"]
        use_queue = options["use_queue"]

        # 构建查询集
        qs = ArbitrationDocument.objects.filter(crawl_status="success")
        if source_id:
            qs = qs.filter(source_id=source_id)
        if status_filter == "pending":
            qs = qs.filter(parse_status=ParseStatus.PENDING)
        elif status_filter == "failed":
            qs = qs.filter(parse_status=ParseStatus.FAILED)
        # all = 过滤掉正在解析中的
        else:
            qs = qs.exclude(parse_status=ParseStatus.PROCESSING)

        total = qs.count()
        if limit and limit < total:
            total = limit
            qs = qs[:limit]

        if total == 0:
            self.stdout.write(self.style.WARNING("没有需要解析的文书。"))
            return

        self.stdout.write(
            f"共 {total} 篇文书待解析，后端: {backend or '来源默认'}, "
            f"模式: {'Django-Q 队列' if use_queue else '前台直接执行'}"
        )

        if use_queue:
            self._submit_to_queue(list(qs.values_list("id", flat=True)), backend)
            return

        self._parse_directly(list(qs.values_list("id", flat=True)), backend)

    def _submit_to_queue(self, doc_ids: list[int], backend: str | None) -> None:
        """将所有文书逐个提交到 Django-Q 后台队列。"""
        from apps.core.tasking import submit_task

        submitted = 0
        for doc_id in doc_ids:
            try:
                submit_task(
                    "apps.labor_arbitration.tasks.parse_document",
                    doc_id,
                    backend,
                    task_name=f"labor_parse_{doc_id}",
                    timeout=600,
                )
                submitted += 1
            except Exception as exc:
                logger.error("[劳动仲裁] 提交解析任务 %s 失败: %s", doc_id, exc)
                self.stdout.write(self.style.ERROR(f"  提交失败 doc_id={doc_id}: {exc}"))

        self.stdout.write(self.style.SUCCESS(f"已提交 {submitted}/{len(doc_ids)} 篇到 Django-Q 队列。"))
        self.stdout.write("请启动 django-q worker: python manage.py qcluster")

    def _parse_directly(self, doc_ids: list[int], backend: str | None) -> None:
        """前台直接逐个解析（适合小批量验证）。"""
        from apps.labor_arbitration.services.parsing_service import parse_arbitration_document

        ok = 0
        failed = 0
        start = time.time()
        total = len(doc_ids)

        for idx, doc_id in enumerate(doc_ids, 1):
            doc = ArbitrationDocument.objects.get(id=doc_id)
            try:
                result = parse_arbitration_document(doc, backend or "local")
                if result.get("success"):
                    ok += 1
                    self.stdout.write(f"  [{idx}/{total}] ✓ doc_id={doc_id} 完成 ({result.get('pages', '?')} 页)")
                else:
                    failed += 1
                    self.stdout.write(self.style.ERROR(f"  [{idx}/{total}] ✗ doc_id={doc_id}: {result.get('error')}"))
            except Exception as exc:
                failed += 1
                logger.error("[劳动仲裁] 前台解析 doc_id=%s 失败: %s", doc_id, exc, exc_info=True)
                self.stdout.write(self.style.ERROR(f"  [{idx}/{total}] ✗ doc_id={doc_id}: {exc}"))

            # 进度提示
            if idx % 10 == 0:
                elapsed = time.time() - start
                avg = elapsed / idx
                eta = avg * (total - idx)
                self.stdout.write(
                    f"    进度 {idx}/{total} | 成功:{ok} 失败:{failed} | 均速:{avg:.1f}s/篇 | 预计剩余:{eta / 60:.0f}分"
                )

        elapsed = time.time() - start
        self.stdout.write(
            self.style.SUCCESS(
                f"\n完成：总计 {total} 篇，成功 {ok}，失败 {failed}。"
                f"耗时 {elapsed / 60:.1f} 分，平均 {elapsed / total:.1f} 秒/篇。"
            )
        )
