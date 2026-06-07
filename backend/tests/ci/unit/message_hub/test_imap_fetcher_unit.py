"""imap_fetcher.py 单元测试。"""

from __future__ import annotations

import pytest


class TestDecodeHeaderValue:

    def test_none_returns_empty(self):
        from apps.message_hub.services.imap.imap_fetcher import _decode_header_value
        assert _decode_header_value(None) == ""

    def test_plain_text(self):
        from apps.message_hub.services.imap.imap_fetcher import _decode_header_value
        assert _decode_header_value("Hello World") == "Hello World"

    def test_encoded_header(self):
        from apps.message_hub.services.imap.imap_fetcher import _decode_header_value
        # 带编码的 header
        result = _decode_header_value("=?utf-8?B?5L2g5aW9?=")
        assert "你好" in result


class TestExtractBody:

    def test_simple_text_message(self):
        from email.message import Message
        from apps.message_hub.services.imap.imap_fetcher import _extract_body
        msg = Message()
        msg.set_payload(b"Hello body", charset="utf-8")
        msg.set_type("text/plain")
        text, html = _extract_body(msg)
        assert "Hello body" in text
        assert html == ""

    def test_html_message(self):
        from email.message import Message
        from apps.message_hub.services.imap.imap_fetcher import _extract_body
        msg = Message()
        msg.set_payload(b"<p>Hello</p>", charset="utf-8")
        msg.set_type("text/html")
        text, html = _extract_body(msg)
        assert html == "<p>Hello</p>"


class TestExtractImapHost:

    def test_full_url(self):
        from apps.message_hub.services.imap.imap_fetcher import _extract_imap_host
        assert _extract_imap_host("imap://mail.example.com") == "mail.example.com"

    def test_plain_host(self):
        from apps.message_hub.services.imap.imap_fetcher import _extract_imap_host
        assert _extract_imap_host("mail.example.com") == "mail.example.com"

    def test_empty(self):
        from apps.message_hub.services.imap.imap_fetcher import _extract_imap_host
        assert _extract_imap_host("") == ""


class TestBuildImapHostCandidates:

    def test_both_provided(self):
        from apps.message_hub.services.imap.imap_fetcher import _build_imap_host_candidates
        result = _build_imap_host_candidates("imap.example.com", "mail.example.com")
        assert "imap.example.com" in result
        assert "mail.example.com" in result

    def test_generates_variants(self):
        from apps.message_hub.services.imap.imap_fetcher import _build_imap_host_candidates
        result = _build_imap_host_candidates("mail.example.com", "")
        assert "imap.example.com" in result or "example.com" in result

    def test_empty_returns_empty(self):
        from apps.message_hub.services.imap.imap_fetcher import _build_imap_host_candidates
        result = _build_imap_host_candidates("", "")
        assert result == []


class TestLooksLikeValidHost:

    @pytest.mark.parametrize("host,expected", [
        ("mail.example.com", True),
        ("imap.qq.com", True),
        ("", False),
        (".example.com", False),
        ("example.com.", False),
        ("http://example.com", False),
        ("example.com/path", False),
        ("host with space", False),
    ])
    def test_valid_host(self, host, expected):
        from apps.message_hub.services.imap.imap_fetcher import _looks_like_valid_host
        assert _looks_like_valid_host(host) == expected


class TestParseDate:

    def test_valid_date(self):
        from apps.message_hub.services.imap.imap_fetcher import _parse_date
        result = _parse_date("Mon, 15 Jan 2024 10:30:00 +0800")
        assert result is not None
        assert result.year == 2024

    def test_invalid_date(self):
        from apps.message_hub.services.imap.imap_fetcher import _parse_date
        assert _parse_date("not a date") is None


class TestParseFilterLines:

    def test_splits_lines(self):
        from apps.message_hub.services.imap.imap_fetcher import _parse_filter_lines
        result = _parse_filter_lines("line1\nline2\n\nline3")
        assert result == ["line1", "line2", "line3"]

    def test_empty(self):
        from apps.message_hub.services.imap.imap_fetcher import _parse_filter_lines
        assert _parse_filter_lines("") == []


class TestSenderAllowed:

    def test_whitelist_allows(self):
        from apps.message_hub.services.imap.imap_fetcher import _sender_allowed
        source = SimpleNamespace(sender_whitelist="example.com", sender_blacklist="")
        assert _sender_allowed("user@example.com", source) is True

    def test_whitelist_blocks(self):
        from apps.message_hub.services.imap.imap_fetcher import _sender_allowed
        source = SimpleNamespace(sender_whitelist="allowed.com", sender_blacklist="")
        assert _sender_allowed("user@blocked.com", source) is False

    def test_blacklist_blocks(self):
        from apps.message_hub.services.imap.imap_fetcher import _sender_allowed
        source = SimpleNamespace(sender_whitelist="", sender_blacklist="spam.com")
        assert _sender_allowed("user@spam.com", source) is False

    def test_no_filters_allows_all(self):
        from apps.message_hub.services.imap.imap_fetcher import _sender_allowed
        source = SimpleNamespace(sender_whitelist="", sender_blacklist="")
        assert _sender_allowed("anyone@any.com", source) is True


# 为 sender_allowed 测试补充 SimpleNamespace import
from types import SimpleNamespace
