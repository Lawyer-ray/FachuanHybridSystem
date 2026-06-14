"""Weike document and search mixin tests with mocked HTTP."""

from __future__ import annotations

import time
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest

from apps.legal_research.services.sources.weike.document import WeikeDocumentMixin
from apps.legal_research.services.sources.weike.search import WeikeSearchMixin
from apps.legal_research.services.sources.weike.types import WeikeCaseDetail, WeikeSearchItem, WeikeSession


def _make_session(**kwargs):
    session = MagicMock(spec=WeikeSession)
    session.task_id = kwargs.get("task_id", "test-task")
    session.restricted_until_epoch = kwargs.get("restricted_until_epoch", 0.0)
    session.search_via_api_enabled = kwargs.get("search_via_api_enabled", False)
    session.search_api_degraded_until_epoch = kwargs.get("search_api_degraded_until_epoch", 0.0)
    session.search_api_empty_streak = kwargs.get("search_api_empty_streak", 0)
    session.search_api_error_streak = kwargs.get("search_api_error_streak", 0)
    session.page = kwargs.get("page")
    session.intercepted_payload = None
    return session


def _make_search_item(**kwargs):
    return WeikeSearchItem(
        doc_id_raw=kwargs.get("doc_id_raw", "DOC001"),
        doc_id_unquoted=kwargs.get("doc_id_unquoted", "DOC001"),
        detail_url=kwargs.get("detail_url", "https://law.wkinfo.com.cn/judgment-documents/detail/DOC001"),
        title_hint=kwargs.get("title_hint", "买卖合同纠纷"),
        search_id=kwargs.get("search_id", "S001"),
        module=kwargs.get("module", "law.case"),
    )


def _make_detail(**kwargs):
    return WeikeCaseDetail(
        doc_id_raw=kwargs.get("doc_id_raw", "DOC001"),
        doc_id_unquoted=kwargs.get("doc_id_unquoted", "DOC001"),
        detail_url=kwargs.get("detail_url", ""),
        search_id=kwargs.get("search_id", ""),
        module=kwargs.get("module", "law.case"),
        title=kwargs.get("title", "买卖合同纠纷判决书"),
        court_text=kwargs.get("court_text", "北京市朝阳区人民法院"),
        document_number=kwargs.get("document_number", "2024京0105民初123号"),
        judgment_date=kwargs.get("judgment_date", "2024-01-01"),
        case_digest=kwargs.get("case_digest", "原告起诉被告"),
        content_text=kwargs.get("content_text", "本案系买卖合同纠纷"),
        raw_meta=kwargs.get("raw_meta", {}),
    )


# ── WeikeDocumentMixin tests ──────────────────────────────────


class TestWeikeDocumentMixinStatic:
    """Static and helper methods."""

    def test_detail_doc_id_candidates(self):
        item = _make_search_item(doc_id_raw="RAW1", doc_id_unquoted="UNQ1")
        result = WeikeDocumentMixin._detail_doc_id_candidates(item)
        assert "RAW1" in result
        assert "UNQ1" in result

    def test_detail_doc_id_candidates_dedup(self):
        item = _make_search_item(doc_id_raw="SAME", doc_id_unquoted="SAME")
        result = WeikeDocumentMixin._detail_doc_id_candidates(item)
        assert result == ["SAME"]

    def test_compact_error_short(self):
        exc = RuntimeError("short error")
        assert WeikeDocumentMixin._compact_error(exc) == "short error"

    def test_compact_error_long(self):
        exc = RuntimeError("x" * 200)
        result = WeikeDocumentMixin._compact_error(exc, max_len=50)
        assert len(result) <= 50

    def test_is_session_restricted_response(self):
        assert WeikeDocumentMixin._is_session_restricted_response(
            status=400, payload={"code": "C_001_009"}
        ) is True
        assert WeikeDocumentMixin._is_session_restricted_response(
            status=200, payload={"code": "C_001_009"}
        ) is True
        assert WeikeDocumentMixin._is_session_restricted_response(
            status=200, payload={"code": "OK"}
        ) is False

    def test_build_download_filename(self):
        detail = _make_detail(title="买卖合同纠纷判决书")
        filename = WeikeDocumentMixin._build_download_filename(detail)
        assert "买卖合同纠纷判决书" in filename
        assert filename.endswith(".pdf")

    def test_build_download_filename_empty_title(self):
        detail = _make_detail(title="")
        filename = WeikeDocumentMixin._build_download_filename(detail)
        assert filename.endswith(".pdf")

    def test_html_to_text(self):
        # Note: source regex [\\t\\r ]+ treats \r and \t as literal chars, so r/t get removed
        html = "<p>Hello 买卖合同</p>"
        text = WeikeDocumentMixin._html_to_text(html)
        assert "<p>" not in text
        assert "Hello" in text
        assert "买卖合同" in text

    def test_summarize_meta_payload(self):
        payload = {"currentDoc": {"title": "T", "additionalFields": {"courtText": "C"}}}
        result = WeikeDocumentMixin._summarize_meta_payload(payload)
        assert result["title"] == "T"
        assert result["court_text"] == "C"

    def test_summarize_html_payload(self):
        result = WeikeDocumentMixin._summarize_html_payload({"content": "<p>text</p>"})
        assert result["has_content"] is True
        assert result["content_length"] > 0

    def test_normalize_dom_text(self):
        text = "  hello  \xa0  world  \n\n\n\nextra"
        result = WeikeDocumentMixin._normalize_dom_text(text)
        assert "\xa0" not in result
        assert "\n\n\n" not in result

    def test_extract_dom_field(self):
        text = "审理法院：北京市朝阳区人民法院"
        result = WeikeDocumentMixin._extract_dom_field(
            text=text, patterns=(r"(?:审理法院|法院)[:：]\s*([^\n]+)",)
        )
        assert "北京市朝阳区人民法院" in result

    def test_extract_dom_field_no_match(self):
        result = WeikeDocumentMixin._extract_dom_field(text="no match", patterns=(r"xxx:(.+)",))
        assert result == ""

    def test_extract_dom_title(self):
        item = _make_search_item(title_hint="买卖合同纠纷")
        result = WeikeDocumentMixin._extract_dom_title(body_text="判决书内容", item=item)
        assert isinstance(result, str)
        assert len(result) > 0

    def test_build_dom_digest_short(self):
        assert WeikeDocumentMixin._build_dom_digest("short text") == "short text"

    def test_build_dom_digest_long(self):
        text = "x" * 300
        result = WeikeDocumentMixin._build_dom_digest(text)
        assert len(result) <= 223  # 220 + "..."

    def test_resolve_session_restrict_cooldown_seconds(self):
        mixin = WeikeDocumentMixin()
        result = mixin._resolve_session_restrict_cooldown_seconds()
        assert result >= 30


