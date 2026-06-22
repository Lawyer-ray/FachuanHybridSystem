"""IMAP fetcher tests with mocked imaplib."""

from __future__ import annotations

import email
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

try:
    from plugins import has_message_hub_plugin
    _HAS_MH = has_message_hub_plugin()
except ImportError:
    _HAS_MH = False

pytestmark = pytest.mark.skipif(not _HAS_MH, reason="message_hub plugin not installed")

if _HAS_MH:
    from plugins.message_hub.services.imap.imap_fetcher import (
        ImapFetcher,
        _build_imap_host_candidates,
        _decode_header_value,
        _extract_body,
        _extract_imap_host,
        _looks_like_valid_host,
        _parse_date,
        _parse_filter_lines,
        _sender_allowed,

)

class TestDecodeHeaderValue:
    def test_decode_plain_ascii(self):
        assert _decode_header_value("Hello") == "Hello"

    def test_decode_none(self):
        assert _decode_header_value(None) == ""

    def test_decode_empty(self):
        assert _decode_header_value("") == ""

class TestExtractBody:
    def test_extract_body_plain_text(self):
        msg = email.message_from_string("Content-Type: text/plain\n\nHello World")
        text, html = _extract_body(msg)
        assert "Hello" in text
        assert html == ""

    def test_extract_body_html(self):
        msg = email.message_from_string("Content-Type: text/html\n\n<p>Hello</p>")
        text, html = _extract_body(msg)
        assert text == ""
        assert "<p>" in html

class TestImapHostExtraction:
    def test_extract_imap_host_from_url(self):
        assert _extract_imap_host("imap://mail.example.com") == "mail.example.com"

    def test_extract_imap_host_from_hostname(self):
        assert _extract_imap_host("mail.example.com") == "mail.example.com"

    def test_extract_imap_host_empty(self):
        assert _extract_imap_host("") == ""

    def test_build_imap_host_candidates(self):
        candidates = _build_imap_host_candidates("imap.example.com", "example.com")
        assert isinstance(candidates, list)
        assert len(candidates) > 0

    def test_build_imap_host_candidates_empty(self):
        candidates = _build_imap_host_candidates("", "")
        assert candidates == []

class TestLooksLikeValidHost:
    def test_valid_host(self):
        assert _looks_like_valid_host("imap.example.com") is True

    def test_invalid_host_with_scheme(self):
        assert _looks_like_valid_host("https://example.com") is False

    def test_invalid_host_with_slash(self):
        assert _looks_like_valid_host("example.com/path") is False

    def test_invalid_host_empty(self):
        assert _looks_like_valid_host("") is False

    def test_invalid_host_dot_start(self):
        assert _looks_like_valid_host(".example.com") is False

class TestParseDate:
    def test_parse_date_valid(self):
        dt = _parse_date("Mon, 1 Jan 2024 12:00:00 +0800")
        assert dt is not None
        assert dt.year == 2024

    def test_parse_date_invalid(self):
        assert _parse_date("not a date") is None

class TestSenderFilter:
    def test_sender_allowed_no_filter(self):
        source = MagicMock()
        source.sender_whitelist = ""
        source.sender_blacklist = ""
        assert _sender_allowed("test@example.com", source) is True

    def test_sender_allowed_whitelist_match(self):
        source = MagicMock()
        source.sender_whitelist = "example.com\nother.com"
        source.sender_blacklist = ""
        assert _sender_allowed("user@example.com", source) is True

    def test_sender_allowed_whitelist_no_match(self):
        source = MagicMock()
        source.sender_whitelist = "allowed.com"
        source.sender_blacklist = ""
        assert _sender_allowed("user@blocked.com", source) is False

    def test_sender_allowed_blacklist(self):
        source = MagicMock()
        source.sender_whitelist = ""
        source.sender_blacklist = "spam.com"
        assert _sender_allowed("user@spam.com", source) is False

    def test_parse_filter_lines(self):
        result = _parse_filter_lines("line1\nline2\n\nline3")
        assert result == ["line1", "line2", "line3"]

class TestImapFetcherConnect:
    @patch("plugins.message_hub.services.imap.imap_fetcher.imaplib.IMAP4_SSL")
    def test_connect_success(self, mock_imap):
        mock_conn = MagicMock()
        mock_imap.return_value = mock_conn

        source = MagicMock()
        source.imap_account = "user@example.com"
        source.credential.account = "user@example.com"
        source.credential.password = "pass"
        source.imap_host = "imap.example.com"
        source.credential.url = ""
        source.credential.site_name = ""

        fetcher = ImapFetcher()
        result = fetcher._connect(source)
        assert result == mock_conn
        mock_conn.login.assert_called_once()

    @patch("plugins.message_hub.services.imap.imap_fetcher.imaplib.IMAP4_SSL")
    def test_connect_login_failure(self, mock_imap):
        import imaplib

        mock_imap.side_effect = imaplib.IMAP4.error("Login failed")

        source = MagicMock()
        source.imap_account = "user@example.com"
        source.credential.account = "user@example.com"
        source.credential.password = "wrong"
        source.imap_host = "imap.example.com"
        source.credential.url = ""
        source.credential.site_name = ""

        fetcher = ImapFetcher()
        with pytest.raises(ValueError, match="登录失败"):
            fetcher._connect(source)
