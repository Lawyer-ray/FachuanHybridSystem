"""Tests for finance app: interest calculator, schemas, seed data loader."""
from __future__ import annotations

import json
from datetime import date
from decimal import Decimal
from typing import Any
from unittest.mock import MagicMock, patch

import pytest

from apps.core.exceptions import ValidationException
from apps.finance.schemas.lpr_schemas import (
    CalculationPeriodSchema,
    InterestCalculateRequest,
    InterestCalculateResponse,
    LPRRateListResponse,
    LPRRateSchema,
    LPRSyncRequest,
    LPRSyncResponse,
    LPRSyncStatusResponse,
    PrincipalChangeSchema,
)
from apps.finance.services.calculator.interest_calculator import (
    CalculationPeriod,
    InterestCalculationResult,
    InterestCalculator,
)
from apps.finance.services.lpr.rate_service import LPRRateService, PrincipalPeriod, RateSegment
from apps.finance.services.lpr.sync_service import LPRData, LPRSyncService


# ---------------------------------------------------------------------------
# CalculationPeriod
# ---------------------------------------------------------------------------


class TestCalculationPeriod:
    def test_calculate_basic(self) -> None:
        period = CalculationPeriod(
            start_date=date(2023, 1, 1),
            end_date=date(2023, 1, 31),
            principal=Decimal("100000"),
            rate=Decimal("3.65"),
            days=31,
            year_days=365,
        )
        result = period.calculate()
        # 100000 * 3.65/100 * 31/365 = 310.00
        assert result == Decimal("310.00")

    def test_calculate_zero_days(self) -> None:
        period = CalculationPeriod(
            start_date=date(2023, 1, 1),
            end_date=date(2023, 1, 1),
            principal=Decimal("100000"),
            rate=Decimal("3.65"),
            days=0,
            year_days=365,
        )
        assert period.calculate() == Decimal("0")


class TestInterestCalculationResult:
    def test_to_dict(self) -> None:
        p = CalculationPeriod(
            start_date=date(2023, 1, 1),
            end_date=date(2023, 6, 30),
            principal=Decimal("100000"),
            rate=Decimal("3.65"),
            days=180,
            year_days=365,
            interest=Decimal("1800.00"),
        )
        result = InterestCalculationResult(
            total_interest=Decimal("1800.00"),
            total_principal=Decimal("100000"),
            total_days=180,
            periods=[p],
            start_date=date(2023, 1, 1),
            end_date=date(2023, 6, 30),
        )
        d = result.to_dict()
        assert d["total_interest"] == "1800.00"
        assert d["total_principal"] == "100000"
        assert d["total_days"] == 180
        assert d["start_date"] == "2023-01-01"
        assert d["end_date"] == "2023-06-30"
        assert len(d["periods"]) == 1
        assert d["periods"][0]["start_date"] == "2023-01-01"
        assert d["periods"][0]["interest"] == "1800.00"


# ---------------------------------------------------------------------------
# InterestCalculator
# ---------------------------------------------------------------------------


class TestInterestCalculatorDateInclusion:
    def test_both(self) -> None:
        calc = InterestCalculator(rate_service=MagicMock())
        s, e = calc._apply_date_inclusion(date(2023, 1, 1), date(2023, 1, 10), "both")
        assert s == date(2023, 1, 1)
        assert e == date(2023, 1, 10)

    def test_start_only(self) -> None:
        calc = InterestCalculator(rate_service=MagicMock())
        s, e = calc._apply_date_inclusion(date(2023, 1, 1), date(2023, 1, 10), "start_only")
        assert s == date(2023, 1, 1)
        assert e == date(2023, 1, 9)

    def test_end_only(self) -> None:
        calc = InterestCalculator(rate_service=MagicMock())
        s, e = calc._apply_date_inclusion(date(2023, 1, 1), date(2023, 1, 10), "end_only")
        assert s == date(2023, 1, 2)
        assert e == date(2023, 1, 10)

    def test_neither(self) -> None:
        calc = InterestCalculator(rate_service=MagicMock())
        s, e = calc._apply_date_inclusion(date(2023, 1, 1), date(2023, 1, 10), "neither")
        assert s == date(2023, 1, 2)
        assert e == date(2023, 1, 9)

    def test_neither_single_day(self) -> None:
        calc = InterestCalculator(rate_service=MagicMock())
        s, e = calc._apply_date_inclusion(date(2023, 1, 5), date(2023, 1, 5), "neither")
        # start +1 = 6, end -1 = 4, so start > end -> calc_end = calc_start
        assert s == date(2023, 1, 6)
        assert e == date(2023, 1, 6)


