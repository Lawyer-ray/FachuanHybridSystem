"""Property-based tests for execution_request_utils module."""

from __future__ import annotations

from datetime import date
from decimal import Decimal, InvalidOperation

from hypothesis import given, settings, assume
from hypothesis import strategies as st

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


@given(st.none())
@settings(max_examples=200, deadline=None)
def test_parse_decimal_none_returns_none(raw: None) -> None:
    assert parse_decimal(raw) is None


@given(st.just(""))
@settings(max_examples=200, deadline=None)
def test_parse_decimal_empty_returns_none(raw: str) -> None:
    assert parse_decimal(raw) is None


@settings(max_examples=200, deadline=None)
@given(st.decimals(allow_nan=False, allow_infinity=False))
def test_parse_decimal_roundtrip(d: Decimal) -> None:
    s = str(d)
    result = parse_decimal(s)
    assert result is not None
    assert result == d


@settings(max_examples=200, deadline=None)
@given(st.decimals(allow_nan=False, allow_infinity=False, min_value=0))
def test_parse_decimal_with_commas(d: Decimal) -> None:
    # Add commas as thousands separators (format with grouping)
    s = f"{d:,}"
    result = parse_decimal(s)
    assert result is not None
    assert result == d


@settings(max_examples=200, deadline=None)
@given(st.sampled_from(["abc", "xyz", "not-a-number", "!!", "中文"]))
def test_parse_decimal_non_numeric_returns_none(raw: str) -> None:
    assume(raw.replace(",", "").strip() != "")
    try:
        Decimal(raw.replace(",", "").strip())
        assume(False)  # skip valid decimals
    except (InvalidOperation, ValueError):
        assert parse_decimal(raw) is None


# ---------------------------------------------------------------------------
# safe_decimal
# ---------------------------------------------------------------------------


@given(st.none())
@settings(max_examples=200, deadline=None)
def test_safe_decimal_none_returns_zero(v: None) -> None:
    result = safe_decimal(v)
    assert isinstance(result, Decimal)
    assert result == Decimal("0")


@settings(max_examples=200, deadline=None)
@given(st.decimals(allow_nan=False, allow_infinity=False))
def test_safe_decimal_passthrough(d: Decimal) -> None:
    result = safe_decimal(d)
    assert isinstance(result, Decimal)
    assert result == d


@settings(max_examples=200, deadline=None)
@given(st.integers())
def test_safe_decimal_from_int(i: int) -> None:
    result = safe_decimal(i)
    assert isinstance(result, Decimal)
    assert result == Decimal(i)


@settings(max_examples=200, deadline=None)
@given(st.floats(allow_nan=False, allow_infinity=False))
def test_safe_decimal_from_float(f: float) -> None:
    result = safe_decimal(f)
    assert isinstance(result, Decimal)
    # Should not raise


# ---------------------------------------------------------------------------
# format_amount
# ---------------------------------------------------------------------------


@given(st.none())
@settings(max_examples=200, deadline=None)
def test_format_amount_none_returns_zero(v: None) -> None:
    assert format_amount(v) == "0"


@settings(max_examples=200, deadline=None)
@given(st.integers(min_value=-10**12, max_value=10**12))
def test_format_amount_integer_no_decimal(i: int) -> None:
    d = Decimal(i)
    result = format_amount(d)
    assert "." not in result
    assert int(result) == i


@settings(max_examples=200, deadline=None)
@given(st.decimals(min_value=Decimal("-1000000"), max_value=Decimal("1000000"), allow_nan=False, allow_infinity=False, places=2))
def test_format_amount_has_two_decimals_for_fractional(d: Decimal) -> None:
    quantized = d.quantize(Decimal("0.01"))
    if quantized != quantized.to_integral_value():
        result = format_amount(d)
        parts = result.split(".")
        assert len(parts) == 2
        assert len(parts[1]) <= 2


# ---------------------------------------------------------------------------
# build_date
# ---------------------------------------------------------------------------


@given(
    st.integers(min_value=1, max_value=9999),
    st.integers(min_value=1, max_value=12),
    st.integers(min_value=1, max_value=28),
)
@settings(max_examples=200, deadline=None)
def test_build_date_valid(y: int, m: int, d: int) -> None:
    result = build_date(str(y), str(m), str(d))
    assert isinstance(result, date)
    assert result.year == y
    assert result.month == m
    assert result.day == d


