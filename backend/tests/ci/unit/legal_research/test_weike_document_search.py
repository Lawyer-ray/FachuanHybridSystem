"""Weike 文档和搜索 mixin 测试。"""

from unittest.mock import MagicMock, patch

import pytest

from apps.legal_research.services.sources.weike.document import WeikeDocumentMixin
from apps.legal_research.services.sources.weike.search import WeikeSearchMixin


class TestWeikeDocumentMixinHelpers:
    """WeikeDocumentMixin 静态方法和辅助逻辑测试。"""

    # ── _detail_doc_id_candidates ──

    def test_detail_doc_id_candidates_both(self):
        from apps.legal_research.services.sources.weike.types import WeikeSearchItem

        item = WeikeSearchItem(
            doc_id_raw="abc", doc_id_unquoted="abc_unquoted",
            detail_url="", title_hint="", search_id="", module=""
        )
        result = WeikeDocumentMixin._detail_doc_id_candidates(item)
        assert "abc" in result
        assert "abc_unquoted" in result

    def test_detail_doc_id_candidates_dedup(self):
        from apps.legal_research.services.sources.weike.types import WeikeSearchItem

        item = WeikeSearchItem(
            doc_id_raw="abc", doc_id_unquoted="abc",
            detail_url="", title_hint="", search_id="", module=""
        )
        result = WeikeDocumentMixin._detail_doc_id_candidates(item)
        assert len(result) == 1

    # ── _compact_error ──

    def test_compact_error_short(self):
        result = WeikeDocumentMixin._compact_error(RuntimeError("短错误"))
        assert result == "短错误"

    def test_compact_error_long(self):
        long_msg = "x" * 200
        result = WeikeDocumentMixin._compact_error(RuntimeError(long_msg), max_len=50)
        assert len(result) <= 50
        assert result.endswith("...")

    def test_compact_error_empty(self):
        result = WeikeDocumentMixin._compact_error(RuntimeError(""))
        assert len(result) > 0  # uses class name

    # ── _is_session_restricted_response ──

    def test_is_session_restricted_code_match(self):
        result = WeikeDocumentMixin._is_session_restricted_response(
            status=200, payload={"code": "C_001_009"}
        )
        assert result is True

    def test_is_session_restricted_code_case_insensitive(self):
        result = WeikeDocumentMixin._is_session_restricted_response(
            status=200, payload={"code": "c_001_009"}
        )
        assert result is True

    def test_is_session_restricted_400_with_code(self):
        result = WeikeDocumentMixin._is_session_restricted_response(
            status=400, payload={"code": "C_001_009"}
        )
        assert result is True

    def test_is_session_restricted_normal(self):
        result = WeikeDocumentMixin._is_session_restricted_response(
            status=200, payload={"code": "OK"}
        )
        assert result is False

    def test_is_session_restricted_none_payload(self):
        result = WeikeDocumentMixin._is_session_restricted_response(
            status=200, payload=None
        )
        assert result is False

    # ── _raise_if_session_restricted ──

    def test_raise_if_session_restricted_not_restricted(self):
        mixin = WeikeDocumentMixin.__new__(WeikeDocumentMixin)
        session = MagicMock()
        session.restricted_until_epoch = 0.0
        # Should not raise
        mixin._raise_if_session_restricted(session=session, stage="test")

    def test_raise_if_session_restricted_restricted(self):
        import time
        mixin = WeikeDocumentMixin.__new__(WeikeDocumentMixin)
        session = MagicMock()
        session.restricted_until_epoch = time.time() + 60
        with pytest.raises(RuntimeError, match="C_001_009"):
            mixin._raise_if_session_restricted(session=session, stage="test")

    # ── _resolve_session_restrict_cooldown_seconds ──

    def test_resolve_session_restrict_cooldown_default(self):
        mixin = WeikeDocumentMixin.__new__(WeikeDocumentMixin)
        result = mixin._resolve_session_restrict_cooldown_seconds()
        assert result >= 30

    def test_resolve_session_restrict_cooldown_custom(self):
        mixin = WeikeDocumentMixin.__new__(WeikeDocumentMixin)
        mixin._session_restrict_cooldown_seconds = 60
        result = mixin._resolve_session_restrict_cooldown_seconds()
        assert result == 60

    def test_resolve_session_restrict_cooldown_minimum(self):
        mixin = WeikeDocumentMixin.__new__(WeikeDocumentMixin)
        mixin._session_restrict_cooldown_seconds = 5
        result = mixin._resolve_session_restrict_cooldown_seconds()
        assert result >= 30

    # ── _build_download_filename ──

    def test_build_download_filename_normal(self):
        from apps.legal_research.services.sources.weike.types import WeikeCaseDetail

        detail = WeikeCaseDetail(
            doc_id_raw="abc", doc_id_unquoted="abc",
            detail_url="", search_id="", module="",
            title="张某诉李某合同纠纷", court_text="",
            document_number="", judgment_date="",
            case_digest="", content_text="", raw_meta={}
        )
        filename = WeikeDocumentMixin._build_download_filename(detail)
        assert "张某诉李某合同纠纷" in filename
        assert filename.endswith(".pdf")

    def test_build_download_filename_special_chars(self):
        from apps.legal_research.services.sources.weike.types import WeikeCaseDetail

        detail = WeikeCaseDetail(
            doc_id_raw="abc", doc_id_unquoted="abc",
            detail_url="", search_id="", module="",
            title='张某\\李某:合同*纠纷?', court_text="",
            document_number="", judgment_date="",
            case_digest="", content_text="", raw_meta={}
        )
        filename = WeikeDocumentMixin._build_download_filename(detail)
        assert "\\" not in filename
        assert ":" not in filename
        assert "*" not in filename

    def test_build_download_filename_empty_title(self):
        from apps.legal_research.services.sources.weike.types import WeikeCaseDetail

        detail = WeikeCaseDetail(
            doc_id_raw="abc", doc_id_unquoted="id123",
            detail_url="", search_id="", module="",
            title="", court_text="",
            document_number="", judgment_date="",
            case_digest="", content_text="", raw_meta={}
        )
        filename = WeikeDocumentMixin._build_download_filename(detail)
        assert "id123" in filename

    # ── _html_to_text ──

    def test_html_to_text_removes_script(self):
        result = WeikeDocumentMixin._html_to_text('<p>hello</p><script>alert("xss")</script>')
        assert "alert" not in result
        assert "hello" in result

    def test_html_to_text_removes_style(self):
        result = WeikeDocumentMixin._html_to_text('<p>hello</p><style>.cls{color:red}</style>')
        assert "hello" in result
        # style content should be removed or replaced

    def test_html_to_text_converts_br(self):
        result = WeikeDocumentMixin._html_to_text("line1<br>line2")
        assert "line1" in result
        assert "line2" in result

    def test_html_to_text_converts_p(self):
        result = WeikeDocumentMixin._html_to_text("<p>para1</p><p>para2</p>")
        assert "\n" in result

    def test_html_to_text_strips_tags(self):
        result = WeikeDocumentMixin._html_to_text("<b>bold</b>")
        assert "<b>" not in result
        assert "bold" in result

    def test_html_to_text_unescapes_entities(self):
        result = WeikeDocumentMixin._html_to_text("&amp; &lt; &gt;")
        assert "&" in result
        assert "<" in result

    # ── _normalize_dom_text ──

    def test_normalize_dom_text_nbsp(self):
        result = WeikeDocumentMixin._normalize_dom_text("hello\xa0world")
        assert "\xa0" not in result

    def test_normalize_dom_text_multi_newlines(self):
        result = WeikeDocumentMixin._normalize_dom_text("a\n\n\n\nb")
        assert "\n\n\n" not in result

    def test_normalize_dom_text_multi_spaces(self):
        result = WeikeDocumentMixin._normalize_dom_text("a    b")
        assert "    " not in result

    # ── _extract_dom_field ──

    def test_extract_dom_field_match(self):
        result = WeikeDocumentMixin._extract_dom_field(
            text="审理法院：广州市天河区人民法院",
            patterns=(r"审理法院[:：]\s*([^\n]+)",)
        )
        assert "广州市天河区人民法院" in result

    def test_extract_dom_field_no_match(self):
        result = WeikeDocumentMixin._extract_dom_field(
            text="没有法院信息",
            patterns=(r"审理法院[:：]\s*([^\n]+)",)
        )
        assert result == ""

    def test_extract_dom_field_multiple_patterns(self):
        result = WeikeDocumentMixin._extract_dom_field(
            text="案号：（2025）粤01民初123号",
            patterns=(
                r"审理法院[:：]\s*([^\n]+)",
                r"案号[:：]\s*([^\n]+)",
            )
        )
        assert "2025" in result

    # ── _build_dom_digest ──

    def test_build_dom_digest_short(self):
        result = WeikeDocumentMixin._build_dom_digest("短文本")
        assert result == "短文本"

    def test_build_dom_digest_long(self):
        text = "x" * 300
        result = WeikeDocumentMixin._build_dom_digest(text)
        assert len(result) <= 225

    def test_build_dom_digest_empty(self):
        assert WeikeDocumentMixin._build_dom_digest("") == ""

    # ── _summarize_meta_payload ──

    def test_summarize_meta_payload_full(self):
        payload = {
            "currentDoc": {
                "title": "测试标题",
                "additionalFields": {
                    "courtText": "广州法院",
                    "documentNumber": "粤01民初123号",
                    "judgmentDate": "2025-01-15",
                }
            }
        }
        result = WeikeDocumentMixin._summarize_meta_payload(payload)
        assert result["title"] == "测试标题"
        assert result["court_text"] == "广州法院"

    def test_summarize_meta_payload_none(self):
        result = WeikeDocumentMixin._summarize_meta_payload(None)
        assert result["title"] == ""

    # ── _summarize_html_payload ──

    def test_summarize_html_payload_with_content(self):
        result = WeikeDocumentMixin._summarize_html_payload({"content": "hello"})
        assert result["content_length"] == 5
        assert result["has_content"] is True

    def test_summarize_html_payload_empty(self):
        result = WeikeDocumentMixin._summarize_html_payload(None)
        assert result["has_content"] is False