class TestInterestCalculatorValidation:
    def test_start_after_end_raises(self) -> None:
        calc = InterestCalculator(rate_service=MagicMock())
        with pytest.raises(ValidationException, match="开始日期"):
            calc.calculate(
                start_date=date(2023, 12, 31),
                end_date=date(2023, 1, 1),
                principal=Decimal("100000"),
            )

    def test_zero_principal_raises(self) -> None:
        calc = InterestCalculator(rate_service=MagicMock())
        with pytest.raises(ValidationException, match="本金"):
            calc.calculate(
                start_date=date(2023, 1, 1),
                end_date=date(2023, 12, 31),
                principal=Decimal("0"),
            )


class TestInterestCalculatorCustomRate:
    def test_percent_rate(self) -> None:
        calc = InterestCalculator(rate_service=MagicMock())
        result = calc.calculate(
            start_date=date(2023, 1, 1),
            end_date=date(2023, 1, 10),
            principal=Decimal("100000"),
            custom_rate_unit="percent",
            custom_rate_value=Decimal("5"),
        )
        assert result.total_interest > 0
        assert len(result.periods) == 1
        assert result.periods[0].rate == Decimal("5")

    def test_permille_rate(self) -> None:
        calc = InterestCalculator(rate_service=MagicMock())
        result = calc.calculate(
            start_date=date(2023, 1, 1),
            end_date=date(2023, 1, 10),
            principal=Decimal("100000"),
            custom_rate_unit="permille",
            custom_rate_value=Decimal("5"),
        )
        assert result.total_interest > 0
        # permille: 100000 * 5/1000 * 10 = 5000
        assert result.total_interest == Decimal("5000.00")

    def test_permyriad_rate(self) -> None:
        calc = InterestCalculator(rate_service=MagicMock())
        result = calc.calculate(
            start_date=date(2023, 1, 1),
            end_date=date(2023, 1, 10),
            principal=Decimal("100000"),
            custom_rate_unit="permyriad",
            custom_rate_value=Decimal("5"),
        )
        # permyriad: 100000 * 5/10000 * 10 = 500
        assert result.total_interest == Decimal("500.00")

    def test_unknown_unit_defaults_to_percent(self) -> None:
        calc = InterestCalculator(rate_service=MagicMock())
        result = calc.calculate(
            start_date=date(2023, 1, 1),
            end_date=date(2023, 1, 10),
            principal=Decimal("100000"),
            custom_rate_unit="unknown",
            custom_rate_value=Decimal("5"),
        )
        assert result.total_interest > 0


class TestInterestCalculatorLprMode:
    def test_lpr_mode_with_mocked_rate_service(self) -> None:
        mock_rs = MagicMock()
        mock_rs.get_rate_segments.return_value = [
            RateSegment(
                start=date(2023, 1, 1),
                end=date(2023, 12, 31),
                rate_1y=Decimal("3.65"),
                rate_5y=Decimal("4.30"),
            ),
        ]
        calc = InterestCalculator(rate_service=mock_rs)
        result = calc.calculate(
            start_date=date(2023, 1, 1),
            end_date=date(2023, 12, 31),
            principal=Decimal("100000"),
            rate_type="1y",
        )
        assert result.total_interest > 0
        mock_rs.get_rate_segments.assert_called_once()

    def test_rate_type_5y(self) -> None:
        mock_rs = MagicMock()
        mock_rs.get_rate_segments.return_value = [
            RateSegment(
                start=date(2023, 1, 1),
                end=date(2023, 12, 31),
                rate_1y=Decimal("3.65"),
                rate_5y=Decimal("4.30"),
            ),
        ]
        calc = InterestCalculator(rate_service=mock_rs)
        result = calc.calculate(
            start_date=date(2023, 1, 1),
            end_date=date(2023, 12, 31),
            principal=Decimal("100000"),
            rate_type="5y",
        )
        assert result.total_interest > 0

    def test_multiplier(self) -> None:
        mock_rs = MagicMock()
        mock_rs.get_rate_segments.return_value = [
            RateSegment(
                start=date(2023, 1, 1),
                end=date(2023, 12, 31),
                rate_1y=Decimal("3.65"),
                rate_5y=Decimal("4.30"),
            ),
        ]
        calc = InterestCalculator(rate_service=mock_rs)
        result_1x = calc.calculate(
            start_date=date(2023, 1, 1),
            end_date=date(2023, 12, 31),
            principal=Decimal("100000"),
            multiplier=Decimal("1"),
        )
        result_1_5x = calc.calculate(
            start_date=date(2023, 1, 1),
            end_date=date(2023, 12, 31),
            principal=Decimal("100000"),
            multiplier=Decimal("1.5"),
        )
        assert result_1_5x.total_interest > result_1x.total_interest

    def test_cross_segment_calculation(self) -> None:
        mock_rs = MagicMock()
        mock_rs.get_rate_segments.return_value = [
            RateSegment(
                start=date(2023, 1, 1),
                end=date(2023, 6, 30),
                rate_1y=Decimal("3.65"),
                rate_5y=Decimal("4.30"),
            ),
            RateSegment(
                start=date(2023, 7, 1),
                end=date(2023, 12, 31),
                rate_1y=Decimal("3.45"),
                rate_5y=Decimal("4.20"),
            ),
        ]
        calc = InterestCalculator(rate_service=mock_rs)
        result = calc.calculate(
            start_date=date(2023, 1, 1),
            end_date=date(2023, 12, 31),
            principal=Decimal("100000"),
        )
        assert len(result.periods) == 2

    def test_no_matching_segments_raises(self) -> None:
        mock_rs = MagicMock()
        mock_rs.get_rate_segments.return_value = []
        calc = InterestCalculator(rate_service=mock_rs)
        with pytest.raises(ValidationException, match="无法计算"):
            calc.calculate(
                start_date=date(2023, 1, 1),
                end_date=date(2023, 12, 31),
                principal=Decimal("100000"),
            )


