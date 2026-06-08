"""Tests for sales_dispute.services.calculation.interest_calculator_service."""
from __future__ import annotations

from datetime import date
from decimal import Decimal
from unittest.mock import MagicMock, patch

import pytest

from apps.sales_dispute.services.calculation.interest_calculator_service import (
    BatchDelivery,
    InterestCalcParams,
    InterestCalcResult,
    InterestCalculatorService,
    InterestStartType,
    LPR_WATERSHED,
    OLD_BENCHMARK_RATE_1Y,
    RateType,
    SegmentDetail,
)


class TestEnums:
    def test_interest_start_type_values(self) -> None:
        assert InterestStartType.AGREED_DATE.value == "agreed_date"
        assert InterestStartType.DEMAND_NOTICE.value == "demand_notice"
        assert InterestStartType.BATCH_DELIVERY.value == "batch_delivery"

    def test_rate_type_values(self) -> None:
        assert RateType.LPR.value == "lpr"
        assert RateType.AGREED_RATE.value == "agreed_rate"
        assert RateType.PENALTY_FIXED.value == "penalty_fixed"
        assert RateType.PENALTY_DAILY.value == "penalty_daily"


class TestBatchDelivery:
    def test_defaults(self) -> None:
        bd = BatchDelivery(delivery_date=date(2024, 1, 1), amount=Decimal("10000"))
        assert bd.payment_date is None


class TestSegmentDetail:
    def test_creation(self) -> None:
        seg = SegmentDetail(
            start_date=date(2024, 1, 1),
            end_date=date(2024, 2, 1),
            days=31,
            rate=Decimal("3.85"),
            interest=Decimal("100.00"),
        )
        assert seg.days == 31
        assert seg.rate == Decimal("3.85")


class TestInterestCalcResult:
    def test_defaults(self) -> None:
        result = InterestCalcResult()
        assert result.total_interest == Decimal("0")
        assert result.segments == []
        assert result.warnings == []


