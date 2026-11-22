"""Tests for legal_research/services/sources/weike/document.py — mixin methods.

Covers uncovered branches in WeikeDocumentMixin:
  - fetch_case_detail: success path, meta non-200, html non-200,
    session restricted at meta, session restricted at html, DOM fallback,
    all errors -> RuntimeError
  - _raise_if_session_restricted: restricted / not restricted
  - _resolve_session_restrict_cooldown_seconds: various inputs
  - _mark_session_restricted
  - _fetch_case_detail_via_dom: no detail_url, page None, empty body,
    login required, normal success, playwright error
  - _record_detail_event
"""

from __future__ import annotations

import time
from types import SimpleNamespace
from typing import Any
from unittest.mock import MagicMock, patch

import pytest

from apps.legal_research.services.sources.weike import document as weike_document
from apps.legal_research.services.sources.weike.document import _record_detail_event
from apps.legal_research.services.sources.weike.types import WeikeCaseDetail, WeikeSearchItem, WeikeSession

# ---------------------------------------------------------------------------
# transport 模块级响应访问器的默认桩
# ---------------------------------------------------------------------------


@pytest.fixture(autouse=True)
def _stub_transport_response_helpers(monkeypatch: pytest.MonkeyPatch) -> None:
    """给 transport 的模块级响应访问器装默认桩（200 / {} / b""）。

    `_response_status` / `_response_headers` / `_response_body` 在 v27.4.4 的「Service 层
    静态方法棘轮」中从 mixin 下沉成模块级函数。本文件曾经改成给**实例**塞 MagicMock，
    于是「线上 `self._response_status` 已不存在 → AttributeError 被 except 吞掉 → 静默
    回退 Playwright 拿到网页壳」这件事在 CI 里始终是绿的（task 127/128/129 现场证据）。
    现在按生产代码的真实形态 patch 模块级函数：谁再把调用改回 `self.*`，这里必红。
    """
    monkeypatch.setattr(weike_document, "_response_status", lambda _resp: 200)
    monkeypatch.setattr(weike_document, "_response_headers", lambda _resp: {})
    monkeypatch.setattr(weike_document, "_response_body", lambda _resp: b"")

# ---------------------------------------------------------------------------
# Helper to create a mixin instance with required protocol attributes
# ---------------------------------------------------------------------------


def _make_mixin():
    """Create a WeikeDocumentMixin instance with stub methods."""
    from apps.legal_research.services.sources.weike.document import WeikeDocumentMixin

    m = WeikeDocumentMixin.__new__(WeikeDocumentMixin)
    m._request_get_with_retry = MagicMock()
    m._request_post_json_with_retry = MagicMock()
    m._response_json = MagicMock(return_value={})
    # _response_status / _response_headers / _response_body 是 transport 的模块级函数，
    # 由本文件的 autouse fixture 统一打桩（不要改回实例属性）。
    return m


def _make_session(**kwargs) -> WeikeSession:
    s = WeikeSession(
        page=kwargs.get("page"),
        task_id=kwargs.get("task_id", "task-1"),
        restricted_until_epoch=kwargs.get("restricted_until_epoch", 0.0),
    )
    return s


def _make_item(**kwargs) -> WeikeSearchItem:
    return WeikeSearchItem(
        doc_id_raw=kwargs.get("doc_id_raw", "RAW-1"),
        doc_id_unquoted=kwargs.get("doc_id_unquoted", "UNQ-1"),
        detail_url=kwargs.get("detail_url", "https://law.wkinfo.com.cn/detail/1"),
        title_hint=kwargs.get("title_hint", "Title"),
        search_id=kwargs.get("search_id", ""),
        module=kwargs.get("module", "law.case"),
    )


# ===========================================================================
# _raise_if_session_restricted
# ===========================================================================


