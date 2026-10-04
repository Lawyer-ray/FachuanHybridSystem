"""Django-Q 后台任务入口。

由 admin 按钮 / 管理命令通过 ``apps.core.tasking.submit_task`` 调用，
函数路径即 dotted path：``apps.labor_arbitration.tasks.crawl_source`` 等。

Django-Q worker 同步调用任务函数（django_q.worker 直接 ``f(*args)``），
任务体为 async（ORM 走 aget/asave/acount，重 sync 服务经 ``asyncio.to_thread``
隔离），经 ``apps.core.infrastructure.sync_async_bridge.run_coro_sync`` 消费，
不再需要 ``allow_async_unsafe`` 环境变量放行。
"""

from __future__ import annotations

import asyncio
import logging
from typing import Any

from django.utils import timezone

from apps.core.infrastructure.sync_async_bridge import run_coro_sync
from apps.labor_arbitration.models import ArbitrationDocument, ArbitrationDocumentSource
from apps.labor_arbitration.services.crawler import FoshanLaborAwardCrawler
from apps.labor_arbitration.services.parsing_service import parse_arbitration_document

logger = logging.getLogger(__name__)


def crawl_source(source_id: int, limit: int | None = None) -> dict[str, Any]:
    """增量爬取某个来源的新文书。"""
    return run_coro_sync(
        _crawl_source_async(source_id, limit),
        thread_name_prefix="labor-arb-crawl",
    )


async def _crawl_source_async(source_id: int, limit: int | None) -> dict[str, Any]:
    source = await ArbitrationDocumentSource.objects.aget(id=source_id)
    try:
        crawler = FoshanLaborAwardCrawler(source, limit=limit)
        # 爬虫为纯 HTTP + sync ORM 的重服务，隔离到线程执行（线程内无事件循环，
        # sync ORM 合法）；stats 字典在线程内组装完成后回写。
        stats = await asyncio.to_thread(crawler.crawl)
        source.last_crawl_at = timezone.now()
        source.last_crawl_status = "success"
        source.last_crawl_summary = stats
        await source.asave(update_fields=["last_crawl_at", "last_crawl_status", "last_crawl_summary"])
        logger.info("[劳动仲裁] 来源 %s 爬取完成: %s", source_id, stats)
        return stats
    except Exception as exc:
        logger.error("[劳动仲裁] 来源 %s 爬取失败: %s", source_id, exc, exc_info=True)
        source.last_crawl_at = timezone.now()
        source.last_crawl_status = "failed"
        source.last_crawl_summary = {"error": str(exc)[:2000]}
        await source.asave(update_fields=["last_crawl_at", "last_crawl_status", "last_crawl_summary"])
        raise


def parse_document(doc_id: int, backend: str | None = None) -> dict[str, Any]:
    """解析某篇文书的图片（默认沿用来源的解析后端）。"""
    return run_coro_sync(
        _parse_document_async(doc_id, backend),
        thread_name_prefix="labor-arb-parse",
    )


async def _parse_document_async(doc_id: int, backend: str | None) -> dict[str, Any]:
    # select_related 预取 source，避免 async 体内触发 sync 懒加载
    doc = await ArbitrationDocument.objects.select_related("source").aget(id=doc_id)
    chosen = backend or doc.source.parse_backend or "local"
    return await asyncio.to_thread(parse_arbitration_document, doc, chosen)


def recrawl_document(doc_id: int) -> dict[str, Any]:
    """重试抓取单篇文书的详情页 + 图片（供「重试」按钮调用）。"""
    return run_coro_sync(
        _recrawl_document_async(doc_id),
        thread_name_prefix="labor-arb-recrawl",
    )


async def _recrawl_document_async(doc_id: int) -> dict[str, Any]:
    doc = await ArbitrationDocument.objects.select_related("source").aget(id=doc_id)
    crawler = FoshanLaborAwardCrawler(doc.source)
    await asyncio.to_thread(crawler.recrawl_detail, doc)
    images = await doc.images.acount()
    logger.info("[劳动仲裁] 文书 %s 重试完成，图片数=%d", doc_id, images)
    return {"ok": True, "images": images}
