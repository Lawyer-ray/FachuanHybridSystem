"""Tests for execution_request_utils module.

Covers:
  - parse_decimal
  - safe_decimal
  - format_amount
  - build_date
  - parse_amount_value
  - parse_multiplier_value
  - extract_sentence
  - normalize_text
  - normalize_year_days
  - normalize_date_inclusion
  - to_docx_hard_breaks
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal

import pytest

from apps.documents.services.placeholders.litigation.execution_request_utils import (
    build_date,
    extract_sentence,
    format_amount,
    normalize_date_inclusion,
    normalize_text,
    normalize_year_days,
    parse_amount_value,
    parse_decimal,
    parse_multiplier_value,
    safe_decimal,
    to_docx_hard_breaks,
)


# ---------------------------------------------------------------------------
# parse_decimal
# ---------------------------------------------------------------------------


class TestParseDecimal:
    def test_valid(self) -> None:
        assert parse_decimal("100") == Decimal("100")

    def test_with_comma(self) -> None:
        assert parse_decimal("1,000") == Decimal("1000")

    def test_float(self) -> None:
        assert parse_decimal("3.14") == Decimal("3.14")

    def test_none(self) -> None:
        assert parse_decimal(None) is None

    def test_empty(self) -> None:
        assert parse_decimal("") is None

    def test_whitespace(self) -> None:
        assert parse_decimal("   ") is None

    def test_invalid(self) -> None:
        assert parse_decimal("abc") is None


# ---------------------------------------------------------------------------
# safe_decimal
# ---------------------------------------------------------------------------


class TestSafeDecimal:
    def test_none(self) -> None:
        assert safe_decimal(None) == Decimal("0")

    def test_decimal(self) -> None:
        assert safe_decimal(Decimal("100")) == Decimal("100")

    def test_int(self) -> None:
        assert safe_decimal(100) == Decimal("100")

    def test_str(self) -> None:
        assert safe_decimal("3.14") == Decimal("3.14")

    def test_invalid(self) -> None:
        assert safe_decimal("abc") == Decimal("0")


# ---------------------------------------------------------------------------
# format_amount
# ---------------------------------------------------------------------------


class TestFormatAmount:
    def test_integer(self) -> None:
        assert format_amount(Decimal("100")) == "100"

    def test_decimal_places(self) -> None:
        result = format_amount(Decimal("100.50"))
        assert "100.5" in result

    def test_none(self) -> None:
        assert format_amount(None) == "0"

    def test_rounding(self) -> None:
        result = format_amount(Decimal("100.456"))
        assert "100.46" in result

    def test_zero(self) -> None:
        assert format_amount(Decimal("0")) == "0"

    def test_integer_value_with_decimals(self) -> None:
        assert format_amount(Decimal("100.00")) == "100"


# ---------------------------------------------------------------------------
# build_date
# ---------------------------------------------------------------------------


class TestBuildDate:
    def test_valid(self) -> None:
        assert build_date("2020", "1", "15") == date(2020, 1, 15)

    def test_invalid_month(self) -> None:
        assert build_date("2020", "13", "1") is None

    def test_invalid_day(self) -> None:
        assert build_date("2020", "1", "32") is None

    def test_leap_year(self) -> None:
        assert build_date("2024", "2", "29") == date(2024, 2, 29)


# ---------------------------------------------------------------------------
# parse_amount_value
# ---------------------------------------------------------------------------


class TestParseAmountValue:
    def test_basic(self) -> None:
        assert parse_amount_value("100", None) == Decimal("100")

    def test_with_wan(self) -> None:
        assert parse_amount_value("100", "万") == Decimal("1000000")

    def test_none_raw(self) -> None:
        assert parse_amount_value(None, None) is None

    def test_invalid(self) -> None:
        assert parse_amount_value("abc", None) is None

    def test_wan_in_unit(self) -> None:
        assert parse_amount_value("50", "万元") == Decimal("500000")


# ---------------------------------------------------------------------------
# parse_multiplier_value
# ---------------------------------------------------------------------------


class TestParseMultiplierValue:
    def test_numeric(self) -> None:
        assert parse_multiplier_value("1.5") == Decimal("1.5")

    def test_chinese_one(self) -> None:
        assert parse_multiplier_value("一") == Decimal("1")

    def test_chinese_two(self) -> None:
        assert parse_multiplier_value("两") == Decimal("2")

    def test_chinese_ten(self) -> None:
        assert parse_multiplier_value("十") == Decimal("10")

    def test_chinese_compound(self) -> None:
        assert parse_multiplier_value("十五") == Decimal("15")

    def test_none(self) -> None:
        assert parse_multiplier_value(None) is None

    def test_invalid(self) -> None:
        assert parse_multiplier_value("xyz") is None

    def test_chinese_five(self) -> None:
        assert parse_multiplier_value("五") == Decimal("5")


# ---------------------------------------------------------------------------
# extract_sentence
# ---------------------------------------------------------------------------


class TestExtractSentence:
    def test_basic(self) -> None:
        text = "被告支付货款100万元。被告支付利息10万元。"
        result = extract_sentence(text, 0, 11)
        assert "100万元" in result

    def test_with_semicolon(self) -> None:
        text = "被告支付货款100万元；被告支付利息10万元。"
        result = extract_sentence(text, 0, 11)
        assert "100万元" in result

    def test_no_delimiter(self) -> None:
        text = "被告支付货款100万元"
        result = extract_sentence(text, 0, 5)
        assert result == text


# ---------------------------------------------------------------------------
# normalize_text
# ---------------------------------------------------------------------------


class TestNormalizeText:
    def test_fullwidth_digits(self) -> None:
        result = normalize_text("１００万元")
        assert "100万元" in result

    def test_fullwidth_punctuation(self) -> None:
        result = normalize_text("被告（甲方）")
        assert "(" in result
        assert ")" in result

    def test_multiple_spaces(self) -> None:
        result = normalize_text("被告  支付")
        assert "  " not in result

    def test_newlines_normalized(self) -> None:
        result = normalize_text("line1\n\n\nline2")
        assert "\n\n" not in result


# ---------------------------------------------------------------------------
# normalize_year_days
# ---------------------------------------------------------------------------


class TestNormalizeYearDays:
    def test_360(self) -> None:
        assert normalize_year_days(360) == 360

    def test_365(self) -> None:
        assert normalize_year_days(365) == 365

    def test_zero(self) -> None:
        assert normalize_year_days(0) == 0

    def test_invalid(self) -> None:
        assert normalize_year_days(366) == 360

    def test_none(self) -> None:
        assert normalize_year_days(None) == 360


# ---------------------------------------------------------------------------
# normalize_date_inclusion
# ---------------------------------------------------------------------------


class TestNormalizeDateInclusion:
    def test_both(self) -> None:
        assert normalize_date_inclusion("both") == "both"

    def test_start_only(self) -> None:
        assert normalize_date_inclusion("start_only") == "start_only"

    def test_end_only(self) -> None:
        assert normalize_date_inclusion("end_only") == "end_only"

    def test_neither(self) -> None:
        assert normalize_date_inclusion("neither") == "neither"

    def test_invalid(self) -> None:
        assert normalize_date_inclusion("invalid") == "both"

    def test_none(self) -> None:
        assert normalize_date_inclusion(None) == "both"


# ---------------------------------------------------------------------------
# to_docx_hard_breaks
# ---------------------------------------------------------------------------


class TestToDocxHardBreaks:
    def test_basic(self) -> None:
        result = to_docx_hard_breaks("line1\nline2")
        assert "\a" in result
        assert "\n" not in result

    def test_crlf(self) -> None:
        result = to_docx_hard_breaks("line1\r\nline2")
        assert "\a" in result

    def test_empty(self) -> None:
        assert to_docx_hard_breaks("") == ""

    def test_none(self) -> None:
        assert to_docx_hard_breaks("") == ""
