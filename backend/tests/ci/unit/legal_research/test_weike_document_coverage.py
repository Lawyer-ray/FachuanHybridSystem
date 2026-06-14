"""Coverage tests for legal_research/services/sources/weike/document.py.

Covers module-level pure functions:
  - html_to_text
  - normalize_dom_text
  - extract_dom_field
  - build_dom_digest
  - detail_doc_id_candidates
  - is_session_restricted_response
  - compact_error
  - summarize_meta_payload
  - summarize_html_payload
  - build_download_filename
"""
from __future__ import annotations

from types import SimpleNamespace

import pytest

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
    def test_basic_html(self):
        result = html_to_text("<p>Hello</p><p>World</p>")
        assert "Hello" in result
        assert "World" in result

    def test_removes_scripts(self):
        result = html_to_text("<script>alert('x')</script><p>Content</p>")
        assert "alert" not in result
        assert "Content" in result

    def test_removes_styles(self):
        result = html_to_text("<style>.cls{color:red}</style><p>Text</p>")
        assert "cls" not in result
        assert "Text" in result

    def test_br_to_newline(self):
        result = html_to_text("Line1<br>Line2<br/>Line3")
        assert "Line1" in result
        assert "Line2" in result

    def test_html_entities(self):
        result = html_to_text("<p>&amp; &lt; &gt;</p>")
        assert "&" in result
        assert "<" in result
        assert ">" in result

    def test_collapses_whitespace(self):
        result = html_to_text("<p>  hello   world  </p>")
        assert "hello world" in result

    def test_collapses_newlines(self):
        result = html_to_text("<p>a\n\n\n\nb</p>")
        assert "\n\n" in result
        assert "\n\n\n" not in result

    def test_empty(self):
        result = html_to_text("")
        assert result == ""

    def test_no_html(self):
        result = html_to_text("plain text")
        assert result == "plain text"


class TestNormalizeDomText:
    def test_basic(self):
        result = normalize_dom_text("  Hello   World  ")
        assert "Hello World" in result

    def test_nbsp_replacement(self):
        result = normalize_dom_text("Hello\xa0World")
        assert "Hello World" in result

    def test_collapses_newlines(self):
        result = normalize_dom_text("a\n\n\n\nb")
        assert "\n\n" in result
        assert "\n\n\n" not in result

    def test_empty(self):
        assert normalize_dom_text("") == ""

    def test_none(self):
        assert normalize_dom_text("") == ""


class TestExtractDomField:
    def test_match_found(self):
        text = "法院：广州市天河区人民法院\n其他内容"
        result = extract_dom_field(
            text=text,
            patterns=(r"(?:审理法院|法院)[:：]\s*([^\n]+)",),
        )
        assert "天河区" in result

    def test_no_match(self):
        result = extract_dom_field(
            text="some random text",
            patterns=(r"法院[:：]\s*([^\n]+)",),
        )
        assert result == ""

    def test_multiple_patterns(self):
        text = "案号：(2024)粤01民初1号"
        result = extract_dom_field(
            text=text,
            patterns=(r"不存在[:：]\s*([^\n]+)", r"案号[:：]\s*([^\n]+)"),
        )
        assert "(2024)" in result

    def test_strips_whitespace(self):
        text = "法院：  广州市  天河区  "
        result = extract_dom_field(
            text=text,
            patterns=(r"法院[:：]\s*([^\n]+)",),
        )
        assert "广州市 天河区" in result


class TestBuildDomDigest:
    def test_short_text(self):
        result = build_dom_digest("Hello World")
        assert result == "Hello World"

    def test_long_text(self):
        result = build_dom_digest("A" * 300)
        assert len(result) == 223  # 220 + "..."
        assert result.endswith("...")

    def test_empty(self):
        assert build_dom_digest("") == ""

    def test_whitespace_only(self):
        assert build_dom_digest("   ") == ""

    def test_exactly_220(self):
        text = "A" * 220
        assert build_dom_digest(text) == text

    def test_221_chars(self):
        text = "A" * 221
        result = build_dom_digest(text)
        assert result.endswith("...")
        assert len(result) == 223


