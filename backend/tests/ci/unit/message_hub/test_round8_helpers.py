"""Tests for IMAP fetcher helpers, court schedule helpers, segment_detector, and message_hub models."""

from __future__ import annotations

import email
from datetime import datetime
from email.message import Message
from typing import Any
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
        _decode_header_value,
        _extract_body,
        _parse_date,
        _parse_filter_lines,
        _sender_allowed,
        _looks_like_valid_host,
        _extract_imap_host,
        _build_imap_host_candidates,

)
if _HAS_MH:
    from plugins.message_hub.services.court.court_schedule_fetcher import (
        _parse_datetime as court_parse_datetime,
        _extract_party_names as court_extract_party_names,
        _strip_case_cause_suffix as court_strip_case_cause_suffix,
        _split_by_comma,
        _is_valid_party_name,
        _extract_name_from_segment,

)

# ---------------------------------------------------------------------------
# IMAP Helpers
# ---------------------------------------------------------------------------

class TestDecodeHeaderValue:
    def test_none(self):
        assert _decode_header_value(None) == ""

    def test_empty(self):
        assert _decode_header_value("") == ""

    def test_plain_string(self):
        assert _decode_header_value("Hello World") == "Hello World"

    def test_encoded_bytes(self):
        msg = email.message.Message()
        msg["Subject"] = "Test Subject"
        result = _decode_header_value(msg.get("Subject"))
        assert result == "Test Subject"

class TestExtractBody:
    def test_non_multipart_text(self):
        msg = Message()
        msg.set_type("text/plain")
        msg.set_payload("Hello World")
        text, html = _extract_body(msg)
        assert text == "Hello World"
        assert html == ""

    def test_non_multipart_html(self):
        msg = Message()
        msg.set_type("text/html")
        msg.set_payload("<p>Hello</p>")
        text, html = _extract_body(msg)
        assert text == ""
        assert html == "<p>Hello</p>"

    def test_multipart_mixed(self):
        msg = Message()
        msg.add_header("Content-Type", "multipart/mixed")
        msg.set_type("multipart/mixed")
        part1 = Message()
        part1.set_type("text/plain")
        part1.set_payload("Plain text content")
        msg.attach(part1)
        text, html = _extract_body(msg)
        assert "Plain text" in text

    def test_multipart_with_attachment_skip(self):
        msg = Message()
        msg.set_type("multipart/mixed")
        part1 = Message()
        part1.add_header("Content-Disposition", "attachment", filename="test.pdf")
        part1.set_type("application/pdf")
        part1.set_payload(b"binary")
        msg.attach(part1)
        text, html = _extract_body(msg)
        assert text == ""
        assert html == ""

class TestParseDate:
    def test_valid_date(self):
        result = _parse_date("Mon, 15 Jan 2024 10:00:00 +0800")
        assert result is not None

    def test_invalid_date(self):
        result = _parse_date("not a date")
        assert result is None

class TestParseFilterLines:
    def test_multiline(self):
        result = _parse_filter_lines("line1\nline2\nline3")
        assert result == ["line1", "line2", "line3"]

    def test_empty_lines(self):
        result = _parse_filter_lines("line1\n\n\nline2")
        assert result == ["line1", "line2"]

    def test_blank(self):
        result = _parse_filter_lines("")
        assert result == []

class TestSenderAllowed:
    def test_no_filters(self):
        source = MagicMock()
        source.sender_whitelist = ""
        source.sender_blacklist = ""
        assert _sender_allowed("test@example.com", source) is True

    def test_whitelist_match(self):
        source = MagicMock()
        source.sender_whitelist = "trusted.com"
        source.sender_blacklist = ""
        assert _sender_allowed("user@trusted.com", source) is True

    def test_whitelist_no_match(self):
        source = MagicMock()
        source.sender_whitelist = "trusted.com"
        source.sender_blacklist = ""
        assert _sender_allowed("user@other.com", source) is False

    def test_blacklist_match(self):
        source = MagicMock()
        source.sender_whitelist = ""
        source.sender_blacklist = "spam.com"
        assert _sender_allowed("user@spam.com", source) is False

    def test_blacklist_no_match(self):
        source = MagicMock()
        source.sender_whitelist = ""
        source.sender_blacklist = "spam.com"
        assert _sender_allowed("user@good.com", source) is True

