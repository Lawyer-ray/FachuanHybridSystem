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


class TestPrincipalPeriodOverlappingValidation:
    """同一笔本金的时间段重叠校验。

    交叉分段按「每段独立计息」求和：不同基数时间窗允许重叠（判决书多基数
    各自起算的常见写法，各自独立计息即正确总和）；同一笔本金出现在两个
    重叠窗口才会把这笔钱计两次（含闭区间首尾共享日），必须拒绝。
    """

    def test_overlapping_same_principal_raises(self):
        calc = InterestCalculator(rate_service=MagicMock())
        periods = [
            PrincipalPeriod(date(2026, 1, 1), date(2026, 1, 31), Decimal("100000")),
            PrincipalPeriod(date(2026, 1, 20), date(2026, 2, 28), Decimal("100000")),
        ]
        with pytest.raises(ValidationException) as exc_info:
            calc.calculate_with_principal_changes(periods)
        assert exc_info.value.code == "OVERLAPPING_PERIODS"
        assert "重叠" in exc_info.value.message
        assert "第2段" in exc_info.value.message

    def test_shared_boundary_day_same_principal_raises(self):
        """闭区间计息下前段结束日=后段开始日会双计当天，同样判重叠。"""
        calc = InterestCalculator(rate_service=MagicMock())
        periods = [
            PrincipalPeriod(date(2026, 1, 1), date(2026, 1, 31), Decimal("100000")),
            PrincipalPeriod(date(2026, 1, 31), date(2026, 2, 28), Decimal("100000")),
        ]
        with pytest.raises(ValidationException) as exc_info:
            calc.calculate_with_principal_changes(periods)
        assert exc_info.value.code == "OVERLAPPING_PERIODS"

    def test_non_adjacent_same_principal_overlap_raises(self):
        """同一笔本金的重叠段排序后未必相邻（中间隔着其它基数的段），同样拒绝。"""
        calc = InterestCalculator(rate_service=MagicMock())
        periods = [
            PrincipalPeriod(date(2026, 1, 1), date(2026, 6, 30), Decimal("100000")),
            PrincipalPeriod(date(2026, 2, 1), date(2026, 3, 31), Decimal("120000")),
            PrincipalPeriod(date(2026, 3, 1), date(2026, 4, 30), Decimal("100000")),
        ]
        with pytest.raises(ValidationException) as exc_info:
            calc.calculate_with_principal_changes(periods)
        assert exc_info.value.code == "OVERLAPPING_PERIODS"

    def test_overlapping_different_principals_pass(self):
        """不同基数各自独立计息，时间窗重叠是合法语义（执行请求多基数场景）。"""
        calc = InterestCalculator(rate_service=MagicMock())
        periods = [
            PrincipalPeriod(date(2026, 1, 1), date(2026, 1, 31), Decimal("100000")),
            PrincipalPeriod(date(2026, 1, 20), date(2026, 2, 28), Decimal("120000")),
        ]
        result = calc.calculate_with_principal_changes(
            periods, custom_rate_unit="percent", custom_rate_value=Decimal("3.65")
        )
        # 重叠段按各自窗口独立计天（31 + 40），重叠日历天对两段各计一次
        assert result.total_days == 31 + 40

    def test_independent_bases_allows_same_amount_overlap(self):
        """independent_bases=True：等额也可能是不同笔钱（判决多基数条款），跳过同额重叠检查。"""
        calc = InterestCalculator(rate_service=MagicMock())
        periods = [
            PrincipalPeriod(date(2024, 9, 5), date(2026, 3, 23), Decimal("10000000")),
            PrincipalPeriod(date(2024, 9, 14), date(2026, 3, 23), Decimal("10000000")),
        ]
        result = calc.calculate_with_principal_changes(
            periods,
            custom_rate_unit="percent",
            custom_rate_value=Decimal("6"),
            independent_bases=True,
        )
        assert result.total_interest > 0

    def test_adjacent_legal_periods_pass(self):
        """合法相邻段（前一天结束、后一天开始）不受影响。"""
        calc = InterestCalculator(rate_service=MagicMock())
        periods = [
            PrincipalPeriod(date(2026, 1, 1), date(2026, 1, 31), Decimal("100000")),
            PrincipalPeriod(date(2026, 2, 1), date(2026, 2, 28), Decimal("120000")),
        ]
        result = calc.calculate_with_principal_changes(
            periods, custom_rate_unit="percent", custom_rate_value=Decimal("3.65")
        )
        assert result.total_days == 31 + 28

    def test_gap_between_periods_pass(self):
        """段间允许空隙，不算重叠。"""
        calc = InterestCalculator(rate_service=MagicMock())
        periods = [
            PrincipalPeriod(date(2026, 1, 1), date(2026, 1, 10), Decimal("100000")),
            PrincipalPeriod(date(2026, 2, 1), date(2026, 2, 10), Decimal("120000")),
        ]
        result = calc.calculate_with_principal_changes(
            periods, custom_rate_unit="percent", custom_rate_value=Decimal("3.65")
        )
        assert result.total_days == 10 + 10


