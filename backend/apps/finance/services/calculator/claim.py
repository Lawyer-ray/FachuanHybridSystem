"""房贷逾期计算：诉讼请求汇总（主张口径 / 舍入 / 总债权封顶 / 行级回填）.

build_claim(sim) 读取模拟终态，计算诉请金额明细并回填违约行的逾期天数与罚息/复利，
产出 ClaimSummary。纯计算，无数据库副作用。
"""

from __future__ import annotations

from datetime import date, timedelta
from decimal import Decimal
from typing import TYPE_CHECKING

from apps.finance.services.calculator.mortgage_models import (
    CAP_TOTAL_AMOUNT,
    CAP_TOTAL_INTEREST_RATIO,
    CAP_TOTAL_NONE,
    CAP_TOTAL_PRINCIPAL_RATIO,
    CLAIM_MODE_EITHER,
    COMPOUND_METHOD_FLAT,
    STATUS_PAID,
    ClaimSummary,
    _q,
    _str_money,
)

if TYPE_CHECKING:
    from apps.finance.services.calculator.simulation import Simulation

__all__ = ["build_claim"]


def build_claim(sim: Simulation) -> ClaimSummary:
    """计算诉讼请求汇总并回填违约行，返回 ClaimSummary（同时缓存到 sim）."""
    unpaid_interest = sum((lot.amount for lot in sim.interest_lots), Decimal("0"))
    penalty_outstanding = sim.penalty_accrued_total - sim.penalty_paid
    if sim.compound_method == COMPOUND_METHOD_FLAT:
        # 复利不分段：积数 × 收取复利时（截止日）适用的罚息利率
        flat_rate = (
            sim.resolver.eff_penalty_annual(sim.claim, sim.first_penalty_start)
            / Decimal("100")
            / Decimal(sim.year_days)
        )
        compound_from_interest = sim.compound_interest_accrued * flat_rate
        compound_from_penalty = sim.penalty_compound_accrued * flat_rate
        compound_outstanding = compound_from_interest + compound_from_penalty - sim.compound_paid
    else:
        compound_outstanding = sim.compound_accrued_total - sim.compound_paid + sim.penalty_compound_total
    outstanding_principal = max(sim.balance, Decimal("0"))
    p_daily = (
        sim.resolver.eff_penalty_annual(sim.claim, sim.first_penalty_start) / Decimal("100") / Decimal(sim.year_days)
    )
    daily_accrual = outstanding_principal * p_daily + unpaid_interest * p_daily
    if sim.compound_on_penalty:
        daily_accrual += (sim.penalty_accrued_total - sim.penalty_paid) * p_daily

    # 其他费用（律师费/诉讼费/提前还款补偿金等，不参与利息计算）
    fee_items: list[dict] = list(sim.other_fees or [])
    if sim.prepayment_compensation > 0:
        fee_items.append({"name": "提前还款补偿金", "amount": _str_money(sim.prepayment_compensation)})
    other_fees_total = sum((Decimal(str(f.get("amount", 0))) for f in fee_items), Decimal("0"))
    other_fees_outstanding = other_fees_total - sim.fees_paid
    lump_outstanding = sim.lump_penalty_total - sim.lump_penalty_paid
    sim.lump_outstanding = lump_outstanding

    # 违约金 vs 罚息主张口径：both=并行叠加；either=择一从高（避免重复主张）
    claim_taken = ""
    if sim.claim_mode == CLAIM_MODE_EITHER and lump_outstanding and penalty_outstanding:
        if lump_outstanding >= penalty_outstanding:
            claimed_penalty = Decimal("0")
            claimed_lump = lump_outstanding
            claim_taken = "违约金"
        else:
            claimed_penalty = penalty_outstanding
            claimed_lump = Decimal("0")
            claim_taken = "罚息"
        sim.warnings.append(
            f"违约金与罚息择一从高：取【{claim_taken}】（违约金 {_str_money(lump_outstanding)} "
            f"vs 罚息 {_str_money(penalty_outstanding)}）计入诉请，另一项不再叠加"
        )
    else:
        claimed_penalty = penalty_outstanding
        claimed_lump = lump_outstanding

    # 总债权封顶：违约金+罚息+复利合计不得超过封顶值，削减顺序 复利→罚息→违约金
    capped_total = False
    cap_value: Decimal | None = None
    if sim.cap_total_mode != CAP_TOTAL_NONE:
        if sim.cap_total_mode == CAP_TOTAL_AMOUNT:
            cap_value = sim.cap_total_value
            basis_desc = f"固定金额 {_str_money(sim.cap_total_value)}"
        elif sim.cap_total_mode == CAP_TOTAL_PRINCIPAL_RATIO:
            cap_value = max(outstanding_principal, Decimal("0")) * sim.cap_total_value
            basis_desc = f"未还本金 {_str_money(max(outstanding_principal, Decimal('0')))} 的 {sim.cap_total_value} 倍"
        else:  # CAP_TOTAL_INTEREST_RATIO
            cap_value = unpaid_interest * sim.cap_total_value
            basis_desc = f"未付利息 {_str_money(unpaid_interest)} 的 {sim.cap_total_value} 倍"
        responsive = claimed_lump + claimed_penalty + compound_outstanding
        if cap_value is not None and responsive > cap_value:
            reduction = responsive - cap_value
            for bucket in ("compound", "penalty", "lump"):
                if reduction <= 0:
                    break
                if bucket == "compound":
                    take = min(reduction, compound_outstanding)
                    compound_outstanding -= take
                elif bucket == "penalty":
                    take = min(reduction, claimed_penalty)
                    claimed_penalty -= take
                else:
                    take = min(reduction, claimed_lump)
                    claimed_lump -= take
                reduction -= take
            capped_total = True
            sim.warnings.append(
                f"总债权封顶生效：违约金+罚息+复利合计超出封顶值（{basis_desc}），"
                f"已从 {_str_money(responsive)} 削减至 {_str_money(responsive - reduction)}，"
                "削减顺序为复利→罚息→违约金，请核对合同/裁判约定后引用"
            )

    _append_final_warnings(sim, lump_penalty_threshold_days=sim.lump_penalty_threshold_days)

    # 批次归属回填违约行：逾期天数、罚息/复利、还款冲抵金额
    _backfill_rows(sim)

    if sim.rounding_mode == "cumulative":
        total_claim = _q(
            outstanding_principal
            + unpaid_interest
            + claimed_penalty
            + compound_outstanding
            + claimed_lump
            + other_fees_outstanding
        )
    else:
        total_claim = _q(
            _q(outstanding_principal)
            + _q(unpaid_interest)
            + _q(claimed_penalty)
            + _q(compound_outstanding)
            + _q(claimed_lump)
            + _q(other_fees_outstanding)
        )

    claim_summary = ClaimSummary(
        claim_date=sim.claim,
        outstanding_principal=_q(outstanding_principal),
        unpaid_interest=_q(unpaid_interest),
        penalty_interest=_q(claimed_penalty),
        compound_interest=_q(compound_outstanding),
        total_claim=total_claim,
        daily_accrual=_q(daily_accrual),
        lump_penalty=_q(claimed_lump),
        other_fees=_q(other_fees_outstanding),
        fee_items=[
            {"name": f.get("name", ""), "amount": _str_money(Decimal(str(f.get("amount", 0))))} for f in fee_items
        ],
    )
    # 逐期罚息/复利四舍五入展示
    for row in sim.default_rows:
        row.paid_interest = _q(row.paid_interest)
        row.paid_principal = _q(row.paid_principal)
        row.accrued_penalty = _q(row.accrued_penalty)
        row.accrued_compound = _q(row.accrued_compound)

    sim.claim_summary = claim_summary
    sim.claim_taken = claim_taken
    sim.capped_total = capped_total
    return claim_summary