class TestInterestCalculatorPrincipalChanges:
    def test_empty_periods_raises(self) -> None:
        calc = InterestCalculator(rate_service=MagicMock())
        with pytest.raises(ValidationException, match="不能为空"):
            calc.calculate_with_principal_changes([])

    def test_negative_principal_raises(self) -> None:
        calc = InterestCalculator(rate_service=MagicMock())
        periods = [PrincipalPeriod(date(2023, 1, 1), date(2023, 6, 30), Decimal("-100"))]
        with pytest.raises(ValidationException, match="本金"):
            calc.calculate_with_principal_changes(periods)

    def test_start_after_end_raises(self) -> None:
        calc = InterestCalculator(rate_service=MagicMock())
        periods = [PrincipalPeriod(date(2023, 6, 30), date(2023, 1, 1), Decimal("100"))]
        with pytest.raises(ValidationException, match="开始日期"):
            calc.calculate_with_principal_changes(periods)

    def test_custom_rate_mode(self) -> None:
        calc = InterestCalculator(rate_service=MagicMock())
        periods = [
            PrincipalPeriod(date(2023, 1, 1), date(2023, 3, 31), Decimal("100000")),
            PrincipalPeriod(date(2023, 4, 1), date(2023, 6, 30), Decimal("80000")),
        ]
        result = calc.calculate_with_principal_changes(
            periods,
            custom_rate_unit="percent",
            custom_rate_value=Decimal("5"),
        )
        assert result.total_interest > 0
        assert len(result.periods) >= 2


class TestInterestCalculatorYearDays:
    def test_360(self) -> None:
        mock_rs = MagicMock()
        mock_rs.get_rate_segments.return_value = [
            RateSegment(date(2023, 1, 1), date(2023, 1, 10), Decimal("3.65"), Decimal("4.30")),
        ]
        calc = InterestCalculator(rate_service=mock_rs)
        result = calc.calculate(
            start_date=date(2023, 1, 1),
            end_date=date(2023, 1, 10),
            principal=Decimal("100000"),
            year_days=360,
        )
        assert result.periods[0].year_days == 360

    def test_actual_days_leap_year(self) -> None:
        mock_rs = MagicMock()
        mock_rs.get_rate_segments.return_value = [
            RateSegment(date(2024, 2, 1), date(2024, 2, 29), Decimal("3.65"), Decimal("4.30")),
        ]
        calc = InterestCalculator(rate_service=mock_rs)
        result = calc.calculate(
            start_date=date(2024, 2, 1),
            end_date=date(2024, 2, 29),
            principal=Decimal("100000"),
            year_days=0,
        )
        assert result.periods[0].year_days == 366

    def test_actual_days_non_leap_year(self) -> None:
        mock_rs = MagicMock()
        mock_rs.get_rate_segments.return_value = [
            RateSegment(date(2023, 3, 1), date(2023, 3, 31), Decimal("3.65"), Decimal("4.30")),
        ]
        calc = InterestCalculator(rate_service=mock_rs)
        result = calc.calculate(
            start_date=date(2023, 3, 1),
            end_date=date(2023, 3, 31),
            principal=Decimal("100000"),
            year_days=0,
        )
        assert result.periods[0].year_days == 365


class TestCreatePrincipalPeriods:
    def test_basic(self) -> None:
        changes = [
            {"start_date": date(2023, 1, 1), "end_date": date(2023, 3, 31), "principal": 100000},
            {"start_date": date(2023, 4, 1), "end_date": date(2023, 6, 30), "principal": 80000},
        ]
        periods = InterestCalculator.create_principal_periods(changes)
        assert len(periods) == 2
        assert periods[0].principal == Decimal("100000")
        assert periods[0].start_date == date(2023, 1, 1)

    def test_sorted_by_start_date(self) -> None:
        changes = [
            {"start_date": date(2023, 4, 1), "end_date": date(2023, 6, 30), "principal": 80000},
            {"start_date": date(2023, 1, 1), "end_date": date(2023, 3, 31), "principal": 100000},
        ]
        periods = InterestCalculator.create_principal_periods(changes)
        assert periods[0].start_date == date(2023, 1, 1)


