"""Coverage tests for documents.utils.formatters."""
from __future__ import annotations

from datetime import date
from decimal import Decimal
from unittest.mock import MagicMock

import pytest


class TestFormatDate:
    def test_format_date_none(self):
        from apps.documents.utils.formatters import format_date
        assert format_date(None) == ""

    def test_format_date_date_obj(self):
        from apps.documents.utils.formatters import format_date
        result = format_date(date(2024, 1, 15))
        assert result == "2024年01月15日"

    def test_format_date_string(self):
        from apps.documents.utils.formatters import format_date
        result = format_date("2024-01-15")
        assert result == "2024年01月15日"

    def test_format_date_custom_fmt(self):
        from apps.documents.utils.formatters import format_date
        result = format_date(date(2024, 1, 15), fmt="%Y/%m/%d")
        assert result == "2024/01/15"

    def test_format_date_invalid_string(self):
        from apps.documents.utils.formatters import format_date
        result = format_date("not-a-date")
        assert result == ""


class TestFormatDateChinese:
    def test_format_date_chinese_none(self):
        from apps.documents.utils.formatters import format_date_chinese
        assert format_date_chinese(None) == ""

    def test_format_date_chinese_default_today(self):
        from apps.documents.utils.formatters import format_date_chinese
        result = format_date_chinese(None, default_today=True)
        assert "年" in result and "月" in result and "日" in result

    def test_format_date_chinese_date_obj(self):
        from apps.documents.utils.formatters import format_date_chinese
        result = format_date_chinese(date(2024, 3, 5))
        assert result == "2024年03月05日"


class TestFormatCurrency:
    def test_format_currency_none(self):
        from apps.documents.utils.formatters import format_currency
        assert format_currency(None) == ""

    def test_format_currency_basic(self):
        from apps.documents.utils.formatters import format_currency
        result = format_currency(Decimal("1234.56"))
        assert result == "1,234.56"

    def test_format_currency_with_symbol(self):
        from apps.documents.utils.formatters import format_currency
        result = format_currency(Decimal("100"), include_symbol=True)
        assert result == "¥100.00"


class TestFormatPercentage:
    def test_format_percentage_none(self):
        from apps.documents.utils.formatters import format_percentage
        assert format_percentage(None) == ""

    def test_format_percentage_basic(self):
        from apps.documents.utils.formatters import format_percentage
        result = format_percentage(Decimal("10"))
        assert result == "10.00%"

    def test_format_percentage_zero_decimals(self):
        from apps.documents.utils.formatters import format_percentage
        result = format_percentage(Decimal("10"), decimal_places=0)
        assert result == "10%"


class TestGetChoiceDisplay:
    def test_get_choice_display_empty(self):
        from apps.documents.utils.formatters import get_choice_display
        assert get_choice_display("", MagicMock) == ""

    def test_get_choice_display_found(self):
        from apps.documents.utils.formatters import get_choice_display
        cls = MagicMock()
        cls.choices = [("a", "Alpha"), ("b", "Beta")]
        assert get_choice_display("a", cls) == "Alpha"

    def test_get_choice_display_not_found(self):
        from apps.documents.utils.formatters import get_choice_display
        cls = MagicMock()
        cls.choices = [("a", "Alpha")]
        assert get_choice_display("z", cls) == "z"
