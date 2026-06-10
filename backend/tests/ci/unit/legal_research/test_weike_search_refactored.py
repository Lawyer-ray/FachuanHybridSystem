"""Tests for weike/search module-level pure functions."""

from __future__ import annotations

from apps.legal_research.services.sources.weike.search import compact_error_message, parse_detail_url


class TestParseDetailUrl:
    def test_valid_url(self) -> None:
        url = "https://law.wkinfo.com.cn/judgment-documents/detail/abc123?searchId=s1&module=law.case"
        result = parse_detail_url(url)
        assert result is not None
        assert result.doc_id_raw == "abc123"
        assert result.doc_id_unquoted == "abc123"
        assert result.search_id == "s1"
        assert result.module == "law.case"

    def test_url_encoded_id(self) -> None:
        url = "https://law.wkinfo.com.cn/judgment-documents/detail/%22abc%22"
        result = parse_detail_url(url)
        assert result is not None
        assert result.doc_id_unquoted == '"abc"'

    def test_no_detail_path(self) -> None:
        result = parse_detail_url("https://example.com/other/path")
        assert result is None

    def test_empty_url(self) -> None:
        assert parse_detail_url("") is None

    def test_no_query_params(self) -> None:
        url = "https://law.wkinfo.com.cn/judgment-documents/detail/doc999"
        result = parse_detail_url(url)
        assert result is not None
        assert result.search_id == ""
        assert result.module == ""

    def test_detail_url_built(self) -> None:
        url = "/judgment-documents/detail/test123"
        result = parse_detail_url(url)
        assert result is not None
        assert "law.wkinfo.com.cn" in result.detail_url


class TestCompactErrorMessage:
    def test_short(self) -> None:
        result = compact_error_message(ValueError("short error"), max_len=50)
        assert result == "short error"

    def test_long_truncated(self) -> None:
        result = compact_error_message(ValueError("x" * 300), max_len=50)
        assert len(result) == 50
        assert result.endswith("...")

    def test_empty(self) -> None:
        result = compact_error_message(Exception(""), max_len=50)
        assert len(result) > 0