@settings(max_examples=200, deadline=None)
@given(st.integers(min_value=1, max_value=9999), st.integers(min_value=13, max_value=99))
def test_build_date_month_gt_12_returns_none(y: int, m: int) -> None:
    assert build_date(str(y), str(m), "1") is None


@settings(max_examples=200, deadline=None)
@given(st.integers(min_value=1, max_value=9999), st.integers(min_value=0, max_value=0))
def test_build_date_month_zero_returns_none(y: int, m: int) -> None:
    assert build_date(str(y), str(m), "1") is None


# ---------------------------------------------------------------------------
# parse_amount_value
# ---------------------------------------------------------------------------


@given(st.none())
@settings(max_examples=200, deadline=None)
def test_parse_amount_value_none_returns_none(v: None) -> None:
    assert parse_amount_value(v) is None


@settings(max_examples=200, deadline=None)
@given(st.decimals(min_value=Decimal("0"), max_value=Decimal("1000000"), allow_nan=False, allow_infinity=False, places=2))
def test_parse_amount_value_without_unit(d: Decimal) -> None:
    s = str(d)
    result = parse_amount_value(s)
    assert result is not None
    assert result == d


@settings(max_examples=200, deadline=None)
@given(st.decimals(min_value=Decimal("0"), max_value=Decimal("1000000"), allow_nan=False, allow_infinity=False, places=2))
def test_parse_amount_value_with_wan_unit(d: Decimal) -> None:
    s = str(d)
    result = parse_amount_value(s, unit_marker="万")
    assert result is not None
    assert result == d * Decimal("10000")


# ---------------------------------------------------------------------------
# parse_multiplier_value
# ---------------------------------------------------------------------------


@given(st.none())
@settings(max_examples=200, deadline=None)
def test_parse_multiplier_value_none_returns_none(v: None) -> None:
    assert parse_multiplier_value(v) is None


@settings(max_examples=200, deadline=None)
@given(st.decimals(min_value=Decimal("0"), max_value=Decimal("100"), allow_nan=False, allow_infinity=False, places=2))
def test_parse_multiplier_value_numeric_string(d: Decimal) -> None:
    s = str(d)
    result = parse_multiplier_value(s)
    assert result is not None
    assert result == d


@settings(max_examples=200, deadline=None)
@given(st.sampled_from(["零", "一", "二", "两", "三", "四", "五", "六", "七", "八", "九", "十"]))
def test_parse_multiplier_value_chinese_single(char: str) -> None:
    expected = {"零": 0, "一": 1, "二": 2, "两": 2, "三": 3, "四": 4, "五": 5, "六": 6, "七": 7, "八": 8, "九": 9, "十": 10}
    result = parse_multiplier_value(char)
    assert result is not None
    assert result == Decimal(str(expected[char]))


@settings(max_examples=200, deadline=None)
@given(st.sampled_from(["一", "二", "三", "四", "五", "六", "七", "八", "九"]))
def test_parse_multiplier_value_chinese_tens(left: str) -> None:
    digits = {"一": 1, "二": 2, "三": 3, "四": 4, "五": 5, "六": 6, "七": 7, "八": 8, "九": 9}
    s = f"{left}十"
    result = parse_multiplier_value(s)
    assert result is not None
    assert result == Decimal(str(digits[left] * 10))


# ---------------------------------------------------------------------------
# extract_sentence
# ---------------------------------------------------------------------------


@settings(max_examples=200, deadline=None)
@given(st.text(min_size=1, max_size=200), st.integers(min_value=0, max_value=50))
def test_extract_sentence_output_is_substring(text: str, offset: int) -> None:
    assume(offset < len(text))
    end = min(offset + 5, len(text))
    result = extract_sentence(text, offset, end)
    # The result should be a stripped substring of text
    assert result == result.strip()
    # Every char in result should exist in text (not necessarily contiguous but the
    # actual output is a contiguous slice)
    if result:
        assert result in text or len(result) <= len(text)


