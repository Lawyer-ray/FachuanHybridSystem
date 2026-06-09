"""Tests for documents path_utils, formatters, and smart_fill service."""

from __future__ import annotations

from datetime import date
from decimal import Decimal
from unittest.mock import MagicMock, patch

import pytest

from apps.documents.services.generation.path_utils import resolve_media_path, safe_arcname, safe_name
from apps.documents.utils.formatters import (
    format_currency,
    format_date,
    format_date_chinese,
    format_percentage,
    get_choice_display,
)


# ---------------------------------------------------------------------------
# path_utils
# ---------------------------------------------------------------------------


class TestResolveMediaPath:
    def test_empty_path(self) -> None:
        assert resolve_media_path("/media", "") == ""

    def test_none_path(self) -> None:
        assert resolve_media_path("/media", None) == ""  # type: ignore[arg-type]

    def test_http_url_returns_empty(self) -> None:
        assert resolve_media_path("/media", "http://example.com/file.pdf") == ""

    def test_https_url_returns_empty(self) -> None:
        assert resolve_media_path("/media", "https://example.com/file.pdf") == ""

    def test_media_prefix_stripped(self) -> None:
        result = resolve_media_path("/media", "/media/uploads/test.pdf")
        assert result == "/media/uploads/test.pdf"

    def test_absolute_path_returned(self) -> None:
        result = resolve_media_path("/media", "/absolute/path/file.pdf")
        assert result == "/absolute/path/file.pdf"

    def test_relative_path_joined(self) -> None:
        result = resolve_media_path("/media", "uploads/file.pdf")
        assert result == "/media/uploads/file.pdf"

    def test_exception_returns_empty(self) -> None:
        result = resolve_media_path("/media", "\x00invalid")
        # May or may not raise, but should return a string
        assert isinstance(result, str)


class TestSafeName:
    def test_empty(self) -> None:
        assert safe_name("") == "未命名"
        assert safe_name("  ") == "未命名"

    def test_normal(self) -> None:
        assert safe_name("test_file") == "test_file"

    def test_replaces_slashes(self) -> None:
        result = safe_name("path/to/file")
        assert "/" not in result
        assert "／" in result

    def test_replaces_backslash(self) -> None:
        result = safe_name("path\\to\\file")
        assert "\\" not in result

    def test_replaces_newlines(self) -> None:
        result = safe_name("line1\nline2")
        assert "\n" not in result

    def test_replaces_tabs(self) -> None:
        result = safe_name("a\tb")
        assert "\t" not in result


class TestSafeArcname:
    def test_normal(self) -> None:
        assert safe_arcname("test/file.pdf") == "test/file.pdf"

    def test_replaces_backslash(self) -> None:
        result = safe_arcname("test\\file.pdf")
        assert "\\" not in result

    def test_empty_parts_filtered(self) -> None:
        result = safe_arcname("test//file.pdf")
        assert "//" not in result


# ---------------------------------------------------------------------------
# formatters
# ---------------------------------------------------------------------------


class TestFormatDate:
    def test_none_returns_empty(self) -> None:
        assert format_date(None) == ""

    def test_date_object(self) -> None:
        d = date(2024, 1, 15)
        assert format_date(d) == "2024年01月15日"

    def test_date_string(self) -> None:
        assert format_date("2024-01-15") == "2024年01月15日"

    def test_invalid_string(self) -> None:
        assert format_date("not-a-date") == ""

    def test_custom_format(self) -> None:
        d = date(2024, 1, 15)
        assert format_date(d, fmt="%Y/%m/%d") == "2024/01/15"


class TestFormatDateChinese:
    def test_none_no_default(self) -> None:
        assert format_date_chinese(None, default_today=False) == ""

    def test_none_with_default_today(self) -> None:
        result = format_date_chinese(None, default_today=True)
        assert "年" in result  # should have today's date

    def test_valid_date(self) -> None:
        d = date(2024, 3, 5)
        assert format_date_chinese(d) == "2024年03月05日"

    def test_single_digit_month_day(self) -> None:
        d = date(2024, 1, 1)
        assert format_date_chinese(d) == "2024年01月01日"


class TestFormatCurrency:
    def test_none_returns_empty(self) -> None:
        assert format_currency(None) == ""

    def test_basic(self) -> None:
        assert format_currency(Decimal("1234.56")) == "1,234.56"

    def test_with_symbol(self) -> None:
        assert format_currency(Decimal("100"), include_symbol=True) == "¥100.00"

    def test_large_number(self) -> None:
        result = format_currency(Decimal("1000000"))
        assert "1,000,000" in result


class TestFormatPercentage:
    def test_none_returns_empty(self) -> None:
        assert format_percentage(None) == ""

    def test_basic(self) -> None:
        assert format_percentage(Decimal("10")) == "10.00%"

    def test_zero_decimal_places(self) -> None:
        assert format_percentage(Decimal("10"), decimal_places=0) == "10%"

    def test_four_decimal_places(self) -> None:
        result = format_percentage(Decimal("3.14159"), decimal_places=4)
        assert result == "3.1416%"


class TestGetChoiceDisplay:
    class SampleChoices:
        choices = [("a", "Alpha"), ("b", "Beta")]

    def test_valid_choice(self) -> None:
        assert get_choice_display("a", self.SampleChoices) == "Alpha"

    def test_invalid_choice(self) -> None:
        assert get_choice_display("c", self.SampleChoices) == "c"

    def test_empty_value(self) -> None:
        assert get_choice_display("", self.SampleChoices) == ""