class TestRaiseIfSessionRestricted:
    def test_not_restricted(self) -> None:
        m = _make_mixin()
        session = _make_session(restricted_until_epoch=0.0)
        # Should not raise
        assert m._raise_if_session_restricted(session=session, stage="test") is None

    def test_restricted_raises(self) -> None:
        m = _make_mixin()
        session = _make_session(restricted_until_epoch=time.time() + 300)
        with pytest.raises(RuntimeError, match="C_001_009"):
            m._raise_if_session_restricted(session=session, stage="test")

    def test_restricted_in_past(self) -> None:
        m = _make_mixin()
        session = _make_session(restricted_until_epoch=time.time() - 10)
        # 过去的限流时间已失效，不应抛异常
        assert m._raise_if_session_restricted(session=session, stage="test") is None

    def test_wait_seconds_at_least_1(self) -> None:
        m = _make_mixin()
        # restricted_until_epoch just 0.5 seconds in future
        session = _make_session(restricted_until_epoch=time.time() + 0.5)
        with pytest.raises(RuntimeError, match="1秒后重试"):
            m._raise_if_session_restricted(session=session, stage="test")


# ===========================================================================
# _resolve_session_restrict_cooldown_seconds
# ===========================================================================


class TestResolveSessionRestrictCooldown:
    def test_default_value(self) -> None:
        m = _make_mixin()
        assert m._resolve_session_restrict_cooldown_seconds() == 180

    def test_custom_value(self) -> None:
        m = _make_mixin()
        m._session_restrict_cooldown_seconds = 300
        assert m._resolve_session_restrict_cooldown_seconds() == 300

    def test_non_numeric_falls_back(self) -> None:
        m = _make_mixin()
        m._session_restrict_cooldown_seconds = "not_a_number"
        assert m._resolve_session_restrict_cooldown_seconds() == 180

    def test_minimum_30(self) -> None:
        m = _make_mixin()
        m._session_restrict_cooldown_seconds = 5
        assert m._resolve_session_restrict_cooldown_seconds() == 30

    def test_negative_clamped(self) -> None:
        m = _make_mixin()
        m._session_restrict_cooldown_seconds = -10
        assert m._resolve_session_restrict_cooldown_seconds() == 30


# ===========================================================================
# _mark_session_restricted
# ===========================================================================


class TestMarkSessionRestricted:
    def test_sets_cooldown(self) -> None:
        m = _make_mixin()
        session = _make_session(restricted_until_epoch=0.0)
        before = time.time()
        m._mark_session_restricted(session=session, stage="detail_meta", status=200, payload={"code": "C_001_009"})
        assert session.restricted_until_epoch > before


# ===========================================================================
# _record_detail_event
# ===========================================================================


class TestRecordDetailEvent:
    @patch("apps.legal_research.services.sources.weike.document.LegalResearchTaskEventService")
    def test_calls_record_event(self, MockEventService: MagicMock) -> None:
        session = _make_session(task_id="t-123")
        from apps.legal_research.services.sources.weike.document import WeikeDocumentMixin

        _record_detail_event(
            session=session,
            interface_name="document_meta",
            method="GET",
            url="https://example.com",
            status_code=200,
            duration_ms=100,
            success=True,
            error_code="",
            request_summary={"doc_id": "1"},
            response_summary={"title": "test"},
        )
        MockEventService.record_event.assert_called_once()
        call_kwargs = MockEventService.record_event.call_args[1]
        assert call_kwargs["task_id"] == "t-123"
        assert call_kwargs["interface_name"] == "document_meta"

    @patch("apps.legal_research.services.sources.weike.document.LegalResearchTaskEventService")
    def test_dom_detail_uses_dom_source(self, MockEventService: MagicMock) -> None:
        session = _make_session(task_id="t-456")
        from apps.legal_research.services.sources.weike.document import WeikeDocumentMixin

        _record_detail_event(
            session=session,
            interface_name="dom_detail",
            method="GET",
            url="https://example.com",
            success=True,
        )
        call_kwargs = MockEventService.record_event.call_args[1]
        assert call_kwargs["source"] == "dom"


# ===========================================================================
# fetch_case_detail — success path
# ===========================================================================