class TestDateInclusionOnPrincipalChanges:
    """date_inclusion 只作用于整体首尾，不得对每个本金段独立收缩"""

    _KWARGS = {"custom_rate_unit": "percent", "custom_rate_value": Decimal("3.65")}

    def test_two_adjacent_months_neither_shrinks_only_overall_edges(self):
        """1 月整月 + 2 月整月相邻段 + neither：总天数只比 both 少 2（而非每段各少 2 共 4）。"""
        calc = InterestCalculator(rate_service=MagicMock())
        periods = [
            PrincipalPeriod(date(2026, 1, 1), date(2026, 1, 31), Decimal("100000")),
            PrincipalPeriod(date(2026, 2, 1), date(2026, 2, 28), Decimal("100000")),
        ]
        result_both = calc.calculate_with_principal_changes(periods, date_inclusion="both", **self._KWARGS)
        result_neither = calc.calculate_with_principal_changes(periods, date_inclusion="neither", **self._KWARGS)
        assert result_both.total_days == 31 + 28
        assert result_neither.total_days == 31 + 28 - 2

    def test_neither_keeps_middle_boundary_intact(self):
        """neither 下只有第一段 start 与最后一段 end 收缩，中间分界天保留。"""
        calc = InterestCalculator(rate_service=MagicMock())
        periods = [
            PrincipalPeriod(date(2026, 1, 1), date(2026, 1, 31), Decimal("100000")),
            PrincipalPeriod(date(2026, 2, 1), date(2026, 2, 28), Decimal("100000")),
        ]
        result = calc.calculate_with_principal_changes(periods, date_inclusion="neither", **self._KWARGS)
        assert [p.start_date for p in result.periods] == [date(2026, 1, 2), date(2026, 2, 1)]
        assert [p.end_date for p in result.periods] == [date(2026, 1, 31), date(2026, 2, 27)]

    def test_start_only_and_end_only_shrink_respective_overall_edge(self):
        """start_only 只收整体结束日，end_only 只收整体开始日。"""
        calc = InterestCalculator(rate_service=MagicMock())
        periods = [
            PrincipalPeriod(date(2026, 1, 1), date(2026, 1, 31), Decimal("100000")),
            PrincipalPeriod(date(2026, 2, 1), date(2026, 2, 28), Decimal("100000")),
        ]
        result_start_only = calc.calculate_with_principal_changes(periods, date_inclusion="start_only", **self._KWARGS)
        assert result_start_only.total_days == 31 + 28 - 1
        assert result_start_only.periods[-1].end_date == date(2026, 2, 27)

        result_end_only = calc.calculate_with_principal_changes(periods, date_inclusion="end_only", **self._KWARGS)
        assert result_end_only.total_days == 31 + 28 - 1
        assert result_end_only.periods[0].start_date == date(2026, 1, 2)

    def test_fixed_principal_calculate_behavior_unchanged(self):
        """固定本金 calculate() 单段路径（首尾即整体）四种模式行为保持不变。"""
        calc = InterestCalculator(rate_service=MagicMock())
        base = {
            "start_date": date(2026, 1, 1),
            "end_date": date(2026, 1, 31),
            "principal": Decimal("100000"),
            "custom_rate_unit": "percent",
            "custom_rate_value": Decimal("3.65"),
        }
        assert calc.calculate(date_inclusion="both", **base).total_days == 31
        assert calc.calculate(date_inclusion="neither", **base).total_days == 29
        assert calc.calculate(date_inclusion="start_only", **base).total_days == 30
        assert calc.calculate(date_inclusion="end_only", **base).total_days == 30


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
