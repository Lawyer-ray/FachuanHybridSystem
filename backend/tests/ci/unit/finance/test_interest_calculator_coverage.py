"""Tests for finance/services/calculator/interest_calculator.py — additional branches.

Covers: _calculate_cross_segments (multiple segments, no overlap), _calculate_with_custom_rate
with default unit, calculate_with_principal_changes, to_dict with periods.
"""
from __future__ import annotations

from datetime import date
from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from apps.core.exceptions import ValidationException
from apps.finance.services.calculator.interest_calculator import (
    CalculationPeriod,
    InterestCalculationResult,
    InterestCalculator,
)
from apps.finance.services.lpr.rate_service import PrincipalPeriod


def _make_rate_segment(start, end, r1y="3.45", r5y="3.95"):
    return SimpleNamespace(start=start, end=end, rate_1y=Decimal(r1y), rate_5y=Decimal(r5y))


class TestCalculationPeriodEdgeCases:
    def test_negative_days_returns_zero(self):
        period = CalculationPeriod(
            start_date=date(2026, 5, 1),
            end_date=date(2026, 4, 1),
            principal=Decimal("10000"),
            rate=Decimal("3.85"),
            days=-30,
            year_days=365,
        )
        assert period.calculate() == Decimal("0")

    def test_exact_one_day(self):
        period = CalculationPeriod(
            start_date=date(2026, 1, 1),
            end_date=date(2026, 1, 1),
            principal=Decimal("100000"),
            rate=Decimal("3.60"),
            days=1,
            year_days=360,
        )
        interest = period.calculate()
        # 100000 * 3.60/100 * 1 / 360 = 10.00
        assert interest == Decimal("10.00")


class TestInterestCalculatorCalculateWithMockedRateService:
    def _make_calc(self, rate_segments):
        mock_rs = MagicMock()
        mock_rs.get_rate_segments.return_value = rate_segments
        return InterestCalculator(rate_service=mock_rs)

    def test_single_segment(self):
        segments = [_make_rate_segment(date(2026, 1, 1), date(2026, 12, 31))]
        calc = self._make_calc(segments)
        result = calc.calculate(
            start_date=date(2026, 1, 1),
            end_date=date(2026, 3, 31),
            principal=Decimal("100000"),
            rate_type="1y",
        )
        assert result.total_interest > 0
        assert result.total_days > 0
        assert len(result.periods) >= 1

    def test_5y_rate_type(self):
        segments = [_make_rate_segment(date(2026, 1, 1), date(2026, 12, 31))]
        calc = self._make_calc(segments)
        result = calc.calculate(
            start_date=date(2026, 1, 1),
            end_date=date(2026, 6, 30),
            principal=Decimal("200000"),
            rate_type="5y",
        )
        assert result.total_interest > 0

    def test_multiplier(self):
        segments = [_make_rate_segment(date(2026, 1, 1), date(2026, 12, 31))]
        calc = self._make_calc(segments)
        result_1x = calc.calculate(
            start_date=date(2026, 1, 1),
            end_date=date(2026, 3, 31),
            principal=Decimal("100000"),
            multiplier=Decimal("1"),
        )
        result_15x = calc.calculate(
            start_date=date(2026, 1, 1),
            end_date=date(2026, 3, 31),
            principal=Decimal("100000"),
            multiplier=Decimal("1.5"),
        )
        assert result_15x.total_interest > result_1x.total_interest

    def test_no_overlapping_segments_raises(self):
        # Rate segment doesn't overlap with date range
        segments = [_make_rate_segment(date(2025, 1, 1), date(2025, 6, 30))]
        calc = self._make_calc(segments)
        with pytest.raises(ValidationException) as exc_info:
            calc.calculate(
                start_date=date(2026, 1, 1),
                end_date=date(2026, 3, 31),
                principal=Decimal("100000"),
            )
        assert exc_info.value.code == "CALCULATION_FAILED"

    def test_multiple_rate_segments(self):
        segments = [
            _make_rate_segment(date(2026, 1, 1), date(2026, 3, 31), "3.45"),
            _make_rate_segment(date(2026, 4, 1), date(2026, 12, 31), "3.65"),
        ]
        calc = self._make_calc(segments)
        result = calc.calculate(
            start_date=date(2026, 1, 1),
            end_date=date(2026, 6, 30),
            principal=Decimal("100000"),
        )
        assert len(result.periods) == 2
        assert result.total_interest > 0