class TestFetchCaseDetailSuccess:
    @patch("apps.legal_research.services.sources.weike.document.LegalResearchTaskEventService")
    def test_success_first_docid(self, _mock_event: MagicMock) -> None:
        m = _make_mixin()
        session = _make_session()
        item = _make_item(doc_id_raw="R1", doc_id_unquoted="U1")

        # Meta response: 200
        m._response_json.side_effect = lambda r: {
            "currentDoc": {
                "title": "Case Title",
                "additionalFields": {
                    "courtText": "Beijing Court",
                    "documentNumber": "DOC-1",
                    "judgmentDate": "2024-01-01",
                    "caseDigest": "digest text",
                },
            }
        }

        # HTML response
        m._request_get_with_retry.side_effect = [
            MagicMock(),  # meta resp
            MagicMock(),  # html resp
        ]

        detail = m.fetch_case_detail(session=session, item=item)
        assert detail.title == "Case Title"
        assert detail.court_text == "Beijing Court"
        assert detail.doc_id_raw == "R1"

    @patch("apps.legal_research.services.sources.weike.document.LegalResearchTaskEventService")
    def test_meta_non_200_skips(self, _mock_event: MagicMock, monkeypatch: pytest.MonkeyPatch) -> None:
        m = _make_mixin()
        session = _make_session()
        item = _make_item(doc_id_raw="R1", doc_id_unquoted="U1")

        monkeypatch.setattr(weike_document, "_response_status", lambda _resp: 500)
        m._response_json.return_value = {}

        # Both calls return 500
        m._request_get_with_retry.side_effect = [MagicMock(), MagicMock()]

        with pytest.raises(RuntimeError, match="获取案例详情失败"):
            m.fetch_case_detail(session=session, item=item)

    @patch("apps.legal_research.services.sources.weike.document.LegalResearchTaskEventService")
    def test_session_restricted_at_meta_raises(self, _mock_event: MagicMock) -> None:
        m = _make_mixin()
        session = _make_session()
        item = _make_item()

        m._response_json.return_value = {"code": "C_001_009"}
        m._request_get_with_retry.return_value = MagicMock()

        with pytest.raises(RuntimeError, match="C_001_009"):
            m.fetch_case_detail(session=session, item=item)

    @patch("apps.legal_research.services.sources.weike.document.LegalResearchTaskEventService")
    def test_session_restricted_at_html_raises(self, _mock_event: MagicMock) -> None:
        m = _make_mixin()
        session = _make_session()
        item = _make_item()

        meta_resp = MagicMock()
        html_resp = MagicMock()
        m._request_get_with_retry.side_effect = [meta_resp, html_resp]

        def json_effect(r):
            if r is meta_resp:
                return {"currentDoc": {"title": "T", "additionalFields": {}}}
            return {"code": "C_001_009"}

        m._response_json.side_effect = json_effect

        with pytest.raises(RuntimeError, match="C_001_009"):
            m.fetch_case_detail(session=session, item=item)


# ===========================================================================
# fetch_case_detail — RuntimeError with session restrict code re-raised
# ===========================================================================


class TestFetchCaseDetailRuntimeError:
    @patch("apps.legal_research.services.sources.weike.document.LegalResearchTaskEventService")
    def test_runtime_error_without_restrict_code_continues(self, _mock_event: MagicMock) -> None:
        """RuntimeError without SESSION_RESTRICT_CODE should continue to next docId."""
        m = _make_mixin()
        session = _make_session()
        item = _make_item()

        # Make _request_get_with_retry raise RuntimeError for meta
        m._request_get_with_retry.side_effect = RuntimeError("some transient error")
        # After both docIds fail, should raise the combined error
        with pytest.raises(RuntimeError, match="获取案例详情失败"):
            m.fetch_case_detail(session=session, item=item)

    @patch("apps.legal_research.services.sources.weike.document.LegalResearchTaskEventService")
    def test_generic_exception_continues(self, _mock_event: MagicMock) -> None:
        """Generic Exception (not RuntimeError) should continue to next docId."""
        m = _make_mixin()
        session = _make_session()
        item = _make_item()

        m._request_get_with_retry.side_effect = ValueError("bad value")
        with pytest.raises(RuntimeError, match="获取案例详情失败"):
            m.fetch_case_detail(session=session, item=item)


