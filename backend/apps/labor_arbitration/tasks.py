"""Django-Q 后台任务入口。

由 admin 按钮 / 管理命令通过 ``apps.core.tasking.submit_task`` 调用，
函数路径即 dotted path：``apps.labor_arbitration.tasks.crawl_source`` 等。
"""

from __future__ import annotations

import logging
from typing import Any

from django.utils import timezone

from apps.labor_arbitration.models import ArbitrationDocument, ArbitrationDocumentSource
from apps.labor_arbitration.services.crawler import FoshanLaborAwardCrawler
from apps.labor_arbitration.services.parsing_service import parse_arbitration_document

logger = logging.getLogger(__name__)


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