class TestWeikeSearchMixinHelpers:
    """WeikeSearchMixin 静态方法测试。"""

    # ── _parse_detail_url ──

    def test_parse_detail_url_valid(self):
        url = "https://law.wkinfo.com.cn/judgment-documents/detail/abc123?searchId=sid&module=mod"
        result = WeikeSearchMixin._parse_detail_url(url)
        assert result is not None
        assert result.doc_id_raw == "abc123"
        assert result.search_id == "sid"
        assert result.module == "mod"

    def test_parse_detail_url_encoded(self):
        url = "https://law.wkinfo.com.cn/judgment-documents/detail/abc123?module=mod"
        result = WeikeSearchMixin._parse_detail_url(url)
        assert result is not None
        assert result.doc_id_raw == "abc123"
        assert result.module == "mod"

    def test_parse_detail_url_no_match(self):
        result = WeikeSearchMixin._parse_detail_url("https://example.com/page")
        assert result is None

    def test_parse_detail_url_no_query(self):
        url = "https://law.wkinfo.com.cn/judgment-documents/detail/abc123"
        result = WeikeSearchMixin._parse_detail_url(url)
        assert result is not None
        assert result.search_id == ""
        assert result.module == ""

    # ── _compact_error_message ──

    def test_compact_error_message_short(self):
        result = WeikeSearchMixin._compact_error_message(RuntimeError("error"))
        assert result == "error"

    def test_compact_error_message_long(self):
        result = WeikeSearchMixin._compact_error_message(RuntimeError("x" * 300), max_len=50)
        assert len(result) <= 50

    # ── _is_search_api_degraded ──

    def test_is_search_api_degraded_not(self):
        session = MagicMock()
        session.search_api_degraded_until_epoch = 0.0
        mixin = WeikeSearchMixin.__new__(WeikeSearchMixin)
        assert mixin._is_search_api_degraded(session=session) is False

    def test_is_search_api_degraded_expired(self):
        session = MagicMock()
        session.search_api_degraded_until_epoch = 1.0  # in the past
        mixin = WeikeSearchMixin.__new__(WeikeSearchMixin)
        assert mixin._is_search_api_degraded(session=session) is False

    # ── _search_api_degraded_wait_seconds ──

    def test_search_api_degraded_wait_seconds_zero(self):
        session = MagicMock()
        session.search_api_degraded_until_epoch = 0.0
        result = WeikeSearchMixin._search_api_degraded_wait_seconds(session=session)
        assert result == 0

    # ── _reset_search_api_health ──

    def test_reset_search_api_health(self):
        session = MagicMock()
        session.search_api_empty_streak = 5
        session.search_api_error_streak = 3
        session.search_api_degraded_until_epoch = 999.0
        WeikeSearchMixin._reset_search_api_health(session=session)
        assert session.search_api_empty_streak == 0
        assert session.search_api_error_streak == 0
        assert session.search_api_degraded_until_epoch == 0.0

    # ── _resolve_search_api_degrade_streak_threshold ──

    def test_resolve_streak_threshold_default(self):
        mixin = WeikeSearchMixin.__new__(WeikeSearchMixin)
        assert mixin._resolve_search_api_degrade_streak_threshold() >= 1

    # ── _resolve_search_api_degrade_cooldown_seconds ──

    def test_resolve_cooldown_default(self):
        mixin = WeikeSearchMixin.__new__(WeikeSearchMixin)
        assert mixin._resolve_search_api_degrade_cooldown_seconds() >= 30