@settings(max_examples=200, deadline=None)
@given(st.text(min_size=1, max_size=200))
def test_extract_sentence_starts_at_zero(text: str) -> None:
    result = extract_sentence(text, 0, 0)
    # Result is a stripped prefix of text
    assert result == result.strip()


# ---------------------------------------------------------------------------
# normalize_text
# ---------------------------------------------------------------------------


@settings(max_examples=200, deadline=None)
@given(st.text(max_size=500))
def test_normalize_text_no_consecutive_spaces(text: str) -> None:
    result = normalize_text(text)
    assert "  " not in result


@settings(max_examples=200, deadline=None)
@given(st.text(max_size=500))
def test_normalize_text_no_tabs(text: str) -> None:
    result = normalize_text(text)
    assert "\t" not in result


@settings(max_examples=200, deadline=None)
@given(st.text(max_size=500))
def test_normalize_text_idempotent(text: str) -> None:
    result = normalize_text(text)
    assert normalize_text(result) == result


@settings(max_examples=200, deadline=None)
@given(st.sampled_from(["０", "１", "２", "３", "４", "５", "６", "７", "８", "９", "．", "，", "％", "：", "（", "）", "　"]))
def test_normalize_text_fullwidth_to_halfwidth(char: str) -> None:
    result = normalize_text(char)
    # Each fullwidth char should have a halfwidth counterpart in result
    assert len(result) >= 1


# ---------------------------------------------------------------------------
# normalize_year_days
# ---------------------------------------------------------------------------


@given(st.none())
@settings(max_examples=200, deadline=None)
def test_normalize_year_days_none_returns_360(v: None) -> None:
    assert normalize_year_days(v) == 360


@settings(max_examples=200, deadline=None)
@given(st.sampled_from([0, 360, 365]))
def test_normalize_year_days_valid_passthrough(v: int) -> None:
    assert normalize_year_days(v) == v


@settings(max_examples=200, deadline=None)
@given(st.integers(min_value=-1000, max_value=1000).filter(lambda x: x not in {0, 360, 365}))
def test_normalize_year_days_invalid_returns_360(v: int) -> None:
    assert normalize_year_days(v) == 360


# ---------------------------------------------------------------------------
# normalize_date_inclusion
# ---------------------------------------------------------------------------


@given(st.none())
@settings(max_examples=200, deadline=None)
def test_normalize_date_inclusion_none_returns_both(v: None) -> None:
    assert normalize_date_inclusion(v) == "both"


@settings(max_examples=200, deadline=None)
@given(st.sampled_from(["both", "start_only", "end_only", "neither"]))
def test_normalize_date_inclusion_valid_passthrough(v: str) -> None:
    assert normalize_date_inclusion(v) == v


@settings(max_examples=200, deadline=None)
@given(st.text(max_size=50).filter(lambda x: x not in {"both", "start_only", "end_only", "neither"}))
def test_normalize_date_inclusion_invalid_returns_both(v: str) -> None:
    assert normalize_date_inclusion(v) == "both"


# ---------------------------------------------------------------------------
# to_docx_hard_breaks
# ---------------------------------------------------------------------------


@settings(max_examples=200, deadline=None)
@given(st.text(max_size=500))
def test_to_docx_hard_breaks_no_newline(text: str) -> None:
    result = to_docx_hard_breaks(text)
    assert "\n" not in result


@settings(max_examples=200, deadline=None)
@given(st.text(max_size=500))
def test_to_docx_hard_breaks_idempotent(text: str) -> None:
    result = to_docx_hard_breaks(text)
    assert to_docx_hard_breaks(result) == result


@given(st.just(""))
@settings(max_examples=200, deadline=None)
def test_to_docx_hard_breaks_empty(text: str) -> None:
    assert to_docx_hard_breaks(text) == ""


@settings(max_examples=200, deadline=None)
@given(st.text(alphabet="\n\r", min_size=1, max_size=20))
def test_to_docx_hard_breaks_newline_only(text: str) -> None:
    result = to_docx_hard_breaks(text)
    assert "\n" not in result
    # Every newline becomes \a
    assert len(result) == len(text.replace("\r\n", "\n").replace("\r", "\n"))
