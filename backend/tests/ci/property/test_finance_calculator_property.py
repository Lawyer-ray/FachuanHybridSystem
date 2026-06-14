"""Property-based tests for apps.finance.services.calculator.interest_calculator."""

from __future__ import annotations

import calendar
from datetime import date, timedelta
from decimal import Decimal

from hypothesis import given, settings, assume
from hypothesis import strategies as st

from apps.finance.services.calculator.interest_calculator import (
    CalculationPeriod,
    InterestCalculator,
)


# ---------------------------------------------------------------------------
# Strategies
# ---------------------------------------------------------------------------

# Dates in a reasonable range for legal/financial calculations
_date_strat = st.dates(min_value=date(2000, 1, 1), max_value=date(2099, 12, 28))

# Reasonable principal amounts (1 to 10 billion in cents)
_principal_strat = st.decimals(min_value=1, max_value=Decimal("10000000000"), places=2)

# Annual interest rate percent (0.01% to 100%)
_rate_strat = st.decimals(min_value=Decimal("0.01"), max_value=Decimal("100"), places=4)

# Valid year_days values
_year_days_strat = st.sampled_from([360, 365])


# ---------------------------------------------------------------------------
# CalculationPeriod.calculate()
# ---------------------------------------------------------------------------

@settings(max_examples=200, deadline=None)
@given(
    principal=_principal_strat,
    rate=_rate_strat,
    days=st.integers(min_value=1, max_value=36500),
    year_days=_year_days_strat,
)
def test_calc_period_non_negative_result(
    principal: Decimal, rate: Decimal, days: int, year_days: int,
) -> None:
    """Interest is non-negative for non-negative inputs."""
    d = date(2020, 1, 1)
    period = CalculationPeriod(
        start_date=d,
        end_date=d + timedelta(days=days),
        principal=principal,
        rate=rate,
        days=days,
        year_days=year_days,
    )
    result = period.calculate()
    assert result >= 0


@settings(max_examples=200, deadline=None)
@given(
    principal=_principal_strat,
    rate=_rate_strat,
    year_days=_year_days_strat,
)
def test_calc_period_zero_days_gives_zero_interest(
    principal: Decimal, rate: Decimal, year_days: int,
) -> None:
    """When days <= 0, interest is always zero."""
    d = date(2020, 1, 1)
    for days_val in (0, -1, -100):
        period = CalculationPeriod(
            start_date=d,
            end_date=d,
            principal=principal,
            rate=rate,
            days=days_val,
            year_days=year_days,
        )
        result = period.calculate()
        assert result == Decimal("0")


@settings(max_examples=200, deadline=None)
@given(
    principal=_principal_strat,
    rate=_rate_strat,
    days=st.integers(min_value=1, max_value=3650),
    year_days=_year_days_strat,
)
def test_calc_period_doubling_principal_doubles_interest(
    principal: Decimal, rate: Decimal, days: int, year_days: int,
) -> None:
    """Doubling the principal doubles the interest (linearity)."""
    d = date(2020, 1, 1)
    p1 = CalculationPeriod(
        start_date=d, end_date=d + timedelta(days=days),
        principal=principal, rate=rate, days=days, year_days=year_days,
    )
    p2 = CalculationPeriod(
        start_date=d, end_date=d + timedelta(days=days),
        principal=principal * 2, rate=rate, days=days, year_days=year_days,
    )
    r1 = p1.calculate()
    r2 = p2.calculate()
    # Quantized to 2 dp, allow for rounding: r2 should be very close to 2*r1
    assert abs(r2 - 2 * r1) <= Decimal("0.02")


@settings(max_examples=200, deadline=None)
@given(
    principal=_principal_strat,
    rate=_rate_strat,
    days=st.integers(min_value=1, max_value=36500),
    year_days=_year_days_strat,
)
def test_calc_period_result_quantized_to_2dp(
    principal: Decimal, rate: Decimal, days: int, year_days: int,
) -> None:
    """Result is always quantized to 2 decimal places."""
    d = date(2020, 1, 1)
    period = CalculationPeriod(
        start_date=d, end_date=d + timedelta(days=days),
        principal=principal, rate=rate, days=days, year_days=year_days,
    )
    result = period.calculate()
    assert result == result.quantize(Decimal("0.01"))


# ---------------------------------------------------------------------------
# InterestCalculator._get_year_days
# ---------------------------------------------------------------------------

@settings(max_examples=200, deadline=None)
@given(
    d=_date_strat,
    year_days=st.sampled_from([360, 365, 366]),
)
def test_get_year_days_fixed_passthrough(d: date, year_days: int) -> None:
    """When year_days is 360 or 365, it passes through unchanged."""
    calc = InterestCalculator()
    result = calc._get_year_days(d, d, year_days)
    assert result == year_days


@settings(max_examples=200, deadline=None)
@given(d=_date_strat)
def test_get_year_days_auto_returns_365_or_366(d: date) -> None:
    """When year_days=0 (auto), returns 365 or 366 depending on leap year."""
    calc = InterestCalculator()
    result = calc._get_year_days(d, d, 0)
    expected = 366 if calendar.isleap(d.year) else 365
    assert result == expected


@settings(max_examples=200, deadline=None)
@given(d=_date_strat)
def test_get_year_days_always_in_valid_set(d: date) -> None:
    """Output is always in {360, 365, 366}."""
    calc = InterestCalculator()
    for yd in (0, 360, 365):
        result = calc._get_year_days(d, d, yd)
        assert result in {360, 365, 366}


# ---------------------------------------------------------------------------
# InterestCalculator._apply_date_inclusion
# ---------------------------------------------------------------------------

@settings(max_examples=200, deadline=None)
@given(start=_date_strat, delta=st.integers(min_value=0, max_value=3650))
def test_apply_date_inclusion_both_preserves_dates(start: date, delta: int) -> None:
    """'both' mode preserves the original start and end dates."""
    end = start + timedelta(days=delta)
    calc = InterestCalculator()
    result_start, result_end = calc._apply_date_inclusion(start, end, "both")
    assert result_start == start
    assert result_end == end


@settings(max_examples=200, deadline=None)
@given(start=_date_strat, delta=st.integers(min_value=2, max_value=3650))
def test_apply_date_inclusion_neither_narrows(start: date, delta: int) -> None:
    """'neither' mode narrows the range by 1 day on each side."""
    end = start + timedelta(days=delta)
    calc = InterestCalculator()
    result_start, result_end = calc._apply_date_inclusion(start, end, "neither")
    assert result_start == start + timedelta(days=1)
    assert result_end == end - timedelta(days=1)


@settings(max_examples=200, deadline=None)
@given(start=_date_strat, delta=st.integers(min_value=0, max_value=3650))
def test_apply_date_inclusion_start_leq_end(start: date, delta: int) -> None:
    """Output always satisfies start <= end."""
    end = start + timedelta(days=delta)
    calc = InterestCalculator()
    for mode in ("both", "start_only", "end_only", "neither"):
        result_start, result_end = calc._apply_date_inclusion(start, end, mode)
        assert result_start <= result_end, f"start > end for mode={mode}"
