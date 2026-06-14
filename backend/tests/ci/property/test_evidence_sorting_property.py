"""Property-based tests for evidence sorting classifier & reconciler utilities."""

from __future__ import annotations

import re
from typing import Any

from hypothesis import given, settings, assume
from hypothesis import strategies as st

from apps.evidence_sorting.services.classifier import (
    TYPE_DELIVERY,
    TYPE_OTHER,
    TYPE_RECEIPT,
    TYPE_STATEMENT,
    ClassifierService,
)
from apps.evidence_sorting.services.reconciler import ReconcilerService, StatementInfo

KNOWN_TYPES = {TYPE_STATEMENT, TYPE_DELIVERY, TYPE_RECEIPT, TYPE_OTHER}

classifier = ClassifierService()
reconciler = ReconcilerService()


# ---------------------------------------------------------------------------
# ClassifierService._classify_by_keywords
# ---------------------------------------------------------------------------


@settings(max_examples=200, deadline=None)
@given(
    text=st.text(min_size=0, max_size=500),
    filename=st.text(min_size=0, max_size=200),
)
def test_classify_by_keywords_output_in_known_types(text: str, filename: str) -> None:
    """Output is always one of the four known type constants."""
    result = classifier._classify_by_keywords(text, filename)
    assert result in KNOWN_TYPES, f"unexpected type {result!r}"


# ---------------------------------------------------------------------------
# ClassifierService._extract_date
# ---------------------------------------------------------------------------


@settings(max_examples=200, deadline=None)
@given(
    year=st.integers(min_value=1900, max_value=2100),
    month=st.integers(min_value=1, max_value=12),
    day=st.integers(min_value=1, max_value=28),
    sep=st.sampled_from(["-", "/"]),
)
def test_extract_date_iso_format(year: int, month: int, day: int, sep: str) -> None:
    """ISO-format date text produces an 8-digit YYYYMMDD string."""
    text = f"{year:04d}{sep}{month:02d}{sep}{day:02d}"
    result = classifier._extract_date(text)
    assert result is not None
    assert len(result) == 8
    assert result.isdigit()
    assert result == f"{year:04d}{month:02d}{day:02d}"


@settings(max_examples=200, deadline=None)
@given(
    year=st.integers(min_value=1900, max_value=2100),
    month=st.integers(min_value=1, max_value=12),
    day=st.integers(min_value=1, max_value=28),
)
def test_extract_date_chinese_format(year: int, month: int, day: int) -> None:
    """Chinese-format date text produces an 8-digit YYYYMMDD string."""
    text = f"{year}年{month}月{day}日"
    result = classifier._extract_date(text)
    assert result is not None
    assert len(result) == 8
    assert result.isdigit()


@settings(max_examples=200, deadline=None)
@given(text=st.text(min_size=0, max_size=100).filter(lambda s: not re.search(r"\d{4}[-/年]\d{1,2}[-/月]\d{1,2}", s)))
def test_extract_date_none_for_no_date_text(text: str) -> None:
    """Text without date patterns returns None."""
    result = classifier._extract_date(text)
    assert result is None


# ---------------------------------------------------------------------------
# ClassifierService._extract_amount
# ---------------------------------------------------------------------------


@settings(max_examples=200, deadline=None)
@given(text=st.text(min_size=0, max_size=100).filter(lambda s: not re.search(r"[¥￥]|元|金额|合计|总计", s)))
def test_extract_amount_none_for_no_amount_text(text: str) -> None:
    """Text without amount patterns returns None."""
    assume(not re.search(r"\d", text))
    result = classifier._extract_amount(text)
    assert result is None


@settings(max_examples=200, deadline=None)
@given(amount=st.integers(min_value=1, max_value=99999999))
def test_extract_amount_yen_pattern(amount: int) -> None:
    """Amount with yen sign is extracted correctly."""
    text = f"¥{amount}"
    result = classifier._extract_amount(text)
    assert result is not None
    assert float(result) == float(amount)


