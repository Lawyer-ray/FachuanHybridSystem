"""Tests for weike/document module-level pure functions."""

from __future__ import annotations

from datetime import datetime

from apps.legal_research.services.sources.weike.document import (
    build_dom_digest,
    build_download_filename,
    compact_error,
    detail_doc_id_candidates,
    extract_dom_field,
    html_to_text,
    is_session_restricted_response,
    normalize_dom_text,
    summarize_html_payload,
    summarize_meta_payload,
)
from apps.legal_research.services.sources.weike.types import WeikeCaseDetail, WeikeSearchItem


class TestHtmlToText:
    def test_strips_tags(self) -> None:
        result = html_to_text("<p>Hello <b>World</b></p>")
        assert "<p>" not in result
        assert "Hello" in result
        assert "World" in result

    def test_removes_script(self) -> None:
        result = html_to_text("before<script>alert('xss')</script>after")
        assert "alert" not in result
        assert "before" in result
        assert "after" in result

    def test_removes_style(self) -> None:
        result = html_to_text("text<style>.x{}</style>more")
        assert ".x" not in result

    def test_br_to_newline(self) -> None:
        result = html_to_text("line1<br/>line2")
        assert "\n" in result

    def test_empty(self) -> None:
        assert html_to_text("") == ""

    def test_html_entities(self) -> None:
        result = html_to_text("&amp; &lt;test&gt;")
        assert "&" in result
        assert "<test>" in result


class TestNormalizeDomText:
    def test_replaces_nbsp(self) -> None:
        result = normalize_dom_text("hello\xa0world")
        assert "\xa0" not in result

    def test_collapse_spaces(self) -> None:
        result = normalize_dom_text("a   b")
        assert "   " not in result

    def test_collapse_newlines(self) -> None:
        result = normalize_dom_text("a\n\n\n\nb")
        assert "\n\n\n" not in result

    def test_empty(self) -> None:
        assert normalize_dom_text("") == ""

    def test_none_input(self) -> None:
        assert normalize_dom_text(None) == ""  # type: ignore[arg-type]


class TestExtractDomField:
    def test_basic_match(self) -> None:
        result = extract_dom_field(text="法院：北京市朝阳区人民法院", patterns=(r"法院[:：]\s*(.+)",))
        assert "北京市" in result

    def test_no_match(self) -> None:
        result = extract_dom_field(text="无关文本", patterns=(r"法院[:：]\s*(.+)",))
        assert result == ""

    def test_multiple_patterns(self) -> None:
        result = extract_dom_field(
            text="案号：（2024）京0105民初123号",
            patterns=(r"无匹配", r"案号[:：]\s*(.+)"),
        )
        assert "123号" in result

    def test_strips_whitespace(self) -> None:
        result = extract_dom_field(text="法院:  北京  法院", patterns=(r"法院[:：]\s*(.+)",))
        assert "  " not in result


class TestBuildDomDigest:
    def test_short_text(self) -> None:
        result = build_dom_digest("短文本")
        assert result == "短文本"

    def test_long_text_truncated(self) -> None:
        text = "a" * 300
        result = build_dom_digest(text)
        assert len(result) == 223  # 220 + "..."

    def test_empty(self) -> None:
        assert build_dom_digest("") == ""

    def test_whitespace_only(self) -> None:
        assert build_dom_digest("   ") == ""


class TestDetailDocIdCandidates:
    def test_basic(self) -> None:
        item = WeikeSearchItem(
            doc_id_raw="raw123", doc_id_unquoted="unq456",
            detail_url="", title_hint="", search_id="", module="",
        )
        result = detail_doc_id_candidates(item)
        assert result == ["raw123", "unq456"]

    def test_deduplication(self) -> None:
        item = WeikeSearchItem(
            doc_id_raw="same", doc_id_unquoted="same",
            detail_url="", title_hint="", search_id="", module="",
        )
        result = detail_doc_id_candidates(item)
        assert result == ["same"]

    def test_empty_values(self) -> None:
        item = WeikeSearchItem(
            doc_id_raw="", doc_id_unquoted="",
            detail_url="", title_hint="", search_id="", module="",
        )
        result = detail_doc_id_candidates(item)
        assert result == []


class TestIsSessionRestrictedResponse:
    def test_restrict_code(self) -> None:
        assert is_session_restricted_response(status=200, payload={"code": "C_001_009"}) is True

    def test_status_400_with_code(self) -> None:
        assert is_session_restricted_response(status=400, payload={"code": "C_001_009"}) is True

    def test_normal_response(self) -> None:
        assert is_session_restricted_response(status=200, payload={"code": "OK"}) is False

    def test_none_payload(self) -> None:
        assert is_session_restricted_response(status=200, payload=None) is False


class TestCompactError:
    def test_short_message(self) -> None:
        result = compact_error(ValueError("short"), max_len=50)
        assert result == "short"

    def test_long_truncated(self) -> None:
        result = compact_error(ValueError("x" * 200), max_len=50)
        assert len(result) == 50
        assert result.endswith("...")

    def test_empty_exception(self) -> None:
        result = compact_error(Exception(""), max_len=50)
        assert len(result) > 0


class TestSummarizeMetaPayload:
    def test_basic(self) -> None:
        payload = {
            "currentDoc": {
                "title": "案例标题",
                "additionalFields": {
                    "courtText": "北京法院",
                    "documentNumber": "（2024）京民初1号",
                },
            }
        }
        result = summarize_meta_payload(payload)
        assert result["title"] == "案例标题"
        assert result["court_text"] == "北京法院"

    def test_none_payload(self) -> None:
        result = summarize_meta_payload(None)
        assert result["title"] == ""


class TestSummarizeHtmlPayload:
    def test_with_content(self) -> None:
        result = summarize_html_payload({"content": "hello"})
        assert result["has_content"] is True
        assert result["content_length"] == 5

    def test_empty(self) -> None:
        result = summarize_html_payload(None)
        assert result["has_content"] is False


class TestBuildDownloadFilename:
    def test_basic(self) -> None:
        detail = WeikeCaseDetail(
            doc_id_raw="123", doc_id_unquoted="123", detail_url="",
            search_id="", module="", title="买卖合同纠纷案",
            court_text="", document_number="", judgment_date="",
            case_digest="", content_text="", raw_meta={},
        )
        result = build_download_filename(detail)
        assert "买卖合同纠纷案" in result
        assert datetime.now().strftime("%Y%m%d") in result

    def test_empty_title_fallback(self) -> None:
        detail = WeikeCaseDetail(
            doc_id_raw="123", doc_id_unquoted="abc123", detail_url="",
            search_id="", module="", title="",
            court_text="", document_number="", judgment_date="",
            case_digest="", content_text="", raw_meta={},
        )
        result = build_download_filename(detail)
        assert "abc123" in result
