"""Tests for finance services."""

from __future__ import annotations

import pytest
from datetime import date
from decimal import Decimal
from unittest.mock import MagicMock

from apps.core.exceptions import ValidationException


class TestCalculationPeriod:
    def test_calculate_basic(self):
        from apps.finance.services.calculator.interest_calculator import CalculationPeriod
        period = CalculationPeriod(
            start_date=date(2026, 1, 1),
            end_date=date(2026, 1, 31),
            principal=Decimal("10000"),
            rate=Decimal("3.85"),
            days=31,
            year_days=365,
        )
        interest = period.calculate()
        assert interest > 0

    def test_calculate_zero_days(self):
        from apps.finance.services.calculator.interest_calculator import CalculationPeriod
        period = CalculationPeriod(
            start_date=date(2026, 1, 1),
            end_date=date(2026, 1, 1),
            principal=Decimal("10000"),
            rate=Decimal("3.85"),
            days=0,
            year_days=365,
        )
        assert period.calculate() == Decimal("0")


class TestInterestCalculator:
    def _make_calculator(self, rate_service=None):
        from apps.finance.services.calculator.interest_calculator import InterestCalculator
        return InterestCalculator(rate_service=rate_service)

    def test_start_after_end_raises(self):
        calc = self._make_calculator()
        with pytest.raises(ValidationException):
            calc.calculate(
                start_date=date(2026, 2, 1),
                end_date=date(2026, 1, 1),
                principal=Decimal("10000"),
            )

    def test_zero_principal_raises(self):
        calc = self._make_calculator()
        with pytest.raises(ValidationException):
            calc.calculate(
                start_date=date(2026, 1, 1),
                end_date=date(2026, 1, 31),
                principal=Decimal("0"),
            )

    def test_custom_rate_percent(self):
        calc = self._make_calculator()
        result = calc.calculate(
            start_date=date(2026, 1, 1),
            end_date=date(2026, 1, 31),
            principal=Decimal("100000"),
            custom_rate_unit="percent",
            custom_rate_value=Decimal("3.85"),
            year_days=365,
        )
        assert result.total_interest > 0
        assert result.total_days == 31

    def test_custom_rate_permille(self):
        calc = self._make_calculator()
        result = calc.calculate(
            start_date=date(2026, 1, 1),
            end_date=date(2026, 1, 10),
            principal=Decimal("100000"),
            custom_rate_unit="permille",
            custom_rate_value=Decimal("1"),
            year_days=365,
        )
        assert result.total_interest > 0

    def test_custom_rate_permyriad(self):
        calc = self._make_calculator()
        result = calc.calculate(
            start_date=date(2026, 1, 1),
            end_date=date(2026, 1, 10),
            principal=Decimal("100000"),
            custom_rate_unit="permyriad",
            custom_rate_value=Decimal("5"),
            year_days=365,
        )
        assert result.total_interest > 0


class TestInterestCalculatorDateInclusion:
    def _make_calculator(self):
        from apps.finance.services.calculator.interest_calculator import InterestCalculator
        return InterestCalculator(rate_service=MagicMock())

    def test_both(self):
        calc = self._make_calculator()
        s, e = calc._apply_date_inclusion(date(2026, 1, 1), date(2026, 1, 31), "both")
        assert s == date(2026, 1, 1)
        assert e == date(2026, 1, 31)

    def test_neither(self):
        calc = self._make_calculator()
        s, e = calc._apply_date_inclusion(date(2026, 1, 1), date(2026, 1, 31), "neither")
        assert s == date(2026, 1, 2)
        assert e == date(2026, 1, 30)

    def test_start_only(self):
        calc = self._make_calculator()
        s, e = calc._apply_date_inclusion(date(2026, 1, 1), date(2026, 1, 31), "start_only")
        assert s == date(2026, 1, 1)
        assert e == date(2026, 1, 30)

    def test_end_only(self):
        calc = self._make_calculator()
        s, e = calc._apply_date_inclusion(date(2026, 1, 1), date(2026, 1, 31), "end_only")
        assert s == date(2026, 1, 2)
        assert e == date(2026, 1, 31)


class TestInterestCalculatorGetYearDays:
    def _make_calculator(self):
        from apps.finance.services.calculator.interest_calculator import InterestCalculator
        return InterestCalculator(rate_service=MagicMock())

    def test_fixed_365(self):
        calc = self._make_calculator()
        assert calc._get_year_days(date(2026, 1, 1), date(2026, 12, 31), 365) == 365

    def test_fixed_360(self):
        calc = self._make_calculator()
        assert calc._get_year_days(date(2026, 1, 1), date(2026, 12, 31), 360) == 360

    def test_actual_days_non_leap(self):
        calc = self._make_calculator()
        assert calc._get_year_days(date(2026, 1, 1), date(2026, 12, 31), 0) == 365

    def test_actual_days_leap(self):
        calc = self._make_calculator()
        assert calc._get_year_days(date(2024, 1, 1), date(2024, 12, 31), 0) == 366


class TestInterestCalculatorValidatePrincipalPeriods:
    def _make_calculator(self):
        from apps.finance.services.calculator.interest_calculator import InterestCalculator
        from apps.finance.services.lpr.rate_service import PrincipalPeriod
        return InterestCalculator(rate_service=MagicMock()), PrincipalPeriod

    def test_valid_periods(self):
        calc, PP = self._make_calculator()
        periods = [PP(date(2026, 1, 1), date(2026, 1, 31), Decimal("10000"))]
        calc._validate_principal_periods(periods)

    def test_zero_principal_raises(self):
        calc, PP = self._make_calculator()
        periods = [PP(date(2026, 1, 1), date(2026, 1, 31), Decimal("0"))]
        with pytest.raises(ValidationException):
            calc._validate_principal_periods(periods)

    def test_invalid_date_range_raises(self):
        calc, PP = self._make_calculator()
        periods = [PP(date(2026, 2, 1), date(2026, 1, 1), Decimal("10000"))]
        with pytest.raises(ValidationException):
            calc._validate_principal_periods(periods)


class TestInterestCalculationResultToDict:
    def test_to_dict(self):
        from apps.finance.services.calculator.interest_calculator import (
            InterestCalculationResult, CalculationPeriod
        )
        result = InterestCalculationResult(
            total_interest=Decimal("100.00"),
            total_principal=Decimal("10000"),
            total_days=30,
            periods=[],
            start_date=date(2026, 1, 1),
            end_date=date(2026, 1, 31),
        )
        d = result.to_dict()
        assert d["total_interest"] == "100.00"
        assert d["total_days"] == 30


class TestCreatePrincipalPeriods:
    def test_create_periods(self):
        from apps.finance.services.calculator.interest_calculator import InterestCalculator
        changes = [
            {"start_date": date(2026, 1, 1), "end_date": date(2026, 1, 31), "principal": "10000"},
            {"start_date": date(2026, 2, 1), "end_date": date(2026, 2, 28), "principal": "20000"},
        ]
        periods = InterestCalculator.create_principal_periods(changes)
        assert len(periods) == 2
        assert periods[0].start_date == date(2026, 1, 1)