@settings(max_examples=200, deadline=None)
@given(amount=st.integers(min_value=1, max_value=99999999))
def test_extract_amount_yuan_pattern(amount: int) -> None:
    """Amount with yuan suffix is extracted correctly."""
    text = f"{amount}元"
    result = classifier._extract_amount(text)
    assert result is not None
    assert float(result) == float(amount)


# ---------------------------------------------------------------------------
# ReconcilerService._extract_month_key
# ---------------------------------------------------------------------------


@settings(max_examples=200, deadline=None)
@given(
    year=st.integers(min_value=1900, max_value=2100),
    month=st.integers(min_value=1, max_value=12),
)
def test_extract_month_key_valid_format(year: int, month: int) -> None:
    """Valid YYYY-MM month string produces 'YYYY年MM月' format."""
    st_obj = StatementInfo(month=f"{year:04d}-{month:02d}")
    result = reconciler._extract_month_key(st_obj)
    expected = f"{year:04d}年{month:02d}月"
    assert result == expected


@settings(max_examples=200, deadline=None)
@given(month=st.text(min_size=0, max_size=50).filter(lambda s: not re.match(r"\d{4}-\d{1,2}", s)))
def test_extract_month_key_empty_for_invalid(month: str) -> None:
    """Non-matching month strings produce empty string."""
    st_obj = StatementInfo(month=month)
    result = reconciler._extract_month_key(st_obj)
    assert result == ""


# ---------------------------------------------------------------------------
# ReconcilerService._month_key_to_yyyymm
# ---------------------------------------------------------------------------


@settings(max_examples=200, deadline=None)
@given(
    year=st.integers(min_value=1900, max_value=2100),
    month=st.integers(min_value=1, max_value=12),
)
def test_month_key_to_yyyymm_valid(year: int, month: int) -> None:
    """Valid 'YYYY年MM月' produces a 6-digit YYYYMM string."""
    key = f"{year:04d}年{month:02d}月"
    result = reconciler._month_key_to_yyyymm(key)
    assert result is not None
    assert len(result) == 6
    assert result.isdigit()
    assert result == f"{year:04d}{month:02d}"


@settings(max_examples=200, deadline=None)
@given(key=st.text(min_size=0, max_size=50).filter(lambda s: not re.match(r"\d{4}年\d{2}", s)))
def test_month_key_to_yyyymm_none_for_invalid(key: str) -> None:
    """Non-matching key produces None."""
    result = reconciler._month_key_to_yyyymm(key)
    assert result is None


# ---------------------------------------------------------------------------
# ReconcilerService._normalize_date
# ---------------------------------------------------------------------------


@settings(max_examples=200, deadline=None)
@given(
    year=st.integers(min_value=1900, max_value=2100),
    month=st.integers(min_value=1, max_value=12),
    day=st.integers(min_value=1, max_value=28),
)
def test_normalize_date_valid_8_digits(year: int, month: int, day: int) -> None:
    """A date string with exactly 8 digits produces those 8 digits."""
    val = f"{year:04d}-{month:02d}-{day:02d}"
    result = ReconcilerService._normalize_date(val)
    assert result is not None
    assert len(result) == 8
    assert result == f"{year:04d}{month:02d}{day:02d}"


@settings(max_examples=200, deadline=None)
@given(val=st.none())
def test_normalize_date_none(val: None) -> None:
    """None input returns None."""
    assert ReconcilerService._normalize_date(val) is None


@settings(max_examples=200, deadline=None)
@given(val=st.just(""))
def test_normalize_date_empty(val: str) -> None:
    """Empty string returns None."""
    assert ReconcilerService._normalize_date(val) is None


# ---------------------------------------------------------------------------
# ReconcilerService._to_float
# ---------------------------------------------------------------------------


@settings(max_examples=200, deadline=None)
@given(val=st.none())
def test_to_float_none(val: None) -> None:
    """None input returns None."""
    assert ReconcilerService._to_float(val) is None


