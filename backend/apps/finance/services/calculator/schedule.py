"""房贷逾期计算：摊销计划数学（等额本息/等额本金、重排、到期日、状态判定）.

纯计算函数：不持有状态。需要读写运行状态的 reschedule 接收 Simulation 作为参数。
"""

from __future__ import annotations

import math
from datetime import date, timedelta
from decimal import ROUND_CEILING, Decimal
from typing import TYPE_CHECKING

from apps.finance.services.calculator.mortgage_models import (
    CENT,
    PREPAY_REDUCE_PAYMENT,
    PREPAY_SHORTEN_TERM,
    REPAYMENT_EQUAL_INSTALLMENT,
    REPAYMENT_EQUAL_PRINCIPAL,
    STATUS_PAID,
    STATUS_PARTIAL,
    STATUS_UNPAID,
    add_months,
)

if TYPE_CHECKING:
    from apps.finance.services.calculator.simulation import Simulation


def annuity_payment(bal: Decimal, annual: Decimal, months: int) -> Decimal:
    """等额本息月供公式."""
    i = annual / Decimal("100") / Decimal("12")
    if i == 0:
        return (bal / Decimal(months)).quantize(CENT, rounding=ROUND_CEILING)
    factor = (Decimal(1) + i) ** months
    return bal * i * factor / (factor - Decimal(1))


def first_due_date(start_date: date, payment_day: int | None) -> date:
    """首期扣款日：payment_day 指定日（1-31）或放款日对应日，至少在放款日之后一个月."""
    day = payment_day or start_date.day
    first_candidate = add_months(start_date.replace(day=1), 1)
    # 钳制目标：次月的月末天数（29-31 在无对应日的月份收拢到月末）
    next_month_first = add_months(first_candidate, 1)
    last_day = (next_month_first - timedelta(days=1)).day
    first_candidate = first_candidate.replace(day=min(day, last_day))
    if first_candidate <= start_date:
        first_candidate = add_months(first_candidate, 1)
    return first_candidate


def is_offday(d: date, holidays: set[date]) -> bool:
    """是否非工作日：周六/周日 或 传入的法定节假日."""
    if d.weekday() >= 5:
        return True
    return d in holidays


def shift_workday(d: date, holidays: set[date]) -> date:
    """扣款日逢周末/节假日顺延到下一工作日（逐日后移）."""
    while is_offday(d, holidays):
        d += timedelta(days=1)
    return d


def status(shortfall_principal: Decimal, shortfall_interest: Decimal) -> str:
    """根据本期欠付情况判定期次状态."""
    if shortfall_principal <= 0 and shortfall_interest <= 0:
        return STATUS_PAID
    if shortfall_principal >= 0 and shortfall_interest >= 0:
        return STATUS_PARTIAL if (shortfall_principal < 1 or shortfall_interest < 1) else STATUS_UNPAID
    return STATUS_PARTIAL


def reschedule(sim: Simulation, pay_date: date) -> None:
    """提前还款后重排后续计划（读改写 sim 上的摊销状态）."""
    sim.reschedule_count += 1
    if sim.remaining_periods <= 0 or sim.balance <= 0:
        return
    i = sim.current_rate / Decimal("100") / Decimal("12")
    if sim.repayment_method == REPAYMENT_EQUAL_PRINCIPAL:
        if sim.prepayment_handling == PREPAY_REDUCE_PAYMENT:
            sim.principal_part_plan = sim.balance / Decimal(sim.remaining_periods)
        return
    if sim.prepayment_handling == PREPAY_SHORTEN_TERM:
        if sim.monthly_payment <= i * sim.balance:
            sim.warnings.append("提前还款金额不足以在剩余期限内摊清（月供低于当期利息），已按月供递减方式重排")
            sim.prepayment_handling = PREPAY_REDUCE_PAYMENT
            sim.monthly_payment = annuity_payment(sim.balance, sim.current_rate, sim.remaining_periods)
            return
        growth = (Decimal(1) + i) ** 1
        ratio = Decimal(1) - i * sim.balance / sim.monthly_payment
        if ratio <= 0:
            sim.monthly_payment = annuity_payment(sim.balance, sim.current_rate, sim.remaining_periods)
            return
        months_needed = math.ceil(-math.log(float(ratio)) / math.log(float(growth)))
        sim.remaining_periods = min(months_needed, sim.remaining_periods)
    else:
        sim.monthly_payment = annuity_payment(sim.balance, sim.current_rate, sim.remaining_periods)
