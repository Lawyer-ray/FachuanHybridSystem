"""
Tests for apps.message_hub.services — 消息中心服务
"""

from __future__ import annotations

import pytest


class TestMessageHubModules:
    """消息中心模块可导入性测试"""

    def test_base_importable(self) -> None:
        from apps.message_hub.services.base import MessageFetcher

        assert MessageFetcher is not None

    def test_inbox_query_importable(self) -> None:
        from apps.message_hub.services.inbox_query import get_base_queryset

        assert callable(get_base_queryset)

    def test_court_fetcher_importable(self) -> None:
        from apps.message_hub.services.court.court_fetcher import CourtInboxFetcher

        assert CourtInboxFetcher is not None

    def test_court_schedule_fetcher_importable(self) -> None:
        from apps.message_hub.services.court.court_schedule_fetcher import CourtScheduleFetcher

        assert CourtScheduleFetcher is not None

    def test_imap_fetcher_importable(self) -> None:
        from apps.message_hub.services.imap.imap_fetcher import ImapFetcher

        assert ImapFetcher is not None

# ---------------------------------------------------------------------------
# IMAP helper functions
# ---------------------------------------------------------------------------

class TestImapHelpers:
    def test_decode_header_value_none(self):
        from apps.message_hub.services.imap.imap_fetcher import _decode_header_value
        assert _decode_header_value(None) == ""

    def test_decode_header_value_plain(self):
        from apps.message_hub.services.imap.imap_fetcher import _decode_header_value
        assert _decode_header_value("Hello") == "Hello"

    def test_extract_imap_host_from_url(self):
        from apps.message_hub.services.imap.imap_fetcher import _extract_imap_host
        assert _extract_imap_host("imap.example.com") == "imap.example.com"

    def test_extract_imap_host_from_full_url(self):
        from apps.message_hub.services.imap.imap_fetcher import _extract_imap_host
        assert _extract_imap_host("https://mail.example.com/path") == "mail.example.com"

    def test_extract_imap_host_empty(self):
        from apps.message_hub.services.imap.imap_fetcher import _extract_imap_host
        assert _extract_imap_host("") == ""

    def test_build_imap_host_candidates(self):
        from apps.message_hub.services.imap.imap_fetcher import _build_imap_host_candidates
        candidates = _build_imap_host_candidates("imap.example.com", "example.com")
        assert len(candidates) >= 1

    def test_looks_like_valid_host(self):
        from apps.message_hub.services.imap.imap_fetcher import _looks_like_valid_host
        assert _looks_like_valid_host("imap.example.com") is True
        assert _looks_like_valid_host("") is False
        assert _looks_like_valid_host("http://bad") is False
        assert _looks_like_valid_host(".bad.") is False

    def test_parse_filter_lines(self):
        from apps.message_hub.services.imap.imap_fetcher import _parse_filter_lines
        assert _parse_filter_lines("a\nb\nc") == ["a", "b", "c"]
        assert _parse_filter_lines("\n\n") == []

    def test_parse_date_valid(self):
        from apps.message_hub.services.imap.imap_fetcher import _parse_date
        result = _parse_date("Mon, 15 Jan 2026 09:00:00 +0800")
        assert result is not None

    def test_parse_date_invalid(self):
        from apps.message_hub.services.imap.imap_fetcher import _parse_date
        assert _parse_date("not a date") is None


# ---------------------------------------------------------------------------
# Court fetcher helper functions
# ---------------------------------------------------------------------------

class TestCourtFetcherHelpers:
    def test_build_subject(self):
        from apps.message_hub.services.court.court_fetcher import _build_subject
        record = {"ah": "2024民初001", "wsmc": "判决书"}
        assert _build_subject(record) == "2024民初001 - 判决书"

    def test_build_subject_no_ah(self):
        from apps.message_hub.services.court.court_fetcher import _build_subject
        record = {"ah": "", "wsmc": "判决书"}
        assert _build_subject(record) == "判决书"

    def test_build_subject_empty(self):
        from apps.message_hub.services.court.court_fetcher import _build_subject
        assert _build_subject({}) == "(无主题)"

    def test_build_body(self):
        from apps.message_hub.services.court.court_fetcher import _build_body
        record = {"ah": "2024民初001", "fymc": "北京法院", "wsmc": "判决书"}
        body = _build_body(record)
        assert "2024民初001" in body
        assert "北京法院" in body

    def test_parse_datetime_valid(self):
        from apps.message_hub.services.court.court_fetcher import _parse_datetime
        result = _parse_datetime("2026-01-15 09:00:00")
        assert result is not None

    def test_parse_datetime_invalid(self):
        from apps.message_hub.services.court.court_fetcher import _parse_datetime
        result = _parse_datetime("not a date")
        assert result is not None  # returns timezone.now()

