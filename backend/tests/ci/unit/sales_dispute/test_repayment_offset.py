"""还款冲抵引擎单元测试。"""
from __future__ import annotations

from datetime import date
from decimal import Decimal

import pytest

from apps.sales_dispute.services.calculation.repayment_offset_service import (
    DebtItem,
    RepaymentOffsetService,
)


@pytest.fixture
def svc() -> RepaymentOffsetService:
    return RepaymentOffsetService(interest_calculator=None)


# ── offset_single_debt ─────────────────────────────────────────────────────

def test_offset_fully_covers_all(svc: RepaymentOffsetService) -> None:
    """还款完全覆盖费用、利息、本金。"""
    fee, interest, principal, remaining = svc.offset_single_debt(
        payment_amount=Decimal("300"),
        fee=Decimal("50"),
        interest=Decimal("100"),
        principal=Decimal("1000"),
    )
    assert fee == Decimal("50")
    assert interest == Decimal("100")
    assert principal == Decimal("150")
    assert remaining == Decimal("850")


def test_offset_partial_fee(svc: RepaymentOffsetService) -> None:
    """还款不足以覆盖全部费用。"""
    fee, interest, principal, remaining = svc.offset_single_debt(
        payment_amount=Decimal("30"),
        fee=Decimal("50"),
        interest=Decimal("100"),
        principal=Decimal("1000"),
    )
    assert fee == Decimal("30")
    assert interest == Decimal("0")
    assert principal == Decimal("0")
    assert remaining == Decimal("1000")


def test_offset_partial_interest(svc: RepaymentOffsetService) -> None:
    """还款覆盖全部费用但不足以覆盖全部利息。"""
    fee, interest, principal, remaining = svc.offset_single_debt(
        payment_amount=Decimal("120"),
        fee=Decimal("50"),
        interest=Decimal("100"),
        principal=Decimal("1000"),
    )
    assert fee == Decimal("50")
    assert interest == Decimal("70")
    assert principal == Decimal("0")
    assert remaining == Decimal("1000")


def test_offset_zero_payment(svc: RepaymentOffsetService) -> None:
    """还款金额为 0 不冲抵任何东西。"""
    fee, interest, principal, remaining = svc.offset_single_debt(
        payment_amount=Decimal("0"),
        fee=Decimal("50"),
        interest=Decimal("100"),
        principal=Decimal("1000"),
    )
    assert fee == Decimal("0")
    assert interest == Decimal("0")
    assert principal == Decimal("0")
    assert remaining == Decimal("1000")


def test_offset_exact_cover(svc: RepaymentOffsetService) -> None:
    """还款精确覆盖费用+利息+本金。"""
    fee, interest, principal, remaining = svc.offset_single_debt(
        payment_amount=Decimal("1150"),
        fee=Decimal("50"),
        interest=Decimal("100"),
        principal=Decimal("1000"),
    )
    assert fee == Decimal("50")
    assert interest == Decimal("100")
    assert principal == Decimal("1000")
    assert remaining == Decimal("0")


def test_offset_excess_payment(svc: RepaymentOffsetService) -> None:
    """还款超过总债务时只冲抵实际金额。"""
    fee, interest, principal, remaining = svc.offset_single_debt(
        payment_amount=Decimal("2000"),
        fee=Decimal("50"),
        interest=Decimal("100"),
        principal=Decimal("1000"),
    )
    assert fee == Decimal("50")
    assert interest == Decimal("100")
    assert principal == Decimal("1000")
    assert remaining == Decimal("0")


# ── offset_multiple_debts ──────────────────────────────────────────────────

def test_offset_multiple_debts_default_order(svc: RepaymentOffsetService) -> None:
    """多笔债务默认按法定优先级排序冲抵。"""
    debts = [
        DebtItem(principal=Decimal("500"), accrued_fee=Decimal("10"), accrued_interest=Decimal("20"),
                 due_date=date(2024, 6, 1), has_guarantee=True, debt_id="b"),
        DebtItem(principal=Decimal("500"), accrued_fee=Decimal("10"), accrued_interest=Decimal("20"),
                 due_date=date(2024, 1, 1), has_guarantee=False, debt_id="a"),
    ]
    result = svc.offset_multiple_debts(Decimal("500"), debts)
    # 应先冲抵 "a"（先到期、无担保）
    assert result.details[0].debt_id == "a"
    assert result.details[0].offset_fee == Decimal("10")


