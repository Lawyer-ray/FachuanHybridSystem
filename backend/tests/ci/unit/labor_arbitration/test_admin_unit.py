"""labor_arbitration Admin 单元测试 — 列表列渲染、按钮、自定义视图与批量 action。

用 RequestFactory + FallbackStorage 驱动 message_user，不发起真实 HTTP 请求。
"""

from __future__ import annotations

from typing import Any
from unittest.mock import MagicMock, patch

import pytest
from django.contrib import admin as dj_admin
from django.contrib.messages.storage.fallback import FallbackStorage
from django.test import RequestFactory
from django.urls import reverse

from apps.labor_arbitration.admin.document_admin import ArbitrationDocumentAdmin
from apps.labor_arbitration.admin.source_admin import ArbitrationDocumentSourceAdmin
from apps.labor_arbitration.models import (
    ArbitrationDocument,
    ArbitrationDocumentImage,
    ArbitrationDocumentSource,
    CrawlStatus,
    DocumentCrawlStatus,
)


@pytest.fixture
def source(db: Any) -> ArbitrationDocumentSource:
    return ArbitrationDocumentSource.objects.create(
        name="测试来源", list_url="https://example.com/list-1", category_id=123, parse_backend="local"
    )


@pytest.fixture
def doc(source: ArbitrationDocumentSource) -> ArbitrationDocument:
    return ArbitrationDocument.objects.create(
        source=source, title="佛劳人仲案字〔2024〕1号", detail_url="https://example.com/d/1"
    )


def _admin_instance(model: Any, admin_cls: Any) -> Any:
    return admin_cls(model, dj_admin.site)


def _request_with_messages() -> Any:
    request = RequestFactory().get("/")
    request.session = "session"
    request._messages = FallbackStorage(request)
    return request


@pytest.mark.django_db
class TestDocumentAdminDisplay:
    def test_image_count_uses_annotation(self, doc: ArbitrationDocument) -> None:
        document_admin = _admin_instance(ArbitrationDocument, ArbitrationDocumentAdmin)
        request = _request_with_messages()
        qs = document_admin.get_queryset(request)
        annotated = qs.get(pk=doc.pk)
        assert document_admin.image_count(annotated) == 0

    def test_image_count_fallback_without_annotation(self, doc: ArbitrationDocument) -> None:
        document_admin = _admin_instance(ArbitrationDocument, ArbitrationDocumentAdmin)
        ArbitrationDocumentImage.objects.create(document=doc, page_index=0, source_url="https://x/1.png")
        assert document_admin.image_count(doc) == 1

    def test_images_preview_empty(self, doc: ArbitrationDocument) -> None:
        document_admin = _admin_instance(ArbitrationDocument, ArbitrationDocumentAdmin)
        html = str(document_admin.images_preview(doc))
        assert "暂无图片" in html

    def test_images_preview_escapes_url(self, doc: ArbitrationDocument) -> None:
        document_admin = _admin_instance(ArbitrationDocument, ArbitrationDocumentAdmin)
        ArbitrationDocumentImage.objects.create(
            document=doc, page_index=0, source_url='https://x/1.png?a=1&b="><script>'
        )
        html = str(document_admin.images_preview(doc))
        assert "data-src=" in html
        assert "<script>" not in html  # 已被转义
        assert "共 1 页" in html

    def test_parsed_text_display_empty(self, doc: ArbitrationDocument) -> None:
        document_admin = _admin_instance(ArbitrationDocument, ArbitrationDocumentAdmin)
        assert "-" in str(document_admin.parsed_text_display(doc))

    def test_parsed_text_display_content(self, doc: ArbitrationDocument) -> None:
        doc.parsed_text = "裁决书正文" * 10
        document_admin = _admin_instance(ArbitrationDocument, ArbitrationDocumentAdmin)
        html = str(document_admin.parsed_text_display(doc))
        assert "裁决书正文" in html
        assert "<pre" in html

    def test_parse_button_unsaved(self) -> None:
        document_admin = _admin_instance(ArbitrationDocument, ArbitrationDocumentAdmin)
        unsaved = ArbitrationDocument(source=_source_stub(), title="t", detail_url="https://x/1")
        assert "-" in str(document_admin.parse_button(unsaved))

    def test_parse_button_no_images(self, doc: ArbitrationDocument) -> None:
        document_admin = _admin_instance(ArbitrationDocument, ArbitrationDocumentAdmin)
        assert "无图片可解析" in str(document_admin.parse_button(doc))

    def test_parse_button_with_images(self, doc: ArbitrationDocument) -> None:
        ArbitrationDocumentImage.objects.create(document=doc, page_index=0, source_url="https://x/1.png")
        document_admin = _admin_instance(ArbitrationDocument, ArbitrationDocumentAdmin)
        html = str(document_admin.parse_button(doc))
        expected_url = reverse("admin:labor_arbitration_arbitrationdocument_parse", args=[doc.pk])
        assert expected_url in html

    def test_retry_button_labels_by_images(self, doc: ArbitrationDocument) -> None:
        document_admin = _admin_instance(ArbitrationDocument, ArbitrationDocumentAdmin)
        html_no_img = str(document_admin.retry_button(doc))
        assert "重试抓取图片" in html_no_img
        ArbitrationDocumentImage.objects.create(document=doc, page_index=0, source_url="https://x/1.png")
        assert "重新抓取" in str(document_admin.retry_button(doc))

    def test_retry_button_unsaved(self) -> None:
        document_admin = _admin_instance(ArbitrationDocument, ArbitrationDocumentAdmin)
        unsaved = ArbitrationDocument(source=_source_stub(), title="t", detail_url="https://x/2")
        assert "-" in str(document_admin.retry_button(unsaved))