@settings(max_examples=200, deadline=None)
@given(
    int_part=st.integers(min_value=0, max_value=999999),
    dec_part=st.integers(min_value=0, max_value=99),
)
def test_to_float_with_commas(int_part: int, dec_part: int) -> None:
    """Comma-separated numeric strings are parsed correctly."""
    raw = f"{int_part:,}.{dec_part:02d}"
    result = ReconcilerService._to_float(raw)
    assert result is not None
    expected = float(f"{int_part}.{dec_part:02d}")
    assert abs(result - expected) < 1e-6


@settings(max_examples=200, deadline=None)
@given(n=st.integers(min_value=0, max_value=999999999))
def test_to_float_plain_integer(n: int) -> None:
    """Plain integer string parses correctly."""
    result = ReconcilerService._to_float(str(n))
    assert result is not None
    assert result == float(n)


@settings(max_examples=200, deadline=None)
@given(text=st.text(min_size=1, max_size=20).filter(lambda s: not any(c.isdigit() for c in s) and s.lower() not in ("inf", "nan", "-inf", "+inf", "infinity", "-infinity", "+infinity")))
def test_to_float_non_numeric_returns_none(text: str) -> None:
    """Non-numeric strings return None."""
    result = ReconcilerService._to_float(text)
    assert result is None


# ---------------------------------------------------------------------------
# ReconcilerService._match_delivery
# ---------------------------------------------------------------------------

from apps.evidence_sorting.services.reconciler import DeliveryNote, LineItem


svc = ReconcilerService()


def _make_delivery(date: str | None, amount: str | None) -> DeliveryNote:
    return DeliveryNote(filename="test.pdf", date=date, amount=amount)


def _make_line_item(date: str | None, amount: float | None) -> LineItem:
    return LineItem(date=date, amount=amount, description="test")


@settings(max_examples=200, deadline=None)
@given(
    date_str=st.from_regex(r"\d{8}", fullmatch=True),
    amount=st.floats(min_value=0.01, max_value=1_000_000, allow_nan=False, allow_infinity=False),
)
def test_match_delivery_same_date_and_amount_returns_true(date_str: str, amount: float) -> None:
    """Same date and same amount always match."""
    li = _make_line_item(date=date_str, amount=amount)
    dn = _make_delivery(date=date_str, amount=str(amount))
    assert svc._match_delivery(li, dn) is True


@settings(max_examples=200, deadline=None)
@given(
    date1=st.from_regex(r"\d{8}", fullmatch=True),
    date2=st.from_regex(r"\d{8}", fullmatch=True),
    amount=st.floats(min_value=100, max_value=1_000_000, allow_nan=False, allow_infinity=False),
)
def test_match_delivery_different_date_false(date1: str, date2: str, amount: float) -> None:
    """Different dates (and amounts that are also different) → False."""
    assume(date1 != date2)
    li = _make_line_item(date=date1, amount=amount)
    dn = _make_delivery(date=date2, amount=str(amount + 1_000_000))
    assert svc._match_delivery(li, dn) is False


@settings(max_examples=200, deadline=None)
@given(
    date_str=st.from_regex(r"\d{8}", fullmatch=True),
    amount=st.floats(min_value=100, max_value=1_000_000, allow_nan=False, allow_infinity=False),
    pct=st.floats(min_value=0.0001, max_value=0.0099),
)
def test_match_delivery_within_1pct_tolerance_true(date_str: str, amount: float, pct: float) -> None:
    """Amount within 1% tolerance (and same date) matches."""
    diff = amount * pct
    delivery_amount = amount + diff
    li = _make_line_item(date=date_str, amount=amount)
    dn = _make_delivery(date=date_str, amount=str(delivery_amount))
    assert svc._match_delivery(li, dn) is True


@settings(max_examples=200, deadline=None)
@given(
    date_str=st.just(""),
)
def test_match_delivery_both_dates_none_false(date_str: str) -> None:
    """When both dates are None → False (no date match, no amount fallback)."""
    li = _make_line_item(date=None, amount=None)
    dn = _make_delivery(date=None, amount=None)
    assert svc._match_delivery(li, dn) is False