class TestInterestCalculatorService:
    def setup_method(self) -> None:
        self.service = InterestCalculatorService()

    def test_lpr_watershed_constant(self) -> None:
        assert date(2019, 8, 20) == LPR_WATERSHED

    def test_old_benchmark_rate(self) -> None:
        assert Decimal("4.35") == OLD_BENCHMARK_RATE_1Y

    def test_calculate_start_after_end_returns_zero(self) -> None:
        params = InterestCalcParams(
            principal=Decimal("100000"),
            start_date=date(2024, 6, 1),
            end_date=date(2024, 1, 1),
        )
        result = self.service.calculate(params)
        assert result.total_interest == Decimal("0")

    def test_calculate_same_day_returns_zero(self) -> None:
        params = InterestCalcParams(
            principal=Decimal("100000"),
            start_date=date(2024, 6, 1),
            end_date=date(2024, 6, 1),
        )
        result = self.service.calculate(params)
        assert result.total_interest == Decimal("0")

    def test_calculate_agreed_rate(self) -> None:
        params = InterestCalcParams(
            principal=Decimal("100000"),
            start_date=date(2024, 1, 1),
            end_date=date(2024, 2, 1),
            rate_type=RateType.AGREED_RATE,
            agreed_rate=Decimal("5.0"),
        )
        result = self.service.calculate(params)
        assert result.total_interest > Decimal("0")
        assert len(result.segments) == 1

    def test_calculate_agreed_rate_zero_days(self) -> None:
        params = InterestCalcParams(
            principal=Decimal("100000"),
            start_date=date(2024, 1, 1),
            end_date=date(2024, 1, 1),
            rate_type=RateType.AGREED_RATE,
            agreed_rate=Decimal("5.0"),
        )
        result = self.service.calculate(params)
        assert result.total_interest == Decimal("0")

    def test_calculate_agreed_rate_no_rate_falls_back_to_lpr(self) -> None:
        lpr_service = MagicMock()
        lpr_service.get_rate_segments.return_value = [
            MagicMock(start=date(2024, 1, 1), end=date(2024, 6, 1), rate_1y=Decimal("3.45"), rate_5y=Decimal("3.95"))
        ]
        service = InterestCalculatorService(lpr_rate_service=lpr_service)

        params = InterestCalcParams(
            principal=Decimal("100000"),
            start_date=date(2024, 1, 1),
            end_date=date(2024, 6, 1),
            rate_type=RateType.AGREED_RATE,
            agreed_rate=None,
        )
        result = service.calculate(params)
        assert result.total_interest > Decimal("0")

    def test_calculate_penalty_fixed(self) -> None:
        params = InterestCalcParams(
            principal=Decimal("100000"),
            start_date=date(2024, 1, 1),
            end_date=date(2024, 6, 1),
            rate_type=RateType.PENALTY_FIXED,
            penalty_amount=Decimal("5000"),
        )
        result = self.service.calculate(params)
        assert result.total_interest == Decimal("5000.00")
        assert "违约金" in result.warnings[1]

    def test_calculate_penalty_fixed_none(self) -> None:
        params = InterestCalcParams(
            principal=Decimal("100000"),
            start_date=date(2024, 1, 1),
            end_date=date(2024, 6, 1),
            rate_type=RateType.PENALTY_FIXED,
            penalty_amount=None,
        )
        result = self.service.calculate(params)
        assert result.total_interest == Decimal("0")

    def test_calculate_penalty_daily(self) -> None:
        params = InterestCalcParams(
            principal=Decimal("100000"),
            start_date=date(2024, 1, 1),
            end_date=date(2024, 1, 11),
            rate_type=RateType.PENALTY_DAILY,
            penalty_daily_rate=Decimal("1"),  # 1 basis point
        )
        result = self.service.calculate(params)
        assert result.total_interest > Decimal("0")
        assert len(result.segments) == 1

    def test_calculate_penalty_daily_none(self) -> None:
        params = InterestCalcParams(
            principal=Decimal("100000"),
            start_date=date(2024, 1, 1),
            end_date=date(2024, 6, 1),
            rate_type=RateType.PENALTY_DAILY,
            penalty_daily_rate=None,
        )
        result = self.service.calculate(params)
        assert result.total_interest == Decimal("0")

    def test_calculate_penalty_daily_zero_days(self) -> None:
        params = InterestCalcParams(
            principal=Decimal("100000"),
            start_date=date(2024, 1, 1),
            end_date=date(2024, 1, 1),
            rate_type=RateType.PENALTY_DAILY,
            penalty_daily_rate=Decimal("1"),
        )
        result = self.service.calculate(params)
        assert result.total_interest == Decimal("0")

    def test_calculate_lpr_post_watershed(self) -> None:
        lpr_service = MagicMock()
        lpr_service.get_rate_segments.return_value = [
            MagicMock(start=date(2024, 1, 1), end=date(2024, 6, 1), rate_1y=Decimal("3.45"), rate_5y=Decimal("3.95"))
        ]
        service = InterestCalculatorService(lpr_rate_service=lpr_service)

        params = InterestCalcParams(
            principal=Decimal("100000"),
            start_date=date(2024, 1, 1),
            end_date=date(2024, 6, 1),
            rate_type=RateType.LPR,
        )
        result = service.calculate(params)
        assert result.total_interest > Decimal("0")
        assert "买卖合同" in result.warnings[0]

    def test_calculate_lpr_pre_watershed(self) -> None:
        lpr_service = MagicMock()
        lpr_service.get_rate_segments.return_value = []
        service = InterestCalculatorService(lpr_rate_service=lpr_service)

        params = InterestCalcParams(
            principal=Decimal("100000"),
            start_date=date(2019, 1, 1),
            end_date=date(2019, 6, 1),
            rate_type=RateType.LPR,
        )
        result = service.calculate(params)
        # Pre-watershed uses OLD_BENCHMARK_RATE_1Y
        assert result.total_interest > Decimal("0")

    def test_calculate_lpr_crosses_watershed(self) -> None:
        lpr_service = MagicMock()
        lpr_service.get_rate_segments.return_value = [
            MagicMock(start=date(2019, 8, 20), end=date(2020, 1, 1), rate_1y=Decimal("4.20"), rate_5y=Decimal("4.85"))
        ]
        service = InterestCalculatorService(lpr_rate_service=lpr_service)

        params = InterestCalcParams(
            principal=Decimal("100000"),
            start_date=date(2019, 6, 1),
            end_date=date(2020, 1, 1),
            rate_type=RateType.LPR,
        )
        result = service.calculate(params)
        assert result.total_interest > Decimal("0")
        # Should have segments from both pre and post watershed
        assert len(result.segments) >= 1

    def test_determine_start_date_agreed_with_payment_date(self) -> None:
        params = InterestCalcParams(
            principal=Decimal("100000"),
            start_date=date(2024, 1, 1),
            end_date=date(2024, 6, 1),
            interest_start_type=InterestStartType.AGREED_DATE,
            agreed_payment_date=date(2024, 2, 15),
        )
        start = self.service._determine_start_date(params)
        assert start == date(2024, 2, 16)  # Next day

    def test_determine_start_date_agreed_without_payment_date(self) -> None:
        params = InterestCalcParams(
            principal=Decimal("100000"),
            start_date=date(2024, 1, 1),
            end_date=date(2024, 6, 1),
            interest_start_type=InterestStartType.AGREED_DATE,
            agreed_payment_date=None,
        )
        start = self.service._determine_start_date(params)
        assert start == date(2024, 1, 1)

    def test_determine_start_date_demand_notice(self) -> None:
        params = InterestCalcParams(
            principal=Decimal("100000"),
            start_date=date(2024, 1, 1),
            end_date=date(2024, 6, 1),
            interest_start_type=InterestStartType.DEMAND_NOTICE,
            demand_date=date(2024, 3, 1),
            reasonable_period_days=15,
        )
        start = self.service._determine_start_date(params)
        assert start == date(2024, 3, 17)  # demand_date + 15 + 1

    def test_determine_start_date_demand_no_date(self) -> None:
        params = InterestCalcParams(
            principal=Decimal("100000"),
            start_date=date(2024, 1, 1),
            end_date=date(2024, 6, 1),
            interest_start_type=InterestStartType.DEMAND_NOTICE,
            demand_date=None,
        )
        start = self.service._determine_start_date(params)
        assert start == date(2024, 1, 1)

    def test_batch_delivery_calculation(self) -> None:
        params = InterestCalcParams(
            principal=Decimal("100000"),
            start_date=date(2024, 1, 1),
            end_date=date(2024, 6, 1),
            rate_type=RateType.AGREED_RATE,
            agreed_rate=Decimal("5.0"),
            interest_start_type=InterestStartType.BATCH_DELIVERY,
            batch_deliveries=[
                BatchDelivery(delivery_date=date(2024, 1, 1), amount=Decimal("50000"), payment_date=date(2024, 2, 1)),
                BatchDelivery(delivery_date=date(2024, 3, 1), amount=Decimal("50000")),
            ],
        )
        result = self.service.calculate(params)
        assert result.total_interest > Decimal("0")

    def test_batch_delivery_empty_list(self) -> None:
        params = InterestCalcParams(
            principal=Decimal("100000"),
            start_date=date(2024, 1, 1),
            end_date=date(2024, 6, 1),
            rate_type=RateType.AGREED_RATE,
            agreed_rate=Decimal("5.0"),
            interest_start_type=InterestStartType.BATCH_DELIVERY,
            batch_deliveries=[],
        )
        result = self.service.calculate(params)
        assert result.total_interest == Decimal("0")

    def test_batch_delivery_start_after_end_skipped(self) -> None:
        params = InterestCalcParams(
            principal=Decimal("100000"),
            start_date=date(2024, 1, 1),
            end_date=date(2024, 1, 15),
            rate_type=RateType.AGREED_RATE,
            agreed_rate=Decimal("5.0"),
            interest_start_type=InterestStartType.BATCH_DELIVERY,
            batch_deliveries=[
                BatchDelivery(delivery_date=date(2024, 1, 14), amount=Decimal("50000")),
                BatchDelivery(delivery_date=date(2024, 1, 10), amount=Decimal("50000"), payment_date=date(2024, 1, 14)),
            ],
        )
        result = self.service.calculate(params)
        # Both batches start on 2024-01-15 which equals end_date, so zero
        assert result.total_interest == Decimal("0")