def _source_stub() -> ArbitrationDocumentSource:
    stub = ArbitrationDocumentSource(name="stub", list_url="https://example.com/s")
    return stub


@pytest.mark.django_db
class TestDocumentAdminViews:
    def test_parse_view_redirects_with_task_id(self, doc: ArbitrationDocument) -> None:
        document_admin = _admin_instance(ArbitrationDocument, ArbitrationDocumentAdmin)
        request = _request_with_messages()
        with patch.object(ArbitrationDocument, "trigger_parse", return_value="q-task-1") as m_trigger:
            response = document_admin.parse_view(request, str(doc.pk))
        m_trigger.assert_called_once()
        assert response.status_code == 302
        assert response.url == reverse("admin:labor_arbitration_arbitrationdocument_change", args=[doc.pk])
        assert "q-task-1" in str([m.message for m in request._messages])

    def test_retry_view_redirects_with_task_id(self, doc: ArbitrationDocument) -> None:
        document_admin = _admin_instance(ArbitrationDocument, ArbitrationDocumentAdmin)
        request = _request_with_messages()
        with patch.object(ArbitrationDocument, "trigger_recrawl", return_value="q-task-2") as m_trigger:
            response = document_admin.retry_view(request, str(doc.pk))
        m_trigger.assert_called_once()
        assert response.status_code == 302
        assert "q-task-2" in str([m.message for m in request._messages])

    def test_trigger_parse_action_skips_no_image_docs(self, source: ArbitrationDocumentSource) -> None:
        with_images = ArbitrationDocument.objects.create(source=source, title="有图", detail_url="https://x/w")
        ArbitrationDocumentImage.objects.create(document=with_images, page_index=0, source_url="https://x/1.png")
        without_images = ArbitrationDocument.objects.create(source=source, title="无图", detail_url="https://x/n")

        document_admin = _admin_instance(ArbitrationDocument, ArbitrationDocumentAdmin)
        request = _request_with_messages()
        with patch.object(ArbitrationDocument, "trigger_parse", return_value="t") as m_trigger:
            document_admin.trigger_parse_action(
                request, ArbitrationDocument.objects.filter(pk__in=[with_images.pk, without_images.pk])
            )

        assert m_trigger.call_count == 1
        assert "已提交 1 个文书的解析任务" in str([m.message for m in request._messages])

    def test_retry_action_calls_all(self, source: ArbitrationDocumentSource) -> None:
        d1 = ArbitrationDocument.objects.create(source=source, title="A", detail_url="https://x/a")
        d2 = ArbitrationDocument.objects.create(source=source, title="B", detail_url="https://x/b")
        document_admin = _admin_instance(ArbitrationDocument, ArbitrationDocumentAdmin)
        request = _request_with_messages()
        with patch.object(ArbitrationDocument, "trigger_recrawl", return_value="t") as m_trigger:
            document_admin.retry_action(request, ArbitrationDocument.objects.filter(pk__in=[d1.pk, d2.pk]))
        assert m_trigger.call_count == 2
        assert "已提交 2 个文书的重试抓取任务" in str([m.message for m in request._messages])