# ---------------------------------------------------------------------------
# LPRSyncService (parse methods only - no DB/network)
# ---------------------------------------------------------------------------


class TestLPRSyncServiceParseDate:
    def test_cn_format(self) -> None:
        svc = LPRSyncService()
        assert svc._parse_date("2024年3月20日") == date(2024, 3, 20)

    def test_dash_format(self) -> None:
        svc = LPRSyncService()
        assert svc._parse_date("2024-03-20") == date(2024, 3, 20)

    def test_slash_format(self) -> None:
        svc = LPRSyncService()
        assert svc._parse_date("2024/3/20") == date(2024, 3, 20)

    def test_invalid(self) -> None:
        svc = LPRSyncService()
        assert svc._parse_date("not a date") is None

    def test_invalid_date_values(self) -> None:
        svc = LPRSyncService()
        assert svc._parse_date("2024年13月40日") is None


class TestLPRSyncServiceParseRate:
    def test_with_percent(self) -> None:
        svc = LPRSyncService()
        assert svc._parse_rate("3.45%") == Decimal("3.45")

    def test_without_percent(self) -> None:
        svc = LPRSyncService()
        assert svc._parse_rate("3.45") == Decimal("3.45")

    def test_large_value_divides_by_100(self) -> None:
        svc = LPRSyncService()
        # > 10 → treated as whole-number percentage like 345%
        result = svc._parse_rate("345")
        assert result == Decimal("345") / Decimal("100")

    def test_invalid(self) -> None:
        svc = LPRSyncService()
        assert svc._parse_rate("abc") is None


class TestLPRSyncServiceInit:
    def test_source(self) -> None:
        svc = LPRSyncService()
        assert svc.source == "中国人民银行官网"


# ---------------------------------------------------------------------------
# LPRData
# ---------------------------------------------------------------------------


class TestLPRData:
    def test_creation(self) -> None:
        d = LPRData(effective_date=date(2024, 1, 20), rate_1y=Decimal("3.45"), rate_5y=Decimal("4.20"))
        assert d.effective_date == date(2024, 1, 20)
        assert d.rate_1y == Decimal("3.45")


# ---------------------------------------------------------------------------
# Schemas
# ---------------------------------------------------------------------------


class TestSchemas:
    def test_lpr_rate_schema(self) -> None:
        schema = LPRRateSchema(
            id=1,
            effective_date=date(2024, 1, 20),
            rate_1y=Decimal("3.45"),
            rate_5y=Decimal("4.20"),
            source="央行",
            is_auto_synced=True,
            created_at="2024-01-20T00:00:00",
            updated_at="2024-01-20T00:00:00",
        )
        assert schema.rate_1y == Decimal("3.45")

    def test_lpr_rate_list_response(self) -> None:
        resp = LPRRateListResponse(items=[], total=0)
        assert resp.total == 0

    def test_lpr_sync_request_default(self) -> None:
        req = LPRSyncRequest()
        assert req.force is False

    def test_lpr_sync_response(self) -> None:
        resp = LPRSyncResponse(success=True, message="ok", created=1, updated=2, skipped=3)
        assert resp.created == 1

    def test_lpr_sync_status_response(self) -> None:
        resp = LPRSyncStatusResponse(
            latest_rate_date=date(2024, 1, 20),
            total_records=10,
            auto_synced_records=8,
            manual_records=2,
        )
        assert resp.total_records == 10

    def test_principal_change_schema(self) -> None:
        schema = PrincipalChangeSchema(
            start_date=date(2023, 1, 1),
            end_date=date(2023, 3, 31),
            principal=Decimal("100000"),
        )
        assert schema.principal == Decimal("100000")

    def test_interest_calculate_request_defaults(self) -> None:
        req = InterestCalculateRequest()
        assert req.rate_mode == "lpr"
        assert req.rate_type == "1y"
        assert req.year_days == 360

    def test_interest_calculate_response(self) -> None:
        resp = InterestCalculateResponse(success=True)
        assert resp.success is True
        assert resp.total_interest is None

    def test_calculation_period_schema(self) -> None:
        schema = CalculationPeriodSchema(
            start_date=date(2023, 1, 1),
            end_date=date(2023, 1, 10),
            principal=Decimal("100000"),
            rate=Decimal("3.65"),
            days=10,
            year_days=365,
            interest=Decimal("100.00"),
        )
        assert schema.days == 10