# ===========================================================================
# _fetch_case_detail_via_dom
# ===========================================================================


class TestFetchCaseDetailViaDom:
    @patch("apps.legal_research.services.sources.weike.document.LegalResearchTaskEventService")
    def test_no_detail_url_returns_none(self, _mock_event: MagicMock) -> None:
        m = _make_mixin()
        session = _make_session()
        item = _make_item(detail_url="")
        errors: list[str] = []
        result = m._fetch_case_detail_via_dom(session=session, item=item, errors=errors)
        assert result is None

    @patch("apps.legal_research.services.sources.weike.document.LegalResearchTaskEventService")
    def test_page_none_returns_none(self, _mock_event: MagicMock) -> None:
        m = _make_mixin()
        session = _make_session(page=None)
        item = _make_item()
        errors: list[str] = []
        result = m._fetch_case_detail_via_dom(session=session, item=item, errors=errors)
        assert result is None

    @patch("apps.legal_research.services.sources.weike.document.LegalResearchTaskEventService")
    def test_empty_body_returns_none(self, _mock_event: MagicMock) -> None:
        m = _make_mixin()
        mock_page = MagicMock()
        mock_locator = MagicMock()
        mock_locator.inner_text.return_value = ""
        mock_page.locator.return_value = mock_locator
        session = _make_session(page=mock_page)
        item = _make_item()
        errors: list[str] = []
        result = m._fetch_case_detail_via_dom(session=session, item=item, errors=errors)
        assert result is None

    @patch("apps.legal_research.services.sources.weike.document.LegalResearchTaskEventService")
    def test_login_required_returns_none(self, _mock_event: MagicMock) -> None:
        m = _make_mixin()
        mock_page = MagicMock()
        mock_locator = MagicMock()
        mock_locator.inner_text.return_value = "抱歉，此功能需要登录后操作"
        mock_page.locator.return_value = mock_locator
        session = _make_session(page=mock_page)
        item = _make_item()
        errors: list[str] = []
        result = m._fetch_case_detail_via_dom(session=session, item=item, errors=errors)
        assert result is None

    @patch("apps.legal_research.services.sources.weike.document.LegalResearchTaskEventService")
    def test_normal_success(self, _mock_event: MagicMock) -> None:
        m = _make_mixin()
        mock_page = MagicMock()
        mock_locator = MagicMock()
        mock_locator.inner_text.return_value = "标题：张某诉李某合同纠纷判决书\n审理法院：北京市朝阳区人民法院\n案号：（20XX）京0105民初某某号\n裁判日期：2024年6月1日\n正文内容。"
        mock_page.locator.return_value = mock_locator
        session = _make_session(page=mock_page)
        item = _make_item(title_hint="hint")
        errors: list[str] = []
        result = m._fetch_case_detail_via_dom(session=session, item=item, errors=errors)
        assert result is not None
        assert "张某" in result.title or "判决书" in result.title
        assert "朝阳区" in result.court_text

    @patch("apps.legal_research.services.sources.weike.document.LegalResearchTaskEventService")
    def test_playwright_exception_returns_none(self, _mock_event: MagicMock) -> None:
        m = _make_mixin()
        mock_page = MagicMock()
        mock_page.goto.side_effect = Exception("page crashed")
        session = _make_session(page=mock_page)
        item = _make_item()
        errors: list[str] = []
        result = m._fetch_case_detail_via_dom(session=session, item=item, errors=errors)
        assert result is None
        assert len(errors) > 0


# ===========================================================================
# fetch_case_detail — html non-200 then DOM fallback returns detail
# ===========================================================================


