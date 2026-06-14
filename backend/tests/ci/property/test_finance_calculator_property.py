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


# ---------------------------------------------------------------------------
# LPRRateService.is_data_current – date comparison logic
# ---------------------------------------------------------------------------
#
# is_data_current() queries the DB via get_latest_rate(). We cannot test the
# full method without a database, but we CAN unit-test the date comparison
# logic by extracting it into a standalone function tested below.
#


def _is_data_current_logic(today: date, effective_date: date) -> bool:
    """Pure extraction of the date comparison logic from LPRRateService.is_data_current."""
    ld = effective_date
    if ld.year == today.year and ld.month == today.month:
        return True
    if today.day < 20:
        if ld.year == today.year and ld.month == today.month - 1:
            return True
        if today.month == 1 and ld.month == 12 and ld.year == today.year - 1:
            return True
    return False


@settings(max_examples=200, deadline=None)
@given(year=st.integers(min_value=2000, max_value=2099), month=st.integers(min_value=1, max_value=12))
def test_is_data_current_same_year_month_always_true(year: int, month: int) -> None:
    """When today and effective_date share the same year+month, result is True."""
    today = date(year, month, 10)
    effective = date(year, month, 15)
    assert _is_data_current_logic(today, effective) is True


@settings(max_examples=200, deadline=None)
@given(
    year=st.integers(min_value=2000, max_value=2099),
    month=st.integers(min_value=2, max_value=12),
)
def test_is_data_current_before_20th_prev_month_true(year: int, month: int) -> None:
    """Before the 20th, effective_date from previous month of same year is current."""
    today = date(year, month, 5)
    effective = date(year, month - 1, 20)
    assert _is_data_current_logic(today, effective) is True


@settings(max_examples=200, deadline=None)
@given(year=st.integers(min_value=2000, max_value=2099))
def test_is_data_current_before_20th_jan_prev_dec_true(year: int) -> None:
    """Before Jan 20, effective_date from Dec of previous year is current."""
    today = date(year, 1, 10)
    effective = date(year - 1, 12, 20)
    assert _is_data_current_logic(today, effective) is True


@settings(max_examples=200, deadline=None)
@given(year=st.integers(min_value=2000, max_value=2099))
def test_is_data_current_deterministic(year: int) -> None:
    """Same inputs always produce the same output."""
    today = date(year, 6, 15)
    effective = date(year, 5, 20)
    r1 = _is_data_current_logic(today, effective)
    r2 = _is_data_current_logic(today, effective)
    assert r1 == r2
