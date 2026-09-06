"""房贷逾期计算：逐日计息引擎（罚息 / 复利 / 一次性违约金）.

纯函数 accrue(sim, d_from, d_to)：读改写 Simulation 上的欠款批次与累计金额。
flat 复利模式下按积数累计，daily 模式按日分段。
"""

from __future__ import annotations

from datetime import date, timedelta
from decimal import Decimal
from typing import TYPE_CHECKING

from apps.finance.services.calculator.mortgage_models import COMPOUND_METHOD_FLAT, _q, unpaused_days

if TYPE_CHECKING:
    from apps.finance.services.calculator.simulation import Simulation


def accrue(sim: Simulation, d_from: date, d_to: date) -> None:
    """对逾期本金计罚息、对欠息计复利（按日）.

    各批次罚息/复利从其起罚日（还款日+宽限期次日）起算；启用逾期自动加码时在加码
    生效边界处拆分计息区间；停息区间内暂停计息；含截止日当天（算头算尾）时末日 +1 天。
    """
    if d_to <= d_from:
        return

    surcharge = sim.step_up_rate
    up_boundary: date | None = None
    if surcharge is not None and sim.first_penalty_start is not None:
        up_boundary = sim.first_penalty_start + timedelta(days=sim.step_up_trigger_days)

    segments = [(d_from, d_to)]
    if up_boundary is not None and d_from < up_boundary < d_to:
        segments = [(d_from, up_boundary), (up_boundary, d_to)]

    for seg_from, seg_to in segments:
        uplifted = up_boundary is not None and seg_from >= up_boundary
        base_p = sim.resolver.penalty_annual(seg_from)
        if uplifted and surcharge is not None:
            base_p = base_p * (Decimal("1") + surcharge / Decimal("100"))
            if sim.cap_penalty_annual is not None and base_p > sim.cap_penalty_annual:
                base_p = sim.cap_penalty_annual
        p_rate = base_p / Decimal("100") / Decimal(sim.year_days)

        def effective_days(lot_due: date) -> int:
            """扣除宽限期/停息区间后的实际计罚天数：起罚日 = 还款日+宽限期+1."""
            start = sim.overdue_start_dates.get(lot_due)
            if start is None:
                days = _unpaused(sim, seg_from, seg_to)
            else:
                eff_from = max(seg_from, start)
                days = _unpaused(sim, eff_from, seg_to)
            if seg_to == sim.claim:
                days += sim.boundary_plus
            return max(days, 0)

        for lot in sim.principal_lots:
            if lot.amount <= 0:
                continue
            days_eff = effective_days(lot.due_date)
            if days_eff <= 0:
                continue
            x = lot.amount * p_rate * days_eff
            lot.accrued_penalty += x
            sim.penalty_accrued_total += x
            if (
                sim.lump_penalty_rate is not None or sim.lump_penalty_amount
            ) and lot.due_date not in sim.lump_charged_due:
                start = sim.overdue_start_dates.get(lot.due_date)
                total_overdue = max((seg_to - start).days, 0) if start else days_eff
                if total_overdue >= sim.lump_penalty_threshold_days:
                    sim.lump_charged_due.add(lot.due_date)
                    if sim.lump_penalty_rate is not None:
                        sim.lump_penalty_total += _q(lot.amount * sim.lump_penalty_rate / Decimal("100"))
                    elif sim.lump_penalty_amount is not None:
                        sim.lump_penalty_total += _q(sim.lump_penalty_amount)
        if sim.compound_on_interest:
            for lot in sim.interest_lots:
                if lot.amount <= 0:
                    continue
                days_eff = effective_days(lot.due_date)
                if days_eff <= 0:
                    continue
                if sim.compound_method == COMPOUND_METHOD_FLAT:
                    sim.compound_interest_accrued += lot.amount * days_eff
                    sim.compound_days_total += days_eff
                else:
                    x = lot.amount * p_rate * days_eff
                    lot.accrued_compound += x
                    sim.compound_accrued_total += x
        if sim.compound_on_penalty:
            penalty_outstanding = sim.penalty_accrued_total - sim.penalty_paid
            if penalty_outstanding > 0:
                acc_days = _unpaused(sim, seg_from, seg_to)
                if seg_to == sim.claim:
                    acc_days += sim.boundary_plus
                if sim.compound_method == COMPOUND_METHOD_FLAT:
                    sim.penalty_compound_accrued += penalty_outstanding * acc_days
                else:
                    sim.penalty_compound_total += penalty_outstanding * p_rate * acc_days


def _unpaused(sim: Simulation, d_from: date, d_to: date) -> int:
    return unpaused_days(d_from, d_to, sim.pause_ranges)
