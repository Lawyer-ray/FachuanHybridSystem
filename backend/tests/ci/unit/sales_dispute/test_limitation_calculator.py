"""诉讼时效与还款冲抵计算单元测试。"""
from __future__ import annotations

from datetime import date
from decimal import Decimal

import pytest

from apps.sales_dispute.services.calculation.limitation_calculator_service import (
    InterruptionEvent,
    InterruptionType,
    LimitationCalcParams,
    LimitationCalculatorService,
    _add_months,
)


# ── _add_months ────────────────────────────────────────────────────────────

def test_add_months_normal() -> None:
    """正常加月数。"""
    assert _add_months(date(2024, 1, 15), 6) == date(2024, 7, 15)


def test_add_months_year_overflow() -> None:
    """跨年加月数。"""
    assert _add_months(date(2024, 10, 15), 6) == date(2025, 4, 15)


def test_add_months_day_overflow() -> None:
    """月末溢出修正。"""
    # 1月31日加1个月 -> 2月29日（2024闰年）
    assert _add_months(date(2024, 1, 31), 1) == date(2024, 2, 29)


def test_add_months_zero() -> None:
    """加0个月不变。"""
    assert _add_months(date(2024, 3, 15), 0) == date(2024, 3, 15)


# ── LimitationCalculatorService ────────────────────────────────────────────

@pytest.fixture
def svc() -> LimitationCalculatorService:
    return LimitationCalculatorService()


def test_normal_status(svc: LimitationCalculatorService) -> None:
    """基准日起算3年，距离到期 > 90天，状态 normal。"""
    params = LimitationCalcParams(
        last_claim_date=date(2024, 1, 1),
        interruptions=[],
    )
    result = svc.calculate(params, as_of=date(2024, 6, 1))
    assert result.status == "normal"
    assert result.remaining_days > 90
    assert result.risk_warning == ""


def test_expiring_soon_status(svc: LimitationCalculatorService) -> None:
    """距到期 <= 90天，状态 expiring_soon。"""
    params = LimitationCalcParams(
        last_claim_date=date(2022, 1, 1),
        interruptions=[],
    )
    # 到期日 2025-01-01，as_of 2024-11-15 => 距到期 47 天
    result = svc.calculate(params, as_of=date(2024, 11, 15))
    assert result.status == "expiring_soon"
    assert result.remaining_days <= 90
    assert result.remaining_days > 0
    assert "建议尽快" in result.risk_warning


def test_expired_status(svc: LimitationCalculatorService) -> None:
    """已过期。"""
    params = LimitationCalcParams(
        last_claim_date=date(2020, 1, 1),
        interruptions=[],
    )
    result = svc.calculate(params, as_of=date(2025, 1, 2))
    assert result.status == "expired"
    assert result.remaining_days <= 0
    assert "已届满" in result.risk_warning


def test_interruption_resets_base_date(svc: LimitationCalculatorService) -> None:
    """中断事由重置基准日。"""
    params = LimitationCalcParams(
        last_claim_date=date(2020, 1, 1),
        interruptions=[
            InterruptionEvent(InterruptionType.COLLECTION, date(2023, 6, 15)),
        ],
    )
    result = svc.calculate(params, as_of=date(2024, 1, 1))
    # 基准日应为 2023-06-15，到期日 2026-06-15
    assert result.base_date == date(2023, 6, 15)
    assert result.expiry_date == date(2026, 6, 15)
    assert result.status == "normal"


def test_multiple_interruptions_uses_latest(svc: LimitationCalculatorService) -> None:
    """多个中断事由使用最后日期。"""
    params = LimitationCalcParams(
        last_claim_date=date(2020, 1, 1),
        interruptions=[
            InterruptionEvent(InterruptionType.COLLECTION, date(2022, 3, 10)),
            InterruptionEvent(InterruptionType.DEBTOR_PROMISE, date(2023, 8, 20)),
            InterruptionEvent(InterruptionType.LAWSUIT, date(2023, 1, 5)),
        ],
    )
    result = svc.calculate(params, as_of=date(2024, 1, 1))
    assert result.base_date == date(2023, 8, 20)


def test_guarantee_debtor_calculation(svc: LimitationCalculatorService) -> None:
    """保证人保证期间计算。"""
    params = LimitationCalcParams(
        last_claim_date=date(2024, 1, 1),
        interruptions=[],
        guarantee_debtor=True,
        principal_due_date=date(2024, 6, 1),
    )
    result = svc.calculate(params, as_of=date(2024, 1, 1))
    # 保证期间 = principal_due_date + 6个月
    assert result.guarantee_expiry_date == date(2024, 12, 1)


def test_no_guarantee_debtor(svc: LimitationCalculatorService) -> None:
    """无保证人时保证期间为 None。"""
    params = LimitationCalcParams(
        last_claim_date=date(2024, 1, 1),
        interruptions=[],
        guarantee_debtor=False,
    )
    result = svc.calculate(params, as_of=date(2024, 1, 1))
    assert result.guarantee_expiry_date is None


def test_guarantee_no_due_date(svc: LimitationCalculatorService) -> None:
    """有保证人但无到期日时保证期间为 None。"""
    params = LimitationCalcParams(
        last_claim_date=date(2024, 1, 1),
        interruptions=[],
        guarantee_debtor=True,
        principal_due_date=None,
    )
    result = svc.calculate(params, as_of=date(2024, 1, 1))
    assert result.guarantee_expiry_date is None


def test_interruption_type_values() -> None:
    """各种中断事由类型可创建。"""
    for itype in InterruptionType:
        event = InterruptionEvent(itype, date(2024, 1, 1))
        assert event.event_type == itype
