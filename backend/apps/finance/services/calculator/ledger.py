"""房贷逾期计算：还款账本（冲抵核销、提前还款、溢缴款）.

函数均以 Simulation 为状态宿主，读改写其欠款批次与累计金额。
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal
from typing import TYPE_CHECKING

from apps.finance.services.calculator.accrual import accrue
from apps.finance.services.calculator.mortgage_models import PAYMENT_TYPE_PREPAYMENT, AllocationDetail, _Lot
from apps.finance.services.calculator.schedule import reschedule

if TYPE_CHECKING:
    from apps.finance.services.calculator.mortgage_models import PaymentRecord
    from apps.finance.services.calculator.simulation import Simulation

ALLOC_TOTAL_ATTRS = (
    "to_penalty",
    "to_penalty_lump",
    "to_interest",
    "to_compound",
    "to_principal",
    "to_fee",
)


def pay_toward(sim: Simulation, key: str, amount: Decimal, pay_date: date, alloc: AllocationDetail) -> Decimal:
    """向指定 bucket 支付，返回实际消耗金额."""
    remaining = amount
    if key == "penalty":
        outstanding = sim.penalty_accrued_total - sim.penalty_paid
        take = min(remaining, outstanding)
        if take > 0:
            sim.penalty_paid += take
            alloc.to_penalty += take
            remaining -= take
    elif key == "penalty_lump":
        outstanding = sim.lump_penalty_total - sim.lump_penalty_paid
        take = min(remaining, outstanding)
        if take > 0:
            sim.lump_penalty_paid += take
            alloc.to_penalty_lump += take
            remaining -= take
    elif key == "fee":
        outstanding = sim.fee_base_total - sim.fees_paid
        take = min(remaining, outstanding)
        if take > 0:
            sim.fees_paid += take
            alloc.to_fee += take
            remaining -= take
    elif key == "interest":
        for lot in sim.interest_lots:
            if remaining <= 0:
                break
            take = min(remaining, lot.amount)
            if take > 0:
                lot.amount -= take
                if lot.amount <= 0 and lot.cleared_date is None:
                    lot.cleared_date = pay_date
                alloc.to_interest += take
                alloc.touched_due_dates.add(lot.due_date)
                alloc.interest_by_due[lot.due_date] = alloc.interest_by_due.get(lot.due_date, Decimal("0")) + take
                remaining -= take
    elif key == "compound":
        outstanding = sim.compound_accrued_total + sim.penalty_compound_total - sim.compound_paid
        take = min(remaining, outstanding)
        if take > 0:
            sim.compound_paid += take
            alloc.to_compound += take
            remaining -= take
    elif key == "principal":
        for lot in sim.principal_lots:
            if remaining <= 0:
                break
            take = min(remaining, lot.amount)
            if take > 0:
                lot.amount -= take
                sim.balance -= take
                if lot.amount <= 0 and lot.cleared_date is None:
                    lot.cleared_date = pay_date
                alloc.to_principal += take
                alloc.touched_due_dates.add(lot.due_date)
                alloc.principal_by_due[lot.due_date] = alloc.principal_by_due.get(lot.due_date, Decimal("0")) + take
                remaining -= take
    sim.interest_lots = [lot for lot in sim.interest_lots if lot.amount > 0]
    sim.principal_lots = [lot for lot in sim.principal_lots if lot.amount > 0]
    return amount - remaining


def allocate_by_order(sim: Simulation, amount: Decimal, pay_date: date) -> tuple[Decimal, AllocationDetail]:
    """按冲抵顺序核销，返回 (剩余金额, 冲抵明细)."""
    remaining = amount
    alloc = AllocationDetail(payment_date=pay_date, amount=amount)
    for key in sim.order:
        if remaining <= 0:
            break
        consumed = pay_toward(sim, key, remaining, pay_date, alloc)
        remaining -= consumed
    return remaining, alloc


def attach_allocation(sim: Simulation, alloc: AllocationDetail) -> None:
    """把冲抵明细按批次归属挂到受影响的违约期行."""
    row_by_due = {row.due_date: row for row in sim.default_rows}
    for due_date in sorted(alloc.touched_due_dates):
        row = row_by_due.get(due_date)
        if row is not None:
            row.allocations.append(alloc)


def process_payment(sim: Simulation, rec: PaymentRecord) -> None:
    """处理单笔还款：先按冲抵顺序核销，余款入溢缴；提前还款冲减本金并重排."""
    accrue(sim, sim.prev_event_date, rec.payment_date)
    sim.prev_event_date = rec.payment_date

    if rec.payment_type == PAYMENT_TYPE_PREPAYMENT:
        remaining_amt = rec.amount
        alloc = AllocationDetail(payment_date=rec.payment_date, amount=rec.amount)
        for key in sim.order:
            if remaining_amt <= 0:
                break
            if key == "principal":
                break
            consumed = pay_toward(sim, key, remaining_amt, rec.payment_date, alloc)
            remaining_amt -= consumed
        if remaining_amt < rec.amount:
            attach_allocation(sim, alloc)
        if remaining_amt > 0:
            if sim.prepayment_compensation_rate is not None:
                sim.prepayment_compensation += remaining_amt * sim.prepayment_compensation_rate / Decimal("100")
            sim.balance -= remaining_amt
            if sim.balance <= 0:
                sim.balance = Decimal("0")
                sim.settled = True
            else:
                reschedule(sim, rec.payment_date)
    else:
        leftover, alloc = allocate_by_order(sim, rec.amount, rec.payment_date)
        if leftover > 0:
            sim.credit += leftover
        if any(getattr(alloc, attr) for attr in ALLOC_TOTAL_ATTRS):
            attach_allocation(sim, alloc)


def _alloc_dummy(sim: Simulation) -> _Lot:  # pragma: no cover - 仅占位避免未用导入
    return sim.principal_lots[0] if sim.principal_lots else _Lot(due_date=date.min, amount=Decimal("0"))
