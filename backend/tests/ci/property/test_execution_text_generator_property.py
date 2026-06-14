"""Property-based tests for execution_request_text_generator helpers."""

from __future__ import annotations

from decimal import Decimal

from hypothesis import given, settings, assume
from hypothesis import strategies as st

from apps.documents.services.placeholders.litigation.execution_request_models import (
    InterestSegment,
    ParsedAmounts,
)
from apps.documents.services.placeholders.litigation.execution_request_text_generator import (
    build_fee_desc,
    build_interest_segment_desc,
)

from datetime import date


# ---------------------------------------------------------------------------
# build_fee_desc
# ---------------------------------------------------------------------------


@settings(max_examples=200, deadline=None)
@given(
    litigation=st.decimals(min_value=Decimal("0"), max_value=Decimal("0"), allow_nan=False),
    preservation=st.decimals(min_value=Decimal("0"), max_value=Decimal("0"), allow_nan=False),
    announcement=st.decimals(min_value=Decimal("0"), max_value=Decimal("0"), allow_nan=False),
    attorney=st.decimals(min_value=Decimal("0"), max_value=Decimal("0"), allow_nan=False),
    guarantee=st.decimals(min_value=Decimal("0"), max_value=Decimal("0"), allow_nan=False),
)
def test_build_fee_desc_all_zero_returns_empty(
    litigation: Decimal,
    preservation: Decimal,
    announcement: Decimal,
    attorney: Decimal,
    guarantee: Decimal,
) -> None:
    """All-zero fee amounts produce an empty string."""
    amounts = ParsedAmounts(
        litigation_fee=litigation,
        preservation_fee=preservation,
        announcement_fee=announcement,
        attorney_fee=attorney,
        guarantee_fee=guarantee,
    )
    result = build_fee_desc(amounts)
    assert result == ""


@settings(max_examples=200, deadline=None)
@given(
    litigation=st.decimals(min_value=Decimal("0.01"), max_value=Decimal("999999.99"), allow_nan=False, allow_infinity=False),
)
def test_build_fee_desc_nonzero_litigation_contains_yuan(litigation: Decimal) -> None:
    """Non-zero litigation_fee produces output containing '元'."""
    amounts = ParsedAmounts(litigation_fee=litigation)
    result = build_fee_desc(amounts)
    assert "元" in result
    assert "受理费" in result


@settings(max_examples=200, deadline=None)
@given(
    preservation=st.decimals(min_value=Decimal("0.01"), max_value=Decimal("999999.99"), allow_nan=False, allow_infinity=False),
)
def test_build_fee_desc_nonzero_preservation_contains_yuan(preservation: Decimal) -> None:
    """Non-zero preservation_fee produces output containing '保全费'."""
    amounts = ParsedAmounts(preservation_fee=preservation)
    result = build_fee_desc(amounts)
    assert "保全费" in result
    assert "元" in result


@settings(max_examples=200, deadline=None)
@given(
    attorney=st.decimals(min_value=Decimal("0.01"), max_value=Decimal("999999.99"), allow_nan=False, allow_infinity=False),
)
def test_build_fee_desc_nonzero_attorney_contains_yuan(attorney: Decimal) -> None:
    """Non-zero attorney_fee produces output containing '律师代理费'."""
    amounts = ParsedAmounts(attorney_fee=attorney)
    result = build_fee_desc(amounts)
    assert "律师代理费" in result
    assert "元" in result


# ---------------------------------------------------------------------------
# build_interest_segment_desc
# ---------------------------------------------------------------------------


@settings(max_examples=200, deadline=None)
@given(segments=st.just([]))
def test_build_interest_segment_desc_empty(segments: list) -> None:
    """Empty segment list produces empty string."""
    result = build_interest_segment_desc(segments)
    assert result == ""


@settings(max_examples=200, deadline=None)
@given(
    base=st.decimals(min_value=Decimal("1"), max_value=Decimal("999999"), allow_nan=False, allow_infinity=False),
    year=st.integers(min_value=2000, max_value=2030),
    month=st.integers(min_value=1, max_value=12),
    day=st.integers(min_value=1, max_value=28),
)
def test_build_interest_segment_desc_single_segment_contains_yuan(
    base: Decimal, year: int, month: int, day: int,
) -> None:
    """A single segment produces output containing '元' and date text."""
    segment = InterestSegment(
        base_amount=base,
        start_date=date(year, month, day),
        end_date=None,
    )
    result = build_interest_segment_desc([segment])
    assert "元" in result
    assert f"{year}年" in result


@settings(max_examples=200, deadline=None)
@given(
    n=st.integers(min_value=2, max_value=5),
)
def test_build_interest_segment_desc_multiple_segments_semicolons(n: int) -> None:
    """Multiple segments are separated by semicolons."""
    segments = []
    for i in range(n):
        segments.append(
            InterestSegment(
                base_amount=Decimal("1000"),
                start_date=date(2020, 1, 1),
                end_date=date(2020, 1 + i, 1),
            )
        )
    result = build_interest_segment_desc(segments)
    assert result.count("；") == n - 1
