"""
Tests for documents/utils/formatters.py - uncovered branches and edge cases.
"""
from __future__ import annotations

import logging
from datetime import date
from decimal import Decimal

import pytest

from apps.documents.utils.formatters import (
    format_currency,
    format_date,
    format_date_chinese,
    format_percentage,
    get_choice_display,
)


class TestFormatDate:
    def test_none_returns_empty(self):
        assert format_date(None) == ""

    def test_date_object(self):
        d = date(2024, 3, 15)
        assert format_date(d) == "2024年03月15日"

    def test_iso_string(self):
        assert format_date("2024-03-15") == "2024年03月15日"

    def test_custom_format(self):
        d = date(2024, 1, 5)
        assert format_date(d, fmt="%Y/%m/%d") == "2024/01/05"

    def test_invalid_string_returns_empty(self, caplog):
        assert format_date("not-a-date") == ""

    def test_garbage_string_returns_empty(self):
        assert format_date("xyz") == ""


class TestFormatDateChinese:
    def test_none_no_default(self):
        assert format_date_chinese(None) == ""

    def test_none_with_default_today(self):
        result = format_date_chinese(None, default_today=True)
        today = date.today()
        assert result == f"{today.year}年{today.month:02d}月{today.day:02d}日"

    def test_valid_date(self):
        assert format_date_chinese(date(2024, 1, 5)) == "2024年01月05日"

    def test_exception_returns_placeholder(self, monkeypatch):
        """Test that when d.strftime raises, we get the placeholder."""
        # Pass something that will cause .year to fail
        assert format_date_chinese("bad") == "____年____月____日"


class TestFormatCurrency:
    def test_none_returns_empty(self):
        assert format_currency(None) == ""

    def test_basic(self):
        assert format_currency(Decimal("1234.50")) == "1,234.50"

    def test_with_symbol(self):
        assert format_currency(Decimal("100"), include_symbol=True) == "¥100.00"

    def test_exception_returns_empty(self):
        # Pass a non-numeric value to trigger exception
        assert format_currency("not_decimal") == ""


class TestFormatPercentage:
    def test_none_returns_empty(self):
        assert format_percentage(None) == ""

    def test_basic(self):
        assert format_percentage(Decimal("10.5")) == "10.50%"

    def test_zero_decimals(self):
        assert format_percentage(Decimal("10"), decimal_places=0) == "10%"

    def test_exception_returns_empty(self):
        assert format_percentage("bad") == ""


class TestGetChoiceDisplay:
    class FakeChoices:
        A = "alpha"
        B = "beta"
        choices = [("a", "Alpha"), ("b", "Beta")]

    def test_empty_value(self):
        assert get_choice_display("", self.FakeChoices) == ""

    def test_found(self):
        assert get_choice_display("a", self.FakeChoices) == "Alpha"

    def test_not_found_returns_original(self):
        assert get_choice_display("z", self.FakeChoices) == "z"

    def test_exception_returns_original(self):
        class BadChoices:
            @property
            def choices(self):
                raise RuntimeError("fail")

        assert get_choice_display("a", BadChoices) == "a"
