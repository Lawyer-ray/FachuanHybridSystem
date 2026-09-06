"""房贷逾期计算：模拟状态与主驱动循环.

Simulation 持有一次模拟的全部可变状态（欠款批次、累计金额、摊销进度、还款账本），
并将不可变配置（利率解析器、冲抵顺序、停息区间等）一并挂载，供
validation / rate_resolver / schedule / accrual / ledger / claim 各模块读改写。

simulate() 是主驱动：按期间推进，处理还款事件、按日计息、加速到期与尾期截算。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, timedelta
from decimal import Decimal
from typing import TYPE_CHECKING

from apps.finance.services.calculator.mortgage_models import (
    DEFAULT_ALLOCATION_ORDER,
    FIRST_PERIOD_PRORATE,
    REPAYMENT_EQUAL_INSTALLMENT,
    AllocationDetail,
    ClaimSummary,
    DefaultRow,
    PaymentRecord,
    ScheduleRow,
    _Lot,
    _q,
    _str_money,
    add_months,
    unpaused_days,
)

if TYPE_CHECKING:
    from apps.finance.services.calculator.rate_resolver import RateResolver

__all__ = ["Simulation", "simulate", "announce_acceleration"]


@dataclass
class Simulation:
    """房贷逾期模拟的完整状态宿主（配置 + 可变状态）.

    配置字段在构造后不变；计息/冲抵/重排等模块通过方法或直读直写上述字段完成演进。
    """

    # ---- 贷款与利率配置（不变） ----
    principal: Decimal
    start_date: date
    term_months: int
    repayment_method: str
    payment_day: int | None
    penalty_mode: str
    penalty_multiplier: Decimal
    penalty_rate: Decimal | None
    compound_on_interest: bool
    compound_on_penalty: bool
    compound_method: str
    grace_period_days: int
    first_period_interest: str
    charge_interest_on_payment_day: bool
    interest_cut_inclusive: bool
    year_days: int
    lump_penalty_rate: Decimal | None
    lump_penalty_amount: Decimal | None
    lump_penalty_threshold_days: int
    shift_due_to_workday: bool
    holidays_set: set[date]
    prepayment_handling: str
    prepayment_compensation_rate: Decimal | None
    other_fees: list[dict]
    step_up_rate: Decimal | None
    step_up_trigger_days: int
    rounding_mode: str
    claim_mode: str
    fees_offset: bool
    accelerate_date: date | None
    accelerate_grace_days: int
    cap_penalty_annual: Decimal | None
    cap_total_mode: str
    cap_total_value: Decimal
    pause_ranges: list[tuple[date, date]]
    claim: date
    boundary_plus: int
    resolver: RateResolver

    # ---- 可变契约字段（charge/claim 用的只读快表固化在构造期） ----
    order: list[str] = field(default_factory=lambda: list(DEFAULT_ALLOCATION_ORDER))
    allocations: list = field(default_factory=list)
    payments: list[PaymentRecord] = field(default_factory=list)

    # ---- 可变状态 ----
    balance: Decimal = field(default_factory=lambda: Decimal("0"))
    remaining_periods: int = 0
    monthly_payment: Decimal = field(default_factory=lambda: Decimal("0"))
    principal_part_plan: Decimal = field(default_factory=lambda: Decimal("0"))
    credit: Decimal = field(default_factory=lambda: Decimal("0"))
    current_rate: Decimal = field(default_factory=lambda: Decimal("0"))
    prev_event_date: date | None = None
    settled: bool = False
    period_no: int = 0
    payment_idx: int = 0
    reschedule_count: int = 0
    prepayment_compensation: Decimal = field(default_factory=lambda: Decimal("0"))
    accelerated: bool = False
    accelerate_penalty_start: date | None = None
    first_due: date | None = None
    fee_base_total: Decimal = field(default_factory=lambda: Decimal("0"))
    fees_paid: Decimal = field(default_factory=lambda: Decimal("0"))
    lump_penalty_total: Decimal = field(default_factory=lambda: Decimal("0"))
    lump_penalty_paid: Decimal = field(default_factory=lambda: Decimal("0"))
    lump_outstanding: Decimal = field(default_factory=lambda: Decimal("0"))
    lump_charged_due: set[date] = field(default_factory=set)
    penalty_accrued_total: Decimal = field(default_factory=lambda: Decimal("0"))
    penalty_paid: Decimal = field(default_factory=lambda: Decimal("0"))
    compound_accrued_total: Decimal = field(default_factory=lambda: Decimal("0"))
    compound_paid: Decimal = field(default_factory=lambda: Decimal("0"))
    penalty_compound_total: Decimal = field(default_factory=lambda: Decimal("0"))
    compound_interest_accrued: Decimal = field(default_factory=lambda: Decimal("0"))
    penalty_compound_accrued: Decimal = field(default_factory=lambda: Decimal("0"))
    compound_days_total: int = 0
    first_penalty_start: date | None = None
    principal_lots: list[_Lot] = field(default_factory=list)
    interest_lots: list[_Lot] = field(default_factory=list)
    overdue_start_dates: dict[date, date] = field(default_factory=dict)
    schedule_rows: list[ScheduleRow] = field(default_factory=list)
    default_rows: list[DefaultRow] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)

    # ---- 汇总产物（由 claim / simulate 填充） ----
    stub_result: ClaimSummary | None = None
    claim_summary: ClaimSummary | None = None
    claim_taken: str = ""
    capped_total: bool = False


def announce_acceleration(sim: Simulation) -> None:
    """公告加速到期：全部剩余本金转为到期本金批次，停止后续按月摊销.

    罚息/复利自加速宽限期届满次日起对全额本金按日计收；合同利息只结算到加速日为止。
    """
    sim.accelerated = True
    if sim.accelerate_date is None:
        return
    if sim.balance > 0:
        sim.principal_lots.append(_Lot(due_date=sim.accelerate_date, amount=sim.balance))
        start = sim.accelerate_penalty_start
        if start is not None:
            sim.overdue_start_dates[sim.accelerate_date] = start
            if sim.first_penalty_start is None or start < sim.first_penalty_start:
                sim.first_penalty_start = start
        if sim.prev_event_date is not None and sim.prev_event_date < sim.accelerate_date:
            stub_days = unpaused_days(sim.prev_event_date, sim.accelerate_date, sim.pause_ranges)
            annual = sim.resolver.contract_annual(sim.prev_event_date)
            stub_interest = _q(sim.balance * annual / Decimal("100") * stub_days / Decimal(sim.year_days))
            if stub_interest > 0:
                sim.interest_lots.append(_Lot(due_date=sim.accelerate_date, amount=stub_interest))
    sim.warnings.append(
        f"已于 {sim.accelerate_date} 公告加速到期：全部剩余本金 {_str_money(sim.balance)} 转为已到期本金，"
        f"罚息/复利自 {sim.accelerate_penalty_start} 起对全额按日计收"
        f"（加速后宽限 {sim.accelerate_grace_days} 天）"
    )


def simulate(sim: Simulation) -> None:
    """主驱动：截算早于首期扣款日的场景，或推进还款计划直至截止日.

    所有副作用都落在 sim 上（批次、累计金额、计划/违约行、溢缴、加速状态）。
    若首期扣款日早于截止日且无可生成期次，则写入 sim.stub_result 并直接返回。
    """
    from apps.finance.services.calculator.accrual import accrue
    from apps.finance.services.calculator.ledger import process_payment
    from apps.finance.services.calculator.schedule import annuity_payment, first_due_date, shift_workday, status

    first_due = first_due_date(sim.start_date, sim.payment_day)
    if sim.shift_due_to_workday:
        first_due = shift_workday(first_due, sim.holidays_set)
    sim.first_due = first_due

    if first_due > sim.claim:
        # 起诉日早于首期扣款日：仅截算一段合同利息
        stub_days = unpaused_days(sim.start_date, sim.claim, sim.pause_ranges) + sim.boundary_plus
        annual = sim.resolver.contract_annual(sim.start_date)
        stub_interest = _q(sim.principal * annual / Decimal("100") * stub_days / Decimal(sim.year_days))
        sim.stub_result = ClaimSummary(
            claim_date=sim.claim,
            outstanding_principal=sim.principal,
            unpaid_interest=stub_interest,
            penalty_interest=Decimal("0"),
            compound_interest=Decimal("0"),
            total_claim=sim.principal + stub_interest,
            daily_accrual=Decimal("0"),
        )
        sim.warnings.append("计算截止日早于首期扣款日，仅按天截算合同利息，无违约金额")
        return

    while not sim.settled:
        sim.period_no += 1
        due_date = add_months(first_due, sim.period_no - 1)
        if sim.shift_due_to_workday:
            due_date = shift_workday(due_date, sim.holidays_set)
        grace_end = due_date + timedelta(days=sim.grace_period_days) if sim.grace_period_days else due_date

        # 0) 到期日边界触发加速到期：全部本金转到期本金，停止摊销
        if not sim.accelerated and sim.accelerate_date is not None and due_date >= sim.accelerate_date:
            announce_acceleration(sim)
            if sim.accelerated:
                sim.settled = True
                break

        # 1) 处理本期内（上一事件日, 宽限期截止日] 的还款事件
        while sim.payment_idx < len(sim.payments) and sim.payments[sim.payment_idx].payment_date <= grace_end:
            rec = sim.payments[sim.payment_idx]
            sim.payment_idx += 1
            process_payment(sim, rec)
            if sim.settled:
                break

        if sim.settled:
            break

        if due_date > sim.claim:
            sim.period_no -= 1
            break

        # 2) 罚息/复利按日累计至本期扣款日
        if sim.prev_event_date is not None:
            accrue(sim, sim.prev_event_date, due_date)
        sim.prev_event_date = due_date

        # 3) 计息：本期利率（以扣款日为准）
        annual = sim.resolver.contract_annual(due_date)
        i = annual / Decimal("100") / Decimal("12")
        rate_changed = annual != sim.current_rate and sim.period_no > 1
        sim.current_rate = annual

        # 4) 本期应还
        is_final_period = sim.remaining_periods <= 1
        if sim.repayment_method == REPAYMENT_EQUAL_INSTALLMENT:
            if sim.period_no == 1 or rate_changed:
                if rate_changed:
                    sim.reschedule_count += 1
                sim.monthly_payment = annuity_payment(sim.balance, annual, sim.remaining_periods)
            if sim.period_no == 1 and sim.first_period_interest == FIRST_PERIOD_PRORATE:
                stub_days = Decimal((due_date - sim.start_date).days)
                interest_due = _q(sim.balance * annual / Decimal("100") * stub_days / Decimal(sim.year_days))
            else:
                interest_due = _q(sim.balance * i)
            principal_due = sim.monthly_payment - interest_due
            if principal_due > sim.balance:
                principal_due = sim.balance
            # 末期清尾：摊销公式累计误差（如首期按天计息与月供公式的口径差）
            # 由最后一期全额吞掉，确保按计划还满全部期数后本金清零
            if is_final_period:
                principal_due = sim.balance
        else:
            if sim.period_no == 1 and sim.first_period_interest == FIRST_PERIOD_PRORATE:
                stub_days = Decimal((due_date - sim.start_date).days)
                interest_due = _q(sim.balance * annual / Decimal("100") * stub_days / Decimal(sim.year_days))
            else:
                interest_due = _q(sim.balance * i)
            principal_due = sim.principal_part_plan if sim.principal_part_plan <= sim.balance else sim.balance

        if principal_due <= 0:
            sim.period_no -= 1
            break

        # 4) 用溢缴款支付本期应还（按冲抵顺序在 利息/本金 之间分配）
        due_alloc = AllocationDetail(payment_date=due_date, amount=sim.credit, direct=True)
        credit_remaining = sim.credit
        for key in sim.order:
            if credit_remaining <= 0:
                break
            if key not in ("interest", "principal"):
                continue
            if key == "interest":
                take = min(credit_remaining, interest_due)
                if take > 0:
                    due_alloc.to_interest += take
                    credit_remaining -= take
            else:
                take = min(credit_remaining, principal_due)
                if take > 0:
                    due_alloc.to_principal += take
                    credit_remaining -= take
        paid_interest = due_alloc.to_interest
        paid_principal = due_alloc.to_principal
        sim.credit = credit_remaining

        # 5) 未付部分形成欠款批次（起罚日 = 宽限期截止日次日起算）
        shortfall_interest = interest_due - paid_interest
        shortfall_principal = principal_due - paid_principal
        penalty_start = grace_end + timedelta(days=1)
        if shortfall_interest > 0:
            sim.interest_lots.append(_Lot(due_date=due_date, amount=shortfall_interest))
            sim.overdue_start_dates[due_date] = penalty_start
        if shortfall_principal > 0:
            sim.principal_lots.append(_Lot(due_date=due_date, amount=shortfall_principal))
            sim.overdue_start_dates[due_date] = penalty_start
        if sim.first_penalty_start is None or penalty_start < sim.first_penalty_start:
            sim.first_penalty_start = penalty_start

        sim.balance -= paid_principal

        # 6) 记录计划行与违约行
        interest_part = interest_due
        sim.schedule_rows.append(
            ScheduleRow(
                period_no=sim.period_no,
                due_date=due_date,
                monthly_payment=_q(principal_due + interest_due),
                principal_part=_q(principal_due),
                interest_part=interest_part,
                annual_rate=annual,
                remaining_principal=_q(sim.balance),
                rescheduled=rate_changed,
            )
        )
        sim.default_rows.append(
            DefaultRow(
                period_no=sim.period_no,
                due_date=due_date,
                due_principal=_q(principal_due),
                due_interest=interest_due,
                paid_principal=_q(paid_principal),
                paid_interest=_q(paid_interest),
                status=status(shortfall_principal, shortfall_interest),
                overdue_days=0,
                accrued_penalty=Decimal("0"),
                accrued_compound=Decimal("0"),
                annual_rate=annual,
                allocations=[due_alloc] if (paid_principal or paid_interest) else [],
            )
        )

        sim.remaining_periods -= 1
        if sim.balance <= 0:
            sim.settled = True
            break
        if sim.remaining_periods <= 0:
            break

    # ---- 尾期截算：从最后事件日到 claim ----
    if sim.accelerated:
        while sim.payment_idx < len(sim.payments) and sim.payments[sim.payment_idx].payment_date <= sim.claim:
            rec = sim.payments[sim.payment_idx]
            sim.payment_idx += 1
            process_payment(sim, rec)

    if sim.prev_event_date is not None and sim.prev_event_date < sim.claim:
        accrue(sim, sim.prev_event_date, sim.claim)
        if sim.balance > 0 and sim.remaining_periods > 0 and not sim.accelerated:
            annual = sim.resolver.contract_annual(sim.prev_event_date)
            stub_days = unpaused_days(sim.prev_event_date, sim.claim, sim.pause_ranges) + sim.boundary_plus
            stub_interest = sim.balance * annual / Decimal("100") * stub_days / Decimal(sim.year_days)
            if stub_interest > 0:
                sim.interest_lots.append(_Lot(due_date=sim.claim, amount=stub_interest))