class TestFetchCaseDetailDomFallback:
    @patch("apps.legal_research.services.sources.weike.document.LegalResearchTaskEventService")
    def test_all_api_fail_falls_to_dom(self, _mock_event: MagicMock, monkeypatch: pytest.MonkeyPatch) -> None:
        m = _make_mixin()
        session = _make_session()
        item = _make_item()

        # All API calls return 500
        monkeypatch.setattr(weike_document, "_response_status", lambda _resp: 500)
        m._response_json.return_value = {}
        m._request_get_with_retry.side_effect = [MagicMock(), MagicMock()]

        # Make DOM fallback return a result
        mock_page = MagicMock()
        mock_locator = MagicMock()
        mock_locator.inner_text.return_value = "标题：张某诉李某合同纠纷判决书\n审理法院：北京市朝阳区人民法院\n案号：（20XX）京0105民初某某号\n裁判日期：2024年6月1日"
        mock_page.locator.return_value = mock_locator
        session.page = mock_page

        detail = m.fetch_case_detail(session=session, item=item)
        assert detail is not None
        assert "raw_meta" in detail.__dict__ or hasattr(detail, "raw_meta")

    @patch("apps.legal_research.services.sources.weike.document.LegalResearchTaskEventService")
    def test_dom_fallback_also_fails_raises_combined(
        self, _mock_event: MagicMock, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        m = _make_mixin()
        session = _make_session()
        item = _make_item()

        monkeypatch.setattr(weike_document, "_response_status", lambda _resp: 500)
        m._response_json.return_value = {}
        m._request_get_with_retry.side_effect = [MagicMock(), MagicMock()]

        # DOM fallback fails too (no page)
        session.page = None

        with pytest.raises(RuntimeError, match="获取案例详情失败"):
            m.fetch_case_detail(session=session, item=item)


# ===========================================================================
# 真实组合回归：document + transport（禁止再依赖实例上的响应访问器）
# ===========================================================================


class TestRealCompositionedClient:
    """按生产组合（WeikeDocumentMixin + WeikeTransportMixin）跑详情链路。

    本类**不**在实例上塞 `_response_status/_response_headers/_response_body`：
    它们必须由 transport 的模块级函数提供（autouse fixture 只补默认 200）。
    一旦有人把 document.py 的调用改回 `self._response_*`，这里会直接 AttributeError——
    这正是 task 127/128/129「详情静默回退 Playwright 网页壳 + PDF 下载报错」的根因。
    """

    def _make_client(self) -> Any:
        from apps.legal_research.services.sources.weike.document import WeikeDocumentMixin
        from apps.legal_research.services.sources.weike.transport import WeikeTransportMixin

        class Composed(WeikeDocumentMixin, WeikeTransportMixin):
            pass

        return Composed()

    @patch("apps.legal_research.services.sources.weike.document.LegalResearchTaskEventService")
    def test_detail_uses_api_payload_not_dom_fallback(self, _mock_event: MagicMock) -> None:
        client = self._make_client()

        meta_payload = {
            "currentDoc": {
                "title": "某甲公司与某乙公司买卖合同纠纷一审判决书",
                "additionalFields": {
                    "courtText": "北京市朝阳区人民法院",
                    "documentNumber": "（20XX）京0105民初某某号",
                    "judgmentDate": "2024.06.01",
                    "caseDigest": "货款及违约金争议",
                },
            }
        }
        html_payload = {"content": "<h1>判决书</h1><div>本院认为，被告应支付货款。</div>"}

        def _fake_get(url: str, timeout: float | None = None) -> Any:
            body = html_payload if "/html?" in url else meta_payload
            return SimpleNamespace(status_code=200, json=lambda: body, headers={}, text="")

        session = WeikeSession(http_client=SimpleNamespace(get=_fake_get), task_id="")
        item = _make_item(doc_id_raw="R1", doc_id_unquoted="U1")

        detail = client.fetch_case_detail(session=session, item=item)

        assert detail.court_text == "北京市朝阳区人民法院"
        assert detail.document_number == "（20XX）京0105民初某某号"
        assert "本院认为" in detail.content_text
        # 走的是 API 路径，不是 Playwright DOM 兜底
        assert "detail_source" not in (detail.raw_meta or {})