@pytest.mark.django_db
class TestDocumentAdminSearch:
    def test_fts_hit_returns_ranked_queryset(self, source: ArbitrationDocumentSource) -> None:
        doc = ArbitrationDocument.objects.create(
            source=source, title="检索目标", detail_url="https://x/fts", parsed_text="劳动仲裁裁决书全文内容"
        )
        doc.refresh_from_db()  # save() 触发 search_vector 回填
        document_admin = _admin_instance(ArbitrationDocument, ArbitrationDocumentAdmin)
        request = _request_with_messages()
        qs = ArbitrationDocument.objects.all()
        result_qs, use_distinct = document_admin.get_search_results(request, qs, "劳动仲裁")
        assert doc.pk in list(result_qs.values_list("pk", flat=True))
        assert use_distinct is False

    def test_fts_miss_falls_back_to_ilike(self, source: ArbitrationDocumentSource) -> None:
        doc = ArbitrationDocument.objects.create(source=source, title="特别标题XYZ", detail_url="https://x/ilike")
        document_admin = _admin_instance(ArbitrationDocument, ArbitrationDocumentAdmin)
        request = _request_with_messages()
        qs = ArbitrationDocument.objects.all()
        result_qs, _ = document_admin.get_search_results(request, qs, "特别标题XYZ")
        assert doc.pk in list(result_qs.values_list("pk", flat=True))

    def test_empty_term_uses_default(self) -> None:
        document_admin = _admin_instance(ArbitrationDocument, ArbitrationDocumentAdmin)
        request = _request_with_messages()
        qs = MagicMock()
        qs.all.return_value = qs
        result_qs, _ = document_admin.get_search_results(request, qs, "")
        assert result_qs is qs.all()

    def test_add_permission_denied(self) -> None:
        document_admin = _admin_instance(ArbitrationDocument, ArbitrationDocumentAdmin)
        assert document_admin.has_add_permission(_request_with_messages()) is False