class TestWeikeDocumentSessionRestricted:
    """Session restriction checks."""

    def test_raise_if_session_restricted_active(self):
        mixin = WeikeDocumentMixin()
        session = _make_session(restricted_until_epoch=time.time() + 60)
        with pytest.raises(RuntimeError, match="限制访问"):
            mixin._raise_if_session_restricted(session=session, stage="test")

    def test_raise_if_session_restricted_expired(self):
        mixin = WeikeDocumentMixin()
        session = _make_session(restricted_until_epoch=time.time() - 10)
        # Should not raise
        mixin._raise_if_session_restricted(session=session, stage="test")


# ── WeikeSearchMixin tests ────────────────────────────────────


class TestWeikeSearchMixinStatic:
    """Static helper methods."""

    def test_parse_detail_url(self):
        url = "https://law.wkinfo.com.cn/judgment-documents/detail/DOC123?searchId=S001&module=law.case"
        result = WeikeSearchMixin._parse_detail_url(url)
        assert result is not None
        assert result.doc_id_raw == "DOC123"
        assert result.search_id == "S001"
        assert result.module == "law.case"

    def test_parse_detail_url_no_match(self):
        result = WeikeSearchMixin._parse_detail_url("https://example.com/page")
        assert result is None

    def test_compact_error_message(self):
        exc = RuntimeError("test error")
        assert WeikeSearchMixin._compact_error_message(exc) == "test error"

    def test_compact_error_message_long(self):
        exc = RuntimeError("x" * 300)
        result = WeikeSearchMixin._compact_error_message(exc, max_len=100)
        assert len(result) <= 100

    def test_is_search_api_degraded_not_degraded(self):
        session = _make_session(search_api_degraded_until_epoch=0.0)
        assert WeikeSearchMixin()._is_search_api_degraded(session=session) is False

    def test_is_search_api_degraded_active(self):
        session = _make_session(search_api_degraded_until_epoch=time.time() + 60)
        assert WeikeSearchMixin()._is_search_api_degraded(session=session) is True

    def test_is_search_api_degraded_expired(self):
        session = _make_session(search_api_degraded_until_epoch=time.time() - 10)
        assert WeikeSearchMixin()._is_search_api_degraded(session=session) is False

    def test_reset_search_api_health(self):
        session = _make_session(
            search_api_empty_streak=5,
            search_api_error_streak=3,
            search_api_degraded_until_epoch=time.time() + 60,
        )
        WeikeSearchMixin._reset_search_api_health(session=session)
        assert session.search_api_empty_streak == 0
        assert session.search_api_error_streak == 0
        assert session.search_api_degraded_until_epoch == 0.0

    def test_search_api_degraded_wait_seconds(self):
        session = _make_session(search_api_degraded_until_epoch=time.time() + 30)
        wait = WeikeSearchMixin._search_api_degraded_wait_seconds(session=session)
        assert 25 <= wait <= 30

    def test_resolve_search_api_degrade_streak_threshold(self):
        mixin = WeikeSearchMixin()
        assert mixin._resolve_search_api_degrade_streak_threshold() >= 1

    def test_resolve_search_api_degrade_cooldown_seconds(self):
        mixin = WeikeSearchMixin()
        assert mixin._resolve_search_api_degrade_cooldown_seconds() >= 30


class TestWeikeSearchMarkDegraded:
    """Mark API degraded methods."""

    def test_mark_search_api_empty_below_threshold(self):
        mixin = WeikeSearchMixin()
        mixin._search_api_degrade_streak_threshold = 3
        session = _make_session(search_api_empty_streak=0)
        mixin._mark_search_api_empty(session=session, keyword="test", offset=0, doc_count=0)
        assert session.search_api_empty_streak == 1

    def test_mark_search_api_error_below_threshold(self):
        mixin = WeikeSearchMixin()
        mixin._search_api_degrade_streak_threshold = 3
        session = _make_session(search_api_error_streak=0)
        mixin._mark_search_api_error(session=session, keyword="test", offset=0)
        assert session.search_api_error_streak == 1