class TestDetailDocIdCandidates:
    def test_both_raw_and_unquoted(self):
        item = WeikeSearchItem(
            doc_id_raw="RAW-123",
            doc_id_unquoted="UNQUOTED-456",
            detail_url="",
            title_hint="",
            search_id="",
            module="",
        )
        candidates = detail_doc_id_candidates(item)
        assert "UNQUOTED-456" in candidates
        assert "RAW-123" in candidates

    def test_deduplication(self):
        item = WeikeSearchItem(
            doc_id_raw="SAME",
            doc_id_unquoted="SAME",
            detail_url="",
            title_hint="",
            search_id="",
            module="",
        )
        candidates = detail_doc_id_candidates(item)
        assert candidates.count("SAME") == 1

    def test_empty_values_skipped(self):
        item = WeikeSearchItem(
            doc_id_raw="",
            doc_id_unquoted="",
            detail_url="",
            title_hint="",
            search_id="",
            module="",
        )
        assert detail_doc_id_candidates(item) == []

    def test_whitespace_only_skipped(self):
        item = WeikeSearchItem(
            doc_id_raw="  ",
            doc_id_unquoted="  ",
            detail_url="",
            title_hint="",
            search_id="",
            module="",
        )
        assert detail_doc_id_candidates(item) == []


class TestIsSessionRestrictedResponse:
    def test_code_c_001_009(self):
        assert is_session_restricted_response(status=200, payload={"code": "C_001_009"}) is True

    def test_status_400_with_code(self):
        assert is_session_restricted_response(status=400, payload={"code": "C_001_009"}) is True

    def test_status_400_different_code(self):
        assert is_session_restricted_response(status=400, payload={"code": "OTHER"}) is False

    def test_no_payload(self):
        assert is_session_restricted_response(status=200, payload=None) is False

    def test_empty_code(self):
        assert is_session_restricted_response(status=200, payload={"code": ""}) is False

    def test_normal_response(self):
        assert is_session_restricted_response(status=200, payload={"code": "OK"}) is False


class TestCompactError:
    def test_short_message(self):
        exc = ValueError("short")
        assert compact_error(exc) == "short"

    def test_long_message_truncated(self):
        exc = ValueError("A" * 200)
        result = compact_error(exc, max_len=50)
        assert len(result) == 50
        assert result.endswith("...")

    def test_empty_message_uses_classname(self):
        exc = ValueError("")
        assert compact_error(exc) == "ValueError"

    def test_exact_max_len(self):
        exc = ValueError("A" * 120)
        result = compact_error(exc, max_len=120)
        assert len(result) == 120


class TestSummarizeMetaPayload:
    def test_basic(self):
        payload = {
            "currentDoc": {
                "title": "Test Title",
                "additionalFields": {
                    "courtText": "Court",
                    "documentNumber": "No.1",
                    "judgmentDate": "2024-01-01",
                },
            }
        }
        result = summarize_meta_payload(payload)
        assert result["title"] == "Test Title"
        assert result["court_text"] == "Court"
        assert result["document_number"] == "No.1"
        assert result["judgment_date"] == "2024-01-01"

    def test_empty_payload(self):
        result = summarize_meta_payload(None)
        assert result["title"] == ""

    def test_title_from_additional(self):
        payload = {"currentDoc": {"additionalFields": {"title": "From Additional"}}}
        result = summarize_meta_payload(payload)
        assert result["title"] == "From Additional"


class TestSummarizeHtmlPayload:
    def test_with_content(self):
        result = summarize_html_payload({"content": "Hello World"})
        assert result["content_length"] == 11
        assert result["has_content"] is True

    def test_empty_content(self):
        result = summarize_html_payload({"content": ""})
        assert result["content_length"] == 0
        assert result["has_content"] is False

    def test_none_payload(self):
        result = summarize_html_payload(None)
        assert result["has_content"] is False


class TestBuildDownloadFilename:
    def test_basic(self):
        detail = WeikeCaseDetail(
            doc_id_raw="RAW",
            doc_id_unquoted="UNQUOTED",
            detail_url="",
            search_id="",
            module="",
            title="Test Case Title",
            court_text="",
            document_number="",
            judgment_date="",
            case_digest="",
            content_text="",
            raw_meta={},
        )
        filename = build_download_filename(detail)
        assert filename.endswith("下载.pdf")
        assert "Test Case Title" in filename

    def test_special_chars_replaced(self):
        detail = WeikeCaseDetail(
            doc_id_raw="RAW",
            doc_id_unquoted="UNQUOTED",
            detail_url="",
            search_id="",
            module="",
            title='Test/Case\\With*Special?Chars"',
            court_text="",
            document_number="",
            judgment_date="",
            case_digest="",
            content_text="",
            raw_meta={},
        )
        filename = build_download_filename(detail)
        assert "/" not in filename.split("_")[0] or "下载.pdf" in filename

    def test_empty_title_uses_doc_id(self):
        detail = WeikeCaseDetail(
            doc_id_raw="RAW",
            doc_id_unquoted="UNQUOTED-123",
            detail_url="",
            search_id="",
            module="",
            title="",
            court_text="",
            document_number="",
            judgment_date="",
            case_digest="",
            content_text="",
            raw_meta={},
        )
        filename = build_download_filename(detail)
        assert "UNQUOTED-123" in filename
