"""Django-Q 后台任务入口。

由 admin 按钮 / 管理命令通过 ``apps.core.tasking.submit_task`` 调用，
函数路径即 dotted path：``apps.labor_arbitration.tasks.crawl_source`` 等。
"""

from __future__ import annotations

import logging
import os
from typing import Any

from django.utils import timezone

from apps.labor_arbitration.models import ArbitrationDocument, ArbitrationDocumentSource, DocumentCrawlStatus
from apps.labor_arbitration.services.crawler import FoshanLaborAwardCrawler
from apps.labor_arbitration.services.parsing_service import parse_arbitration_document

logger = logging.getLogger(__name__)

# Django-Q worker 以 asyncio 跑任务，且 crawler 用 Playwright sync API（内部起事件循环），
# 两者都会让 Django 同步 ORM 触发 SynchronousOnlyOperation。这里与 legal_solution 任务
# 一致地放行同步 ORM 调用（项目既有约定）。
os.environ.setdefault("DJANGO_ALLOW_ASYNC_UNSAFE", "true")


def crawl_source(source_id: int, limit: int | None = None) -> dict[str, Any]:
    """增量爬取某个来源的新文书。"""
    source = ArbitrationDocumentSource.objects.get(id=source_id)
    try:
        crawler = FoshanLaborAwardCrawler(source, limit=limit)
        stats = crawler.crawl()
        source.last_crawl_at = timezone.now()
        source.last_crawl_status = "success"
        source.last_crawl_summary = stats
        source.save(update_fields=["last_crawl_at", "last_crawl_status", "last_crawl_summary"])
        logger.info("[劳动仲裁] 来源 %s 爬取完成: %s", source_id, stats)
        return stats
    except Exception as exc:
        logger.error("[劳动仲裁] 来源 %s 爬取失败: %s", source_id, exc, exc_info=True)
        source.last_crawl_at = timezone.now()
        source.last_crawl_status = "failed"
        source.last_crawl_summary = {"error": str(exc)[:2000]}
        source.save(update_fields=["last_crawl_at", "last_crawl_status", "last_crawl_summary"])
        raise


def parse_document(doc_id: int, backend: str | None = None) -> dict[str, Any]:
    """解析某篇文书的图片（默认沿用来源的解析后端）。"""
    doc = ArbitrationDocument.objects.get(id=doc_id)
    chosen = backend or doc.source.parse_backend or "local"
    return parse_arbitration_document(doc, chosen)


def auto_resume_crawl() -> dict[str, Any]:
    """自愈续爬：网络中断恢复后自动重爬失败/未完成的来源。

    供定时 Schedule 周期调用；幂等。仅对「上次爬取失败」或「存在 pending/failed 文书」且
    当前未在爬取中的来源触发增量更新，已成功的来源与正在跑的来源不会重复触发。
    """
    from apps.labor_arbitration.models import CrawlStatus

    resumed: list[int] = []
    for source in ArbitrationDocumentSource.objects.filter(enabled=True):
        if source.last_crawl_status == CrawlStatus.RUNNING:
            continue
        has_incomplete = ArbitrationDocument.objects.filter(
            source=source,
            crawl_status__in=[DocumentCrawlStatus.PENDING, DocumentCrawlStatus.FAILED],
        ).exists()
        if source.last_crawl_status == CrawlStatus.FAILED or has_incomplete:
            source.trigger_update()
            resumed.append(source.id)
    logger.info("[劳动仲裁] 自愈续爬触发来源: %s", resumed)
    return {"resumed": resumed}