def _backfill_rows(sim: Simulation) -> None:
    """把批次罚息/复利/逾期天数/还款冲抵回填到违约行."""
    row_by_due = {row.due_date: row for row in sim.default_rows}
    penalty_by_due: dict[date, Decimal] = {}
    compound_by_due: dict[date, Decimal] = {}
    for lot in sim.principal_lots:
        penalty_by_due[lot.due_date] = penalty_by_due.get(lot.due_date, Decimal("0")) + lot.accrued_penalty
    for lot in sim.interest_lots:
        compound_by_due[lot.due_date] = compound_by_due.get(lot.due_date, Decimal("0")) + lot.accrued_compound
    for row in sim.default_rows:
        row.accrued_penalty += penalty_by_due.get(row.due_date, Decimal("0"))
        row.accrued_compound += compound_by_due.get(row.due_date, Decimal("0"))
        if row.status != STATUS_PAID:
            start = sim.overdue_start_dates.get(row.due_date, row.due_date)
            plus = 1 if (sim.charge_interest_on_payment_day or sim.interest_cut_inclusive) else 0
            end_adj = sim.claim + timedelta(days=plus)
            row.overdue_days = max(row.overdue_days, max((end_adj - start).days, 0))
        for alloc in row.allocations:
            if alloc.direct:
                continue
            row.paid_interest += alloc.interest_by_due.get(row.due_date, Decimal("0"))
            row.paid_principal += alloc.principal_by_due.get(row.due_date, Decimal("0"))