def test_offset_multiple_debts_custom_order(svc: RepaymentOffsetService) -> None:
    """多笔债务按自定义顺序冲抵。"""
    debts = [
        DebtItem(principal=Decimal("500"), accrued_fee=Decimal("10"), accrued_interest=Decimal("20"),
                 due_date=date(2024, 6, 1), has_guarantee=True, debt_id="b"),
        DebtItem(principal=Decimal("500"), accrued_fee=Decimal("10"), accrued_interest=Decimal("20"),
                 due_date=date(2024, 1, 1), has_guarantee=False, debt_id="a"),
    ]
    result = svc.offset_multiple_debts(Decimal("500"), debts, custom_order=["b", "a"])
    assert result.details[0].debt_id == "b"


def test_offset_multiple_debts_insufficient_payment(svc: RepaymentOffsetService) -> None:
    """还款不足以覆盖所有债务时后续债务不变。"""
    debts = [
        DebtItem(principal=Decimal("500"), accrued_fee=Decimal("10"), accrued_interest=Decimal("20"),
                 due_date=date(2024, 1, 1), has_guarantee=False, debt_id="a"),
        DebtItem(principal=Decimal("500"), accrued_fee=Decimal("10"), accrued_interest=Decimal("20"),
                 due_date=date(2024, 6, 1), has_guarantee=True, debt_id="b"),
    ]
    result = svc.offset_multiple_debts(Decimal("50"), debts)
    # 第一笔债务冲抵了部分
    assert result.details[0].offset_fee == Decimal("10")
    assert result.details[0].offset_interest == Decimal("20")
    assert result.details[0].offset_principal == Decimal("20")
    # 第二笔债务未被冲抵
    assert result.details[1].offset_fee == Decimal("0")
    assert result.details[1].offset_interest == Decimal("0")
    assert result.details[1].offset_principal == Decimal("0")


def test_offset_multiple_debts_empty(svc: RepaymentOffsetService) -> None:
    """无债务时返回空结果。"""
    result = svc.offset_multiple_debts(Decimal("100"), [])
    assert result.details == []
    assert result.remaining_debts == []


def test_offset_multiple_debts_zero_payment(svc: RepaymentOffsetService) -> None:
    """还款为 0 时所有债务不变。"""
    debts = [
        DebtItem(principal=Decimal("500"), accrued_fee=Decimal("10"), accrued_interest=Decimal("20"),
                 due_date=date(2024, 1, 1), has_guarantee=False, debt_id="a"),
    ]
    result = svc.offset_multiple_debts(Decimal("0"), debts)
    assert result.details[0].offset_fee == Decimal("0")
    assert result.remaining_debts[0].principal == Decimal("500")


def test_offset_debt_priority_by_due_date(svc: RepaymentOffsetService) -> None:
    """法定排序：先到期的债务优先。"""
    debts = [
        DebtItem(principal=Decimal("100"), accrued_fee=Decimal("0"), accrued_interest=Decimal("0"),
                 due_date=date(2024, 12, 1), has_guarantee=False, debt_id="late"),
        DebtItem(principal=Decimal("100"), accrued_fee=Decimal("0"), accrued_interest=Decimal("0"),
                 due_date=date(2024, 1, 1), has_guarantee=False, debt_id="early"),
    ]
    result = svc.offset_multiple_debts(Decimal("100"), debts)
    assert result.details[0].debt_id == "early"


def test_offset_debt_priority_by_guarantee(svc: RepaymentOffsetService) -> None:
    """法定排序：同到期日，无担保优先。"""
    debts = [
        DebtItem(principal=Decimal("100"), accrued_fee=Decimal("0"), accrued_interest=Decimal("0"),
                 due_date=date(2024, 1, 1), has_guarantee=True, debt_id="guaranteed"),
        DebtItem(principal=Decimal("100"), accrued_fee=Decimal("0"), accrued_interest=Decimal("0"),
                 due_date=date(2024, 1, 1), has_guarantee=False, debt_id="unguaranteed"),
    ]
    result = svc.offset_multiple_debts(Decimal("100"), debts)
    assert result.details[0].debt_id == "unguaranteed"
