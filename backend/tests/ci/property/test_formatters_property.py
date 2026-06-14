"""Property-based tests for apps.documents.utils.formatters."""

from __future__ import annotations

from datetime import date
from decimal import Decimal

from hypothesis import given, settings, assume
from hypothesis import strategies as st

from apps.documents.utils.formatters import format_currency, format_date, format_percentage


# ---------------------------------------------------------------------------
# format_date
# ---------------------------------------------------------------------------


@settings(max_examples=200, deadline=None)
@given(d=st.none())
def test_format_date_none_returns_empty(d: None) -> None:
    """None input always returns empty string."""
    assert format_date(d) == ""


@settings(max_examples=200, deadline=None)
@given(d=st.dates(min_value=date(1900, 1, 1), max_value=date(2100, 12, 31)))
def test_format_date_valid_date_contains_year_month_day(d: date) -> None:
    """Valid date formatted with default format contains year/month/day characters."""
    result = format_date(d)
    assert "年" in result
    assert "月" in result
    assert "日" in result


@settings(max_examples=200, deadline=None)
@given(
    year=st.integers(min_value=1900, max_value=2100),
    month=st.integers(min_value=1, max_value=12),
    day=st.integers(min_value=1, max_value=28),
)
def test_format_date_iso_string(year: int, month: int, day: int) -> None:
    """Valid ISO string produces the expected Chinese-formatted date."""
    iso_str = f"{year:04d}-{month:02d}-{day:02d}"
    result = format_date(iso_str)
    assert result == f"{year}年{month:02d}月{day:02d}日"


@settings(max_examples=200, deadline=None)
@given(text=st.text(min_size=1, max_size=50).filter(lambda s: s != ""))
def test_format_date_invalid_string_returns_empty(text: str) -> None:
    """Non-ISO strings return empty string."""
    assume(not _is_iso_date(text))
    result = format_date(text)
    assert result == ""


def _is_iso_date(s: str) -> bool:
    """Check if a string is parseable as YYYY-MM-DD."""
    try:
        from datetime import datetime

        datetime.strptime(s, "%Y-%m-%d")
        return True
    except ValueError:
        return False


# ---------------------------------------------------------------------------
# format_currency
# ---------------------------------------------------------------------------


@settings(max_examples=200, deadline=None)
@given(amount=st.none())
def test_format_currency_none_returns_empty(amount: None) -> None:
    """None input always returns empty string."""
    assert format_currency(amount) == ""


@settings(max_examples=200, deadline=None)
@given(amount=st.decimals(min_value=Decimal("0"), max_value=Decimal("999999999.99"), allow_nan=False, allow_infinity=False))
def test_format_currency_has_two_decimal_places(amount: Decimal) -> None:
    """Output always has exactly 2 decimal places."""
    result = format_currency(amount)
    assert "." in result
    decimal_part = result.split(".")[-1]
    assert len(decimal_part) == 2


@settings(max_examples=200, deadline=None)
@given(amount=st.decimals(min_value=Decimal("0"), max_value=Decimal("999999999.99"), allow_nan=False, allow_infinity=False))
def test_format_currency_with_symbol_starts_with_yen(amount: Decimal) -> None:
    """When include_symbol=True, output starts with yen sign."""
    result = format_currency(amount, include_symbol=True)
    assert result.startswith("¥")


@settings(max_examples=200, deadline=None)
@given(amount=st.decimals(min_value=Decimal("0"), max_value=Decimal("999999999.99"), allow_nan=False, allow_infinity=False))
def test_format_currency_without_symbol_no_yen(amount: Decimal) -> None:
    """When include_symbol=False, output does not start with yen sign."""
    result = format_currency(amount, include_symbol=False)
    assert not result.startswith("¥")


# ---------------------------------------------------------------------------
# format_percentage
# ---------------------------------------------------------------------------


@settings(max_examples=200, deadline=None)
@given(rate=st.none())
def test_format_percentage_none_returns_empty(rate: None) -> None:
    """None input always returns empty string."""
    assert format_percentage(rate) == ""


@settings(max_examples=200, deadline=None)
@given(
    rate=st.decimals(min_value=Decimal("0"), max_value=Decimal("10000"), allow_nan=False, allow_infinity=False),
    decimal_places=st.integers(min_value=0, max_value=6),
)
def test_format_percentage_ends_with_percent(rate: Decimal, decimal_places: int) -> None:
    """Output always ends with percent sign."""
    result = format_percentage(rate, decimal_places=decimal_places)
    assert result.endswith("%")


@settings(max_examples=200, deadline=None)
@given(
    rate=st.decimals(min_value=Decimal("0"), max_value=Decimal("10000"), allow_nan=False, allow_infinity=False),
    decimal_places=st.integers(min_value=1, max_value=6),
)
def test_format_percentage_decimal_places(rate: Decimal, decimal_places: int) -> None:
    """When decimal_places > 0, the decimal part has the expected length."""
    result = format_percentage(rate, decimal_places=decimal_places)
    # strip trailing '%'
    numeric_part = result[:-1]
    if "." in numeric_part:
        dec_part = numeric_part.split(".")[-1]
        assert len(dec_part) == decimal_places