class TestInterestCalculatorCustomRateDefault:
    def test_custom_rate_with_unknown_unit(self):
        calc = InterestCalculator(rate_service=MagicMock())
        result = calc.calculate(
            start_date=date(2026, 1, 1),
            end_date=date(2026, 1, 10),
            principal=Decimal("100000"),
            custom_rate_unit="unknown_unit",
            custom_rate_value=Decimal("5"),
        )
        assert result.total_interest > 0
        # Unknown unit falls into default branch; year_days = 0 since it's not "percent"
        assert result.periods[0].year_days == 0

    def test_to_dict_with_periods(self):
        calc = InterestCalculator(rate_service=MagicMock())
        result = calc.calculate(
            start_date=date(2026, 1, 1),
            end_date=date(2026, 1, 10),
            principal=Decimal("100000"),
            custom_rate_unit="percent",
            custom_rate_value=Decimal("3.65"),
            year_days=365,
        )
        d = result.to_dict()
        assert "periods" in d
        assert len(d["periods"]) == 1
        assert "rate_unit" not in d["periods"][0]  # to_dict doesn't include rate_unit


class TestCalculateWithPrincipalChanges:
    def test_single_period(self):
        calc = InterestCalculator(rate_service=MagicMock())
        periods = [PrincipalPeriod(date(2026, 1, 1), date(2026, 1, 31), Decimal("100000"))]
        result = calc.calculate_with_principal_changes(
            periods,
            custom_rate_unit="percent",
            custom_rate_value=Decimal("3.65"),
        )
        assert result.total_interest > 0

    def test_empty_periods_raises(self):
        calc = InterestCalculator(rate_service=MagicMock())
        with pytest.raises(ValidationException) as exc_info:
            calc.calculate_with_principal_changes([])
        assert exc_info.value.code == "EMPTY_PRINCIPAL_PERIODS"

    def test_multiple_periods(self):
        mock_rs = MagicMock()
        mock_rs.get_rate_segments.return_value = [
            _make_rate_segment(date(2026, 1, 1), date(2026, 12, 31), "3.45"),
        ]
        calc = InterestCalculator(rate_service=mock_rs)
        periods = [
            PrincipalPeriod(date(2026, 1, 1), date(2026, 3, 31), Decimal("100000")),
            PrincipalPeriod(date(2026, 4, 1), date(2026, 6, 30), Decimal("200000")),
        ]
        result = calc.calculate_with_principal_changes(periods, rate_type="1y")
        assert len(result.periods) == 2

    def test_periods_sorted_by_start_date(self):
        mock_rs = MagicMock()
        mock_rs.get_rate_segments.return_value = [
            _make_rate_segment(date(2026, 1, 1), date(2026, 12, 31)),
        ]
        calc = InterestCalculator(rate_service=mock_rs)
        periods = [
            PrincipalPeriod(date(2026, 4, 1), date(2026, 6, 30), Decimal("200000")),
            PrincipalPeriod(date(2026, 1, 1), date(2026, 3, 31), Decimal("100000")),
        ]
        result = calc.calculate_with_principal_changes(periods, rate_type="1y")
        # First period should start from Jan 1
        assert result.start_date == date(2026, 1, 1)

    def test_validation_fails_on_invalid_period(self):
        calc = InterestCalculator(rate_service=MagicMock())
        periods = [
            PrincipalPeriod(date(2026, 2, 1), date(2026, 1, 1), Decimal("100000")),
        ]
        with pytest.raises(ValidationException) as exc_info:
            calc.calculate_with_principal_changes(periods)
        assert "日期" in exc_info.value.message

    def test_zero_principal_in_period_raises(self):
        calc = InterestCalculator(rate_service=MagicMock())
        periods = [
            PrincipalPeriod(date(2026, 1, 1), date(2026, 1, 31), Decimal("0")),
        ]
        with pytest.raises(ValidationException) as exc_info:
            calc.calculate_with_principal_changes(periods)
        assert "本金" in exc_info.value.message


class TestCreatePrincipalPeriods:
    def test_with_default_principal(self):
        changes = [
            {"start_date": date(2026, 1, 1), "end_date": date(2026, 1, 31)},
        ]
        periods = InterestCalculator.create_principal_periods(changes, default_principal=Decimal("50000"))
        assert periods[0].principal == Decimal("50000")

    def test_sorted_by_start_date(self):
        changes = [
            {"start_date": date(2026, 6, 1), "end_date": date(2026, 6, 30), "principal": "20000"},
            {"start_date": date(2026, 1, 1), "end_date": date(2026, 1, 31), "principal": "10000"},
        ]
        periods = InterestCalculator.create_principal_periods(changes)
        assert periods[0].start_date == date(2026, 1, 1)
        assert periods[1].start_date == date(2026, 6, 1)