@pytest.mark.django_db
class TestSourceAdminDisplay:
    def test_document_count_annotated(self, source: ArbitrationDocumentSource, doc: ArbitrationDocument) -> None:
        source_admin = _admin_instance(ArbitrationDocumentSource, ArbitrationDocumentSourceAdmin)
        request = _request_with_messages()
        annotated = source_admin.get_queryset(request).get(pk=source.pk)
        assert source_admin.document_count(annotated) == 1

    def test_document_count_fallback(self, source: ArbitrationDocumentSource, doc: ArbitrationDocument) -> None:
        source_admin = _admin_instance(ArbitrationDocumentSource, ArbitrationDocumentSourceAdmin)
        assert source_admin.document_count(source) == 1

    def test_last_crawl_summary_empty(self, source: ArbitrationDocumentSource) -> None:
        source_admin = _admin_instance(ArbitrationDocumentSource, ArbitrationDocumentSourceAdmin)
        assert "-" in str(source_admin.last_crawl_summary_display(source))

    def test_last_crawl_summary_renders_json(self, source: ArbitrationDocumentSource) -> None:
        source.last_crawl_summary = {"new": 3, "failed": 1}
        source_admin = _admin_instance(ArbitrationDocumentSource, ArbitrationDocumentSourceAdmin)
        html = str(source_admin.last_crawl_summary_display(source))
        assert "<pre" in html
        assert "new" in html and "3" in html and "failed" in html

    def test_update_button_urls(self, source: ArbitrationDocumentSource) -> None:
        source_admin = _admin_instance(ArbitrationDocumentSource, ArbitrationDocumentSourceAdmin)
        html = str(source_admin.update_button(source))
        assert reverse("admin:labor_arbitration_arbitrationdocumentsource_update", args=[source.pk]) in html

    def test_update_button_unsaved(self) -> None:
        source_admin = _admin_instance(ArbitrationDocumentSource, ArbitrationDocumentSourceAdmin)
        assert "-" in str(source_admin.update_button(ArbitrationDocumentSource(name="x", list_url="https://x/1")))


@pytest.mark.django_db
class TestSourceAdminViews:
    def test_update_view_submits_task(self, source: ArbitrationDocumentSource) -> None:
        source_admin = _admin_instance(ArbitrationDocumentSource, ArbitrationDocumentSourceAdmin)
        request = _request_with_messages()
        with patch.object(ArbitrationDocumentSource, "trigger_update", return_value="q-1") as m_trigger:
            response = source_admin.update_view(request, str(source.pk))
        m_trigger.assert_called_once()
        assert response.status_code == 302
        assert "q-1" in str([m.message for m in request._messages])

    def test_update_view_skips_running_source(self, source: ArbitrationDocumentSource) -> None:
        source.last_crawl_status = CrawlStatus.RUNNING
        source.save(update_fields=["last_crawl_status"])
        source_admin = _admin_instance(ArbitrationDocumentSource, ArbitrationDocumentSourceAdmin)
        request = _request_with_messages()
        # trigger_update 真实现：RUNNING 时返回 None → 警告消息
        response = source_admin.update_view(request, str(source.pk))
        assert response.status_code == 302
        assert "已跳过重复提交" in str([m.message for m in request._messages])

    def test_trigger_update_action_counts(self, source: ArbitrationDocumentSource) -> None:
        source_admin = _admin_instance(ArbitrationDocumentSource, ArbitrationDocumentSourceAdmin)
        request = _request_with_messages()
        with patch.object(ArbitrationDocumentSource, "trigger_update", return_value="q-9"):
            source_admin.trigger_update_action(request, ArbitrationDocumentSource.objects.filter(pk=source.pk))
        assert "已提交 1 个来源的增量更新任务" in str([m.message for m in request._messages])

    def test_trigger_update_action_reports_skipped(self, source: ArbitrationDocumentSource) -> None:
        source_admin = _admin_instance(ArbitrationDocumentSource, ArbitrationDocumentSourceAdmin)
        request = _request_with_messages()
        with patch.object(ArbitrationDocumentSource, "trigger_update", return_value=None):
            source_admin.trigger_update_action(request, ArbitrationDocumentSource.objects.filter(pk=source.pk))
        assert "1 个来源已在爬取中被跳过" in str([m.message for m in request._messages])


@pytest.mark.django_db
class TestDocumentAdminCrawlStatusField:
    def test_list_display_includes_crawl_columns(self) -> None:
        document_admin = _admin_instance(ArbitrationDocument, ArbitrationDocumentAdmin)
        assert "crawl_status" in document_admin.list_display
        assert "parse_status" in document_admin.list_display
        assert "trigger_parse_action" in document_admin.actions
        assert "retry_action" in document_admin.actions
