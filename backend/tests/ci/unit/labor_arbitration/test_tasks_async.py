"""labor_arbitration.tasks 真 async 化后的任务体测试。

覆盖：
- 三个 Django-Q 入口（crawl_source / parse_document / recrawl_document）经统一
  桥接消费 async 任务体；
- async 任务体真实 await（aget/asave/acount），重 sync 服务打桩隔离；
- 失败路径回写 last_crawl_status=failed 并透传异常。
"""

from __future__ import annotations

from typing import Any
from unittest.mock import MagicMock, patch

import pytest

from apps.labor_arbitration.models import (
    ArbitrationDocument,
    ArbitrationDocumentImage,
    ArbitrationDocumentSource,
    CrawlStatus,
)


@pytest.fixture
def source(db: Any) -> ArbitrationDocumentSource:
    return ArbitrationDocumentSource.objects.create(
        name="测试来源",
        list_url="https://example.com/list-1",
        category_id=123,
        parse_backend="local",
    )


@pytest.fixture
def doc(source: ArbitrationDocumentSource) -> ArbitrationDocument:
    return ArbitrationDocument.objects.create(source=source, title="文书", detail_url="https://example.com/d/1")


# async ORM 经 asgiref 线程敏感执行器跑在与测试线程不同的连接上，
# 需要 transaction=True 让 fixture 数据真实提交可见（同 test_cloud_storage_account_service 模式）。
@pytest.mark.django_db(transaction=True)
class TestCrawlSource:
    def test_sync_entry_runs_async_body(self, source: ArbitrationDocumentSource):
        """sync 入口端到端：桥接真实消费 async 任务体并回写状态。"""
        stats = {"discovered": 1, "new": 1, "skipped": 0, "failed": 0, "images": 2}
        with patch("apps.labor_arbitration.tasks.FoshanLaborAwardCrawler") as MockCrawler:
            MockCrawler.return_value.crawl.return_value = stats
            from apps.labor_arbitration.tasks import crawl_source

            result = crawl_source(source.id)

        assert result == stats
        source.refresh_from_db()
        assert source.last_crawl_status == CrawlStatus.SUCCESS
        assert source.last_crawl_summary == stats
        assert source.last_crawl_at is not None

    @pytest.mark.asyncio
    @pytest.mark.django_db(transaction=True)
    async def test_async_body_uses_async_orm(self, source: ArbitrationDocumentSource):
        """真 async 断言：任务体直接 await，source 经 aget 读取、asave 回写。"""
        stats = {"discovered": 0, "new": 0, "skipped": 0, "failed": 0, "images": 0}
        with patch("apps.labor_arbitration.tasks.FoshanLaborAwardCrawler") as MockCrawler:
            MockCrawler.return_value.crawl.return_value = stats
            from apps.labor_arbitration.tasks import _crawl_source_async

            result = await _crawl_source_async(source.id, None)

        assert result == stats
        await source.arefresh_from_db()
        assert source.last_crawl_status == CrawlStatus.SUCCESS

    @pytest.mark.asyncio
    @pytest.mark.django_db(transaction=True)
    async def test_async_body_failure_marks_failed_and_reraises(self, source: ArbitrationDocumentSource):
        with patch("apps.labor_arbitration.tasks.FoshanLaborAwardCrawler") as MockCrawler:
            MockCrawler.return_value.crawl.side_effect = RuntimeError("列表接口 403")
            from apps.labor_arbitration.tasks import _crawl_source_async

            with pytest.raises(RuntimeError, match="列表接口 403"):
                await _crawl_source_async(source.id, None)

        await source.arefresh_from_db()
        assert source.last_crawl_status == CrawlStatus.FAILED
        assert source.last_crawl_summary == {"error": "列表接口 403"}

    def test_limit_forwarded_to_crawler(self, source: ArbitrationDocumentSource):
        with patch("apps.labor_arbitration.tasks.FoshanLaborAwardCrawler") as MockCrawler:
            MockCrawler.return_value.crawl.return_value = {}
            from apps.labor_arbitration.tasks import crawl_source

            crawl_source(source.id, 5)

        assert MockCrawler.call_args.kwargs == {"limit": 5}


@pytest.mark.django_db(transaction=True)
class TestParseDocument:
    def test_sync_entry_runs_async_body(self, doc: ArbitrationDocument):
        with patch("apps.labor_arbitration.tasks.parse_arbitration_document") as mock_parse:
            mock_parse.return_value = {"success": True, "doc_id": doc.id, "pages": 3}
            from apps.labor_arbitration.tasks import parse_document

            result = parse_document(doc.id)

        assert result == {"success": True, "doc_id": doc.id, "pages": 3}
        # 默认沿用来源配置的解析后端
        assert mock_parse.call_args.args[1] == "local"

    def test_explicit_backend_wins(self, doc: ArbitrationDocument):
        with patch("apps.labor_arbitration.tasks.parse_arbitration_document") as mock_parse:
            mock_parse.return_value = {"success": True}
            from apps.labor_arbitration.tasks import parse_document

            parse_document(doc.id, "mineru")

        assert mock_parse.call_args.args[1] == "mineru"


@pytest.mark.django_db(transaction=True)
class TestRecrawlDocument:
    def test_sync_entry_returns_image_count(self, doc: ArbitrationDocument):
        ArbitrationDocumentImage.objects.create(document=doc, page_index=0, source_url="https://x/1.png")
        ArbitrationDocumentImage.objects.create(document=doc, page_index=1, source_url="https://x/2.png")

        with patch("apps.labor_arbitration.tasks.FoshanLaborAwardCrawler") as MockCrawler:
            from apps.labor_arbitration.tasks import recrawl_document

            result = recrawl_document(doc.id)

        assert result == {"ok": True, "images": 2}
        # recrawl_detail 在 to_thread 中被调用，入参为同一 doc
        assert MockCrawler.return_value.recrawl_detail.call_args.args[0].id == doc.id

    @pytest.mark.asyncio
    @pytest.mark.django_db(transaction=True)
    async def test_async_body_uses_acount(self, doc: ArbitrationDocument):
        """真 async 断言：图片计数走 acount（async 查询）。"""
        await ArbitrationDocumentImage.objects.acreate(
            document=doc, page_index=0, source_url="https://x/1.png"
        )
        with patch("apps.labor_arbitration.tasks.FoshanLaborAwardCrawler"):
            from apps.labor_arbitration.tasks import _recrawl_document_async

            result = await _recrawl_document_async(doc.id)

        assert result == {"ok": True, "images": 1}


class TestModuleContract:
    def test_no_allow_async_unsafe_import_left(self):
        """async 化后任务模块不应再引用 allow_async_unsafe（文档字符串提及不算）。"""
        from apps.labor_arbitration import tasks as tasks_module

        assert not hasattr(tasks_module, "allow_async_unsafe")
