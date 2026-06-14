"""legal_research/services/sources/weike/document.py 单元测试 — 纯函数部分。"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

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


# ── html_to_text ──────────────────────────────────────────────────────


class TestHtmlToText:
    def test_strips_tags(self) -> None:
        assert html_to_text("<p>Hello <b>world</b></p>") == "Hello world"

    def test_br_to_newline(self) -> None:
        result = html_to_text("line1<br>line2")
        assert "line1\nline2" in result

    def test_script_removed(self) -> None:
        result = html_to_text("<p>a</p><script>alert(1)</script><p>b</p>")
        assert "alert" not in result
        assert "a" in result
        assert "b" in result

    def test_style_removed(self) -> None:
        result = html_to_text("<style>.x{color:red}</style><p>hi</p>")
        assert "color" not in result
        assert "hi" in result

    def test_html_entities(self) -> None:
        result = html_to_text("<p>&amp; &lt; &gt;</p>")
        assert "&" in result

    def test_multiple_newlines_collapsed(self) -> None:
        result = html_to_text("<p>a</p>\n\n\n<p>b</p>")
        assert "\n\n\n" not in result


# ── normalize_dom_text ─────────────────────────────────────────────────


class TestNormalizeDomText:
    def test_nbsp_replaced(self) -> None:
        assert normalize_dom_text("a\xa0b") == "a b"

    def test_extra_spaces(self) -> None:
        assert normalize_dom_text("a  b  c") == "a b c"

    def test_empty(self) -> None:
        assert normalize_dom_text("") == ""

    def test_none_coerced(self) -> None:
        assert normalize_dom_text("") == ""


# ── extract_dom_field ─────────────────────────────────────────────────


class TestExtractDomField:
    def test_match_found(self) -> None:
        result = extract_dom_field(
            text="审理法院: 北京市高级人民法院",
            patterns=(r"审理法院[:：]\s*([^\n]+)",),
        )
        assert "北京市" in result

    def test_no_match(self) -> None:
        result = extract_dom_field(
            text="nothing here",
            patterns=(r"审理法院[:：]\s*([^\n]+)",),
        )
        assert result == ""

    def test_multiple_patterns(self) -> None:
        result = extract_dom_field(
            text="案号: (2024)京01民终123号",
            patterns=(r"案号[:：]\s*([^\n]+)", r"文号[:：]\s*([^\n]+)"),
        )
        assert "2024" in result

    def test_whitespace_normalized(self) -> None:
        result = extract_dom_field(
            text="title:  Hello   World",
            patterns=(r"title:\s*(.+)",),
        )
        assert result == "Hello World"


# ── build_dom_digest ──────────────────────────────────────────────────


class TestBuildDomDigest:
    def test_empty(self) -> None:
        assert build_dom_digest("") == ""

    def test_short_text(self) -> None:
        text = "short text"
        assert build_dom_digest(text) == text

    def test_long_text_truncated(self) -> None:
        text = "a" * 300
        result = build_dom_digest(text)
        assert result.endswith("...")
        assert len(result) == 223  # 220 + "..."

    def test_whitespace_compacted(self) -> None:
        text = "a   b\n\nc"
        assert "a b" in build_dom_digest(text)


# ── detail_doc_id_candidates ──────────────────────────────────────────


class TestDetailDocIdCandidates:
    def test_both_ids(self) -> None:
        item = WeikeSearchItem(
            doc_id_raw="raw1", doc_id_unquoted="uq1", detail_url="", title_hint="", search_id="", module=""
        )
        result = detail_doc_id_candidates(item)
        assert "uq1" in result
        assert "raw1" in result

    def test_deduplication(self) -> None:
        item = WeikeSearchItem(
            doc_id_raw="same", doc_id_unquoted="same", detail_url="", title_hint="", search_id="", module=""
        )
        result = detail_doc_id_candidates(item)
        assert result.count("same") == 1

    def test_empty_values_skipped(self) -> None:
        item = WeikeSearchItem(
            doc_id_raw="", doc_id_unquoted="", detail_url="", title_hint="", search_id="", module=""
        )
        assert detail_doc_id_candidates(item) == []


# ── is_session_restricted_response ────────────────────────────────────


class TestIsSessionRestrictedResponse:
    def test_restricted_code(self) -> None:
        assert is_session_restricted_response(status=200, payload={"code": "C_001_009"}) is True

    def test_not_restricted(self) -> None:
        assert is_session_restricted_response(status=200, payload={"code": "OK"}) is False

    def test_400_with_restricted_code(self) -> None:
        assert is_session_restricted_response(status=400, payload={"code": "C_001_009"}) is True

    def test_none_payload(self) -> None:
        assert is_session_restricted_response(status=200, payload=None) is False

    def test_400_with_other_code(self) -> None:
        assert is_session_restricted_response(status=400, payload={"code": "OTHER"}) is False


# ── compact_error ─────────────────────────────────────────────────────


class TestCompactError:
    def test_short_error(self) -> None:
        assert compact_error(RuntimeError("hi")) == "hi"

    def test_long_error_truncated(self) -> None:
        msg = "x" * 200
        result = compact_error(RuntimeError(msg), max_len=50)
        assert len(result) == 50
        assert result.endswith("...")

    def test_empty_message(self) -> None:
        result = compact_error(RuntimeError(""))
        assert result == "RuntimeError"


# ── summarize_meta_payload ────────────────────────────────────────────


class TestSummarizeMetaPayload:
    def test_full_payload(self) -> None:
        payload = {
            "currentDoc": {
                "title": "Test",
                "additionalFields": {
                    "courtText": "Court",
                    "documentNumber": "Doc#1",
                    "judgmentDate": "2024-01-01",
                },
            }
        }
        result = summarize_meta_payload(payload)
        assert result["title"] == "Test"
        assert result["court_text"] == "Court"

    def test_none_payload(self) -> None:
        result = summarize_meta_payload(None)
        assert result["title"] == ""


# ── summarize_html_payload ────────────────────────────────────────────


class TestSummarizeHtmlPayload:
    def test_with_content(self) -> None:
        result = summarize_html_payload({"content": "hello"})
        assert result["content_length"] == 5
        assert result["has_content"] is True

    def test_none(self) -> None:
        result = summarize_html_payload(None)
        assert result["has_content"] is False


# ── build_download_filename ───────────────────────────────────────────


class TestBuildDownloadFilename:
    def test_with_title(self) -> None:
        detail = WeikeCaseDetail(
            doc_id_raw="raw", doc_id_unquoted="uq", detail_url="", search_id="",
            module="", title="Test Case", court_text="", document_number="",
            judgment_date="", case_digest="", content_text="", raw_meta={},
        )
        result = build_download_filename(detail)
        assert "Test Case" in result
        assert result.endswith(".pdf")

    def test_empty_title_uses_fallback(self) -> None:
        detail = WeikeCaseDetail(
            doc_id_raw="raw", doc_id_unquoted="uq", detail_url="", search_id="",
            module="", title="", court_text="", document_number="",
            judgment_date="", case_digest="", content_text="", raw_meta={},
        )
        result = build_download_filename(detail)
        assert "uq" in result

    def test_special_chars_replaced(self) -> None:
        detail = WeikeCaseDetail(
            doc_id_raw="", doc_id_unquoted="", detail_url="", search_id="",
            module="", title='A/B:C*D?"E<F>G', court_text="", document_number="",
            judgment_date="", case_digest="", content_text="", raw_meta={},
        )
        result = build_download_filename(detail)
        assert "/" not in result.split("_下载")[0]