class TestLooksLikeValidHost:
    def test_valid(self):
        assert _looks_like_valid_host("imap.gmail.com") is True

    def test_empty(self):
        assert _looks_like_valid_host("") is False

    def test_with_scheme(self):
        assert _looks_like_valid_host("https://imap.gmail.com") is False

    def test_with_slash(self):
        assert _looks_like_valid_host("imap/gmail") is False

    def test_starts_with_dot(self):
        assert _looks_like_valid_host(".gmail.com") is False

    def test_ends_with_dot(self):
        assert _looks_like_valid_host("gmail.") is False

    def test_with_space(self):
        assert _looks_like_valid_host("imap gmail") is False

class TestExtractImapHost:
    def test_with_scheme(self):
        assert _extract_imap_host("imap://mail.example.com") == "mail.example.com"

    def test_without_scheme(self):
        assert _extract_imap_host("mail.example.com") == "mail.example.com"

    def test_empty(self):
        assert _extract_imap_host("") == ""

    def test_plain_hostname(self):
        assert _extract_imap_host("imap.gmail.com") == "imap.gmail.com"

class TestBuildImapHostCandidates:
    def test_basic(self):
        candidates = _build_imap_host_candidates("imap.gmail.com", "mail.gmail.com")
        assert "imap.gmail.com" in candidates

    def test_empty(self):
        candidates = _build_imap_host_candidates("", "")
        assert candidates == []

    def test_mail_prefix_generates_imap(self):
        candidates = _build_imap_host_candidates("mail.example.com", "")
        assert any("imap." in c for c in candidates)

    def test_imap_prefix_generates_mail(self):
        candidates = _build_imap_host_candidates("imap.example.com", "")
        assert any("mail." in c for c in candidates)

# ---------------------------------------------------------------------------
# Court Schedule Fetcher Helpers
# ---------------------------------------------------------------------------

class TestCourtScheduleHelpers:
    def test_parse_datetime_valid(self):
        result = court_parse_datetime("2026-05-29 16:30")
        assert result.hour == 16
        assert result.minute == 30

    def test_parse_datetime_invalid(self):
        result = court_parse_datetime("invalid")
        assert result is not None  # falls back to now()

    def test_extract_party_names_empty(self):
        assert court_extract_party_names("") == []

    def test_extract_party_names_with_vs(self):
        result = court_extract_party_names("原告公司与被告公司一案")
        assert "原告公司" in result
        assert "被告公司" in result

    def test_extract_party_names_no_vs(self):
        result = court_extract_party_names("某某公司")
        assert result == []

    def test_strip_case_cause_suffix(self):
        assert court_strip_case_cause_suffix("汪达买卖合同纠纷") == "汪达"
        assert court_strip_case_cause_suffix("石莹追偿权纠纷") == "石莹"
        assert court_strip_case_cause_suffix("公司名称") == "公司名称"

    def test_is_valid_party_name_company(self):
        assert _is_valid_party_name("某某有限公司") is True

    def test_is_valid_party_name_short(self):
        assert _is_valid_party_name("张") is False

    def test_is_valid_party_name_empty(self):
        assert _is_valid_party_name("") is False

    def test_is_valid_party_name_person_name(self):
        assert _is_valid_party_name("张三") is True

    def test_is_valid_party_name_cause_fragment(self):
        assert _is_valid_party_name("买卖合同纠纷") is False

    def test_split_by_comma(self):
        assert _split_by_comma("a，b,c") == ["a", "b", "c"]

    def test_extract_name_from_segment_valid_name(self):
        assert _extract_name_from_segment("张三") == ["张三"]

    def test_extract_name_from_segment_with_cause(self):
        result = _extract_name_from_segment("汪达买卖合同纠纷")
        assert "汪达" in result

    def test_extract_name_from_segment_company(self):
        result = _extract_name_from_segment("某某有限公司")
        assert "某某有限公司" in result