def _append_final_warnings(sim: Simulation, *, lump_penalty_threshold_days: int) -> None:
    """追加汇总口径提示（保持与原计算器一致的告警文案）."""
    if sim.reschedule_count:
        sim.warnings.append(f"因提前还款/利率重定价共重排还款计划 {sim.reschedule_count} 次，明细以重排后计划为准")
    if sim.compound_on_penalty:
        sim.warnings.append("已开启「对罚息再计复利」，该口径依赖合同约定，请核对后再引用")
    if sim.compound_method == COMPOUND_METHOD_FLAT and (sim.compound_on_interest or sim.compound_on_penalty):
        sim.warnings.append("复利按「不分段」口径计算（积数×收取时罚息利率），如合同约定分段计收请改用逐日模式")
    if sim.grace_period_days:
        sim.warnings.append(
            f"宽限期 {sim.grace_period_days} 天：还款日+宽限期内还款视为按时，罚息/复利自宽限期届满次日起算"
        )
    if sim.charge_interest_on_payment_day:
        sim.warnings.append("逾期天数包含还款日当日（算至实际还款日）口径")
    if sim.lump_penalty_total > 0:
        sim.warnings.append(
            f"已计一次性违约金（违约金率 {sim.lump_penalty_rate or '固定金额'}，逾期 {lump_penalty_threshold_days} 天触发），"
            "请核对合同违约金条款后引用；该违约金为一次性固定主张，不随每日增加"
        )
    if sim.step_up_rate is not None and sim.step_up_rate > 0 and sim.first_penalty_start is not None:
        sim.warnings.append(
            f"逾期自动加码已启用（逾期 {sim.step_up_trigger_days} 天起罚息上浮 {sim.step_up_rate}%），"
            "请核对合同是否约定逾期加价后引用"
        )
    if sim.fees_offset:
        sim.warnings.append("诉讼费用已纳入还款冲抵顺序（fee 项），将随还款核销；请核对费用能否参与按序核销的合同约定")
    if sim.rounding_mode == "cumulative":
        sim.warnings.append("舍入规则：全程保持精度，诉讼请求合计一次性四舍五入到分（cumulative）")
    if sim.shift_due_to_workday:
        sim.warnings.append("扣款日已按「逢周末/法定节假日顺延至下一工作日」口径处理")
    if len(sim.resolver.rate_events):
        sim.warnings.append(f"已应用 {len(sim.resolver.rate_events)} 次分段利率调整，罚息/复利按调整后利率分段计算")
    if sim.cap_penalty_annual is not None:
        sim.warnings.append(f"罚息/复利年利率已封顶为 {sim.cap_penalty_annual}%，超过该上限的利率按封顶值计息")
    if sim.interest_cut_inclusive:
        sim.warnings.append("计息口径：含截止日当天（算头算尾），利息/罚息/复利末日各 +1 天")
    if sim.pause_ranges:
        sim.warnings.append(f"已应用 {len(sim.pause_ranges)} 段停息区间，区间内罚息/复利及按天截算的合同利息暂停计息")
