"""劳动仲裁模型行为单元测试。

覆盖：
- ArbitrationDocument.save 对 search_vector 的回填触发（PostgreSQL 全文向量）；
- trigger_parse / trigger_recrawl 的任务提交与状态翻转；
- ArbitrationDocumentSource.trigger_update 的防重复提交守卫。
"""

from __future__ import annotations

from typing import Any
from unittest.mock import patch

import pytest

from apps.labor_arbitration.models import (
    ArbitrationDocument,
    ArbitrationDocumentSource,
    CrawlStatus,
    DocumentCrawlStatus,
    ParseStatus,
)


@pytest.fixture
def source(db: Any) -> ArbitrationDocumentSource:
    return ArbitrationDocumentSource.objects.create(name="测试来源", list_url="https://example.com/list-1")


@pytest.fixture
def doc(source: ArbitrationDocumentSource) -> ArbitrationDocument:
    return ArbitrationDocument.objects.create(source=source, title="文书", detail_url="https://example.com/d/1")


class TestSearchVectorBackfill:
    @pytest.mark.django_db
    def test_parsed_text_triggers_vector_backfill(self, doc: ArbitrationDocument) -> None:
        doc.parsed_text = "劳动仲裁 裁决书"
        doc.save()
        doc.refresh_from_db()
        assert doc.search_vector is not None
        # simple 配置按词建向量，"劳动仲裁" 与 "裁决书" 均应出现
        vector_text = str(doc.search_vector)
        assert "劳动仲裁" in vector_text
        assert "裁决书" in vector_text

    @pytest.mark.django_db
    def test_empty_text_no_vector(self, doc: ArbitrationDocument) -> None:
        doc.refresh_from_db()
        assert doc.search_vector is None


class TestDocumentTriggers:
    @pytest.mark.django_db
    def test_trigger_parse_submits_and_marks_processing(self, doc: ArbitrationDocument) -> None:
        with patch("apps.core.tasking.submit_task", return_value="task-abc") as submit:
            task_id = doc.trigger_parse(backend="mineru")
        assert task_id == "task-abc"
        submit.assert_called_once()
        assert submit.call_args.args[0] == "apps.labor_arbitration.tasks.parse_document"
        doc.refresh_from_db()
        assert doc.parse_status == ParseStatus.PROCESSING

    @pytest.mark.django_db
    def test_trigger_recrawl_marks_crawling(self, doc: ArbitrationDocument) -> None:
        with patch("apps.core.tasking.submit_task", return_value="task-recrawl"):
            doc.trigger_recrawl()
        doc.refresh_from_db()
        assert doc.crawl_status == DocumentCrawlStatus.CRAWLING


class TestSourceTriggerUpdate:
    @pytest.mark.django_db
    def test_submit_when_idle(self, source: ArbitrationDocumentSource) -> None:
        with patch("apps.core.tasking.submit_task", return_value="task-1") as submit:
            task_id = source.trigger_update()
        assert task_id == "task-1"
        submit.assert_called_once()
        source.refresh_from_db()
        assert source.last_crawl_status == CrawlStatus.RUNNING

    @pytest.mark.django_db
    def test_skip_when_already_running(self, source: ArbitrationDocumentSource) -> None:
        source.last_crawl_status = CrawlStatus.RUNNING
        source.save(update_fields=["last_crawl_status"])
        with patch("apps.core.tasking.submit_task") as submit:
            assert source.trigger_update() is None
        submit.assert_not_called()
