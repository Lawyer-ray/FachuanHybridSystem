"""Property-based tests for execution_request_parser module."""

from __future__ import annotations

from decimal import Decimal

from hypothesis import given, settings, assume
from hypothesis import strategies as st

from apps.documents.services.placeholders.litigation.execution_request_parser import (
    extract_party_burden_amount,
    parse_confirmed_amounts,
    parse_fee_items,
    should_include_fee,
)
from apps.documents.services.placeholders.litigation.execution_request_models import ParsedAmounts


# ---------------------------------------------------------------------------
# parse_confirmed_amounts
# ---------------------------------------------------------------------------


@given(st.just(""))
@settings(max_examples=200, deadline=None)
def test_parse_confirmed_amounts_empty_text(text: str) -> None:
    result = parse_confirmed_amounts(text)
    assert isinstance(result, ParsedAmounts)
    # Empty text should yield zero or None amounts
    assert result.principal is None or result.principal >= Decimal("0")
    assert result.confirmed_interest >= Decimal("0")
    assert result.litigation_fee >= Decimal("0")
    assert result.preservation_fee >= Decimal("0")
    assert result.announcement_fee >= Decimal("0")
    assert result.attorney_fee >= Decimal("0")
    assert result.guarantee_fee >= Decimal("0")


@settings(max_examples=200, deadline=None)
@given(st.text(max_size=2000))
def test_parse_confirmed_amounts_amounts_non_negative(text: str) -> None:
    result = parse_confirmed_amounts(text)
    assert isinstance(result, ParsedAmounts)
    if result.principal is not None:
        assert result.principal >= Decimal("0"), f"principal={result.principal} < 0"
    assert result.confirmed_interest >= Decimal("0"), f"confirmed_interest={result.confirmed_interest} < 0"
    assert result.litigation_fee >= Decimal("0")
    assert result.preservation_fee >= Decimal("0")
    assert result.announcement_fee >= Decimal("0")
    assert result.attorney_fee >= Decimal("0")
    assert result.guarantee_fee >= Decimal("0")


@settings(max_examples=200, deadline=None)
@given(st.text(max_size=2000))
def test_parse_confirmed_amounts_returns_dataclass(text: str) -> None:
    result = parse_confirmed_amounts(text)
    assert isinstance(result, ParsedAmounts)
    assert isinstance(result.excluded_fees, list)
    assert isinstance(result.principal_label, str)


# ---------------------------------------------------------------------------
# parse_fee_items
# ---------------------------------------------------------------------------


@given(st.just(""))
@settings(max_examples=200, deadline=None)
def test_parse_fee_items_empty_text(text: str) -> None:
    result = parse_fee_items(text)
    assert isinstance(result, list)
    assert len(result) == 0


@settings(max_examples=200, deadline=None)
@given(st.text(max_size=2000))
def test_parse_fee_items_amounts_non_negative(text: str) -> None:
    items = parse_fee_items(text)
    assert isinstance(items, list)
    for item in items:
        assert item.amount >= Decimal("0"), f"FeeItem {item.key} has amount {item.amount} < 0"


@settings(max_examples=200, deadline=None)
@given(st.text(max_size=2000))
def test_parse_fee_items_have_valid_keys(text: str) -> None:
    valid_keys = {"litigation_fee", "preservation_fee", "announcement_fee", "attorney_fee", "guarantee_fee"}
    items = parse_fee_items(text)
    for item in items:
        assert item.key in valid_keys, f"Unexpected key: {item.key}"


# ---------------------------------------------------------------------------
# should_include_fee
# ---------------------------------------------------------------------------


@settings(max_examples=200, deadline=None)
@given(st.text(max_size=500))
def test_should_include_fee_attorney_fee_always_true(sentence: str) -> None:
    include, reason = should_include_fee(sentence=sentence, key="attorney_fee")
    assert include is True
    assert reason == ""


@settings(max_examples=200, deadline=None)
@given(st.text(max_size=500))
def test_should_include_fee_guarantee_fee_always_true(sentence: str) -> None:
    include, reason = should_include_fee(sentence=sentence, key="guarantee_fee")
    assert include is True
    assert reason == ""


@settings(max_examples=200, deadline=None)
@given(st.text(max_size=500), st.sampled_from(["litigation_fee", "preservation_fee", "announcement_fee"]))
def test_should_include_fee_deterministic(sentence: str, key: str) -> None:
    result1 = should_include_fee(sentence=sentence, key=key)
    result2 = should_include_fee(sentence=sentence, key=key)
    assert result1 == result2


@settings(max_examples=200, deadline=None)
@given(st.text(max_size=500), st.sampled_from(["attorney_fee", "guarantee_fee", "litigation_fee", "preservation_fee", "announcement_fee"]))
def test_should_include_fee_returns_tuple(sentence: str, key: str) -> None:
    result = should_include_fee(sentence=sentence, key=key)
    assert isinstance(result, tuple)
    assert len(result) == 2
    include, reason = result
    assert isinstance(include, bool)
    assert isinstance(reason, str)


# ---------------------------------------------------------------------------
# extract_party_burden_amount
# ---------------------------------------------------------------------------


PARTIES = ("原告", "被告", "申请人", "被申请人")


@settings(max_examples=200, deadline=None)
@given(st.text(max_size=500))
def test_extract_party_burden_returns_none_or_positive_decimal(text: str) -> None:
    """extract_party_burden_amount returns None or a positive Decimal."""
    result = extract_party_burden_amount(text, parties=PARTIES)
    assert result is None or (isinstance(result, Decimal) and result >= 0)


@settings(max_examples=200, deadline=None)
@given(st.text(max_size=500))
def test_extract_party_burden_deterministic(text: str) -> None:
    """Same inputs always produce the same result."""
    r1 = extract_party_burden_amount(text, parties=PARTIES)
    r2 = extract_party_burden_amount(text, parties=PARTIES)
    assert r1 == r2


@settings(max_examples=200, deadline=None)
@given(st.just(""))
def test_extract_party_burden_empty_parties(text: str) -> None:
    """Empty parties tuple always returns None."""
    result = extract_party_burden_amount(text, parties=())
    assert result is None
