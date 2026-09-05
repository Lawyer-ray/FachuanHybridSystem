"""房贷逾期违约债权计算器（门面，向后兼容）.

真正实现已按职责拆分为 calculator/ 下的模块：
- validation.py    输入校验
- rate_resolver.py 合同/罚息/加码/封顶利率解析
- schedule.py      摊销数学与重排
- accrual.py       逐日计息引擎
- ledger.py        还款冲抵账本
- simulation.py    模拟状态与主驱动循环
- claim.py         诉请汇总/舍入/封顶/行级回填
- mortgage_models.py 数据模型与常量

本文件仅保留对外类 MortgageDefaultCalculator（calculate 入口）与各类名再导出，
保证 lpr_api / mcp / 既有测试无需改动即可使用。
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal
from typing import TYPE_CHECKING

from apps.finance.services.calculator.claim import build_claim
from apps.finance.services.calculator.mortgage_models import (
    ALLOCATION_STANCE_PRESETS,
    CAP_TOTAL_NONE,
    CLAIM_MODE_BOTH,
    COMPOUND_METHOD_DAILY,
    FIRST_PERIOD_PRORATE,
    PENALTY_MODE_MULTIPLIER,
    PREPAY_SHORTEN_TERM,
    RATE_MODE_FIXED,
    REPAYMENT_EQUAL_INSTALLMENT,
    ROUNDING_PERIOD,
    AllocationDetail,
    ClaimSummary,
    DefaultRow,
    MortgageDefaultResult,
    PausePeriod,
    PaymentRecord,
    ScheduleRow,
)
from apps.finance.services.calculator.rate_resolver import RateResolver
from apps.finance.services.calculator.simulation import Simulation, simulate
from apps.finance.services.calculator.validation import (
    build_pause_ranges,
    normalize_allocation_order,
    normalize_payments,
    resolve_accelerate_penalty_start,
    validate_claim_config,
    validate_inputs,
    validate_lump,
    validate_step_up,
)

if TYPE_CHECKING:
    from apps.finance.services.lpr.rate_service import LPRRateService

__all__ = [
    "MortgageDefaultCalculator",
    "AllocationDetail",
    "ClaimSummary",
    "DefaultRow",
    "PausePeriod",
    "PaymentRecord",
    "ScheduleRow",
    "MortgageDefaultResult",
    "add_months",
]


def add_months(d: date, months: int) -> date:  # 向后兼容导出
    from apps.finance.services.calculator.mortgage_models import add_months as _am

    return _am(d, months)


class MortgageDefaultCalculator:
    """房贷逾期违约债权计算器（门面）.

    单次模拟同时产出：
    - schedule_rows：重排后的还款计划
    - default_rows：逐期违约明细（含每笔还款冲抵明细）
    - claim：诉讼请求金额汇总
    """

    def __init__(self, rate_service: LPRRateService | None = None) -> None:
        if rate_service is None:
            from apps.finance.services.lpr.rate_service import LPRRateService

            self.rate_service = LPRRateService()
        else:
            self.rate_service = rate_service

    def calculate(
        self,
        *,
        principal: Decimal,
        start_date: date,
        term_months: int,
        repayment_method: str = REPAYMENT_EQUAL_INSTALLMENT,
        payment_day: int | None = None,
        rate_mode: str = RATE_MODE_FIXED,
        fixed_rate: Decimal | None = None,
        lpr_type: str = "5y",
        basis_points: Decimal = Decimal("0"),
        repricing_day: str = "01-01",
        penalty_mode: str = PENALTY_MODE_MULTIPLIER,
        penalty_multiplier: Decimal = Decimal("1.5"),
        penalty_rate: Decimal | None = None,
        compound_on_interest: bool = True,
        compound_on_penalty: bool = False,
        compound_method: str = COMPOUND_METHOD_DAILY,
        grace_period_days: int = 0,
        first_period_interest: str = FIRST_PERIOD_PRORATE,
        charge_interest_on_payment_day: bool = False,
        year_days: int = 360,
        allocation_order: list[str] | None = None,
        allocation_stance: str | None = None,
        rate_events: list[dict] | None = None,
        lump_penalty_rate: Decimal | None = None,
        lump_penalty_amount: Decimal | None = None,
        lump_penalty_threshold_days: int = 0,
        shift_due_to_workday: bool = False,
        holidays: list[date] | None = None,
        prepayment_handling: str = PREPAY_SHORTEN_TERM,
        prepayment_compensation_rate: Decimal | None = None,
        other_fees: list[dict] | None = None,
        fees_offset: bool = False,
        step_up_rate: Decimal | None = None,
        step_up_trigger_days: int = 0,
        rounding_mode: str = ROUNDING_PERIOD,
        claim_mode: str = CLAIM_MODE_BOTH,
        accelerate_date: date | None = None,
        accelerate_grace_days: int = 0,
        cap_penalty_annual: Decimal | None = None,
        cap_total_mode: str = CAP_TOTAL_NONE,
        cap_total_value: Decimal = Decimal("0"),
        interest_cut_inclusive: bool = False,
        pause_periods: list[PausePeriod] | None = None,
        payments: list[PaymentRecord] | None = None,
        claim_date: date | None = None,
    ) -> MortgageDefaultResult:
        """计算逾期违约债权（入口：校验 → 构造 Simulation → 驱动 → 汇总）."""

        # ---- 校验 ----
        validate_inputs(
            principal=principal,
            start_date=start_date,
            term_months=term_months,
            repayment_method=repayment_method,
            rate_mode=rate_mode,
            fixed_rate=fixed_rate,
            penalty_mode=penalty_mode,
            penalty_rate=penalty_rate,
            year_days=year_days,
        )
        validate_lump(
            lump_penalty_rate=lump_penalty_rate,
            lump_penalty_amount=lump_penalty_amount,
            lump_penalty_threshold_days=lump_penalty_threshold_days,
        )
        validate_step_up(step_up_rate=step_up_rate, step_up_trigger_days=step_up_trigger_days)

        claim = claim_date or date.today()
        validate_claim_config(
            rounding_mode=rounding_mode,
            claim_mode=claim_mode,
            accelerate_grace_days=accelerate_grace_days,
            cap_penalty_annual=cap_penalty_annual,
            cap_total_mode=cap_total_mode,
            cap_total_value=cap_total_value,
            claim=claim,
            start_date=start_date,
        )
        pause_ranges: list[tuple[date, date]] = build_pause_ranges(pause_periods)
        boundary_plus = 1 if interest_cut_inclusive else 0

        warnings: list[str] = []
        pay_records = normalize_payments(payments or [], start_date, warnings)
        if not allocation_order and allocation_stance in ALLOCATION_STANCE_PRESETS:
            order = list(ALLOCATION_STANCE_PRESETS[allocation_stance])
        else:
            order = normalize_allocation_order(allocation_order)
        if fees_offset and "fee" not in order:
            order.append("fee")
        holidays_set = set(holidays or [])

        # ---- 加速到期状态 ----
        accelerate_penalty_start = resolve_accelerate_penalty_start(
            accelerate_date=accelerate_date,
            accelerate_grace_days=accelerate_grace_days,
            start_date=start_date,
            claim=claim,
            warnings=warnings,
        )
        # 未触发（None）时按「无加速」处理，避免循环内仍用原始日期触发加速
        effective_accelerate_date = accelerate_date if accelerate_penalty_start is not None else None

        # ---- 分段利率事件覆盖基座 ----
        rate_events_sorted = sorted((rate_events or []), key=lambda e: e.get("date", ""))

        # ---- 利率解析器 ----
        rate_service = getattr(self, "rate_service", None)
        resolver = RateResolver(
            rate_mode=rate_mode,
            fixed_rate=fixed_rate,
            rate_service=rate_service,
            lpr_type=lpr_type,
            basis_points=basis_points,
            repricing_day=repricing_day,
            start_date=start_date,
            rate_events=rate_events_sorted,
            penalty_mode=penalty_mode,
            penalty_multiplier=penalty_multiplier,
            penalty_rate=penalty_rate,
            cap_penalty_annual=cap_penalty_annual,
            step_up_rate=step_up_rate,
            step_up_trigger_days=step_up_trigger_days,
        )

        # ---- 模拟 ----
        sim = Simulation(
            principal=principal,
            start_date=start_date,
            term_months=term_months,
            repayment_method=repayment_method,
            payment_day=payment_day,
            penalty_mode=penalty_mode,
            penalty_multiplier=penalty_multiplier,
            penalty_rate=penalty_rate,
            compound_on_interest=compound_on_interest,
            compound_on_penalty=compound_on_penalty,
            compound_method=compound_method,
            grace_period_days=grace_period_days,
            first_period_interest=first_period_interest,
            charge_interest_on_payment_day=charge_interest_on_payment_day,
            interest_cut_inclusive=interest_cut_inclusive,
            year_days=year_days,
            lump_penalty_rate=lump_penalty_rate,
            lump_penalty_amount=lump_penalty_amount,
            lump_penalty_threshold_days=lump_penalty_threshold_days,
            shift_due_to_workday=shift_due_to_workday,
            holidays_set=holidays_set,
            prepayment_handling=prepayment_handling,
            prepayment_compensation_rate=prepayment_compensation_rate,
            other_fees=other_fees or [],
            step_up_rate=step_up_rate,
            step_up_trigger_days=step_up_trigger_days,
            rounding_mode=rounding_mode,
            claim_mode=claim_mode,
            fees_offset=fees_offset,
            accelerate_date=effective_accelerate_date,
            accelerate_grace_days=accelerate_grace_days,
            cap_penalty_annual=cap_penalty_annual,
            cap_total_mode=cap_total_mode,
            cap_total_value=cap_total_value,
            pause_ranges=pause_ranges,
            claim=claim,
            boundary_plus=boundary_plus,
            resolver=resolver,
            order=order,
            payments=pay_records,
            balance=principal,
            remaining_periods=term_months,
            principal_part_plan=(
                principal / Decimal(term_months) if repayment_method == "equal_principal" else Decimal("0")
            ),
            prev_event_date=start_date,
            fee_base_total=sum((Decimal(str(f.get("amount", 0))) for f in (other_fees or [])), Decimal("0")),
        )
        sim.warnings = warnings

        simulate(sim)

        if sim.stub_result is not None:
            return MortgageDefaultResult(
                claim=sim.stub_result,
                schedule_rows=[],
                default_rows=[],
                warnings=sim.warnings,
                meta=self._build_meta(
                    sim, order=order, rate_events_sorted=rate_events_sorted, allocation_stance=allocation_stance
                ),
            )

        claim_summary = build_claim(sim)
        return MortgageDefaultResult(
            claim=claim_summary,
            schedule_rows=sim.schedule_rows,
            default_rows=sim.default_rows,
            warnings=sim.warnings,
            meta=self._build_meta(
                sim, order=order, rate_events_sorted=rate_events_sorted, allocation_stance=allocation_stance
            ),
        )

    @staticmethod
    def _normalize_allocation_order(allocation_order: list[str] | None) -> list[str]:
        """向后兼容：转交给 validation 模块."""
        return normalize_allocation_order(allocation_order)

    @staticmethod
    def _normalize_payments(
        payments: list[PaymentRecord], start_date: date, warnings: list[str]
    ) -> list[PaymentRecord]:
        """向后兼容：转交给 validation 模块."""
        return normalize_payments(payments, start_date, warnings)

    @staticmethod
    def _build_meta(
        sim: Simulation,
        *,
        order: list[str],
        rate_events_sorted: list[dict],
        allocation_stance: str | None,
    ) -> dict:
        """组装 meta 元数据（保持与旧版 calculate 输出一致）."""
        from apps.finance.services.calculator.mortgage_models import _str_money as _sm

        step_up = _sm(sim.step_up_rate) if sim.step_up_rate is not None else ""
        cap_p = _sm(sim.cap_penalty_annual) if sim.cap_penalty_annual is not None else ""
        accel_date = sim.accelerate_date.isoformat() if sim.accelerated and sim.accelerate_date else ""
        accel_start = (
            sim.accelerate_penalty_start.isoformat() if sim.accelerated and sim.accelerate_penalty_start else ""
        )
        first_due = sim.first_due.isoformat() if sim.first_due is not None else ""
        return {
            "repayment_method": sim.repayment_method,
            "rate_mode": sim.resolver.rate_mode,
            "penalty_mode": sim.penalty_mode,
            "compound_method": sim.compound_method,
            "grace_period_days": sim.grace_period_days,
            "first_period_interest": sim.first_period_interest,
            "charge_interest_on_payment_day": sim.charge_interest_on_payment_day,
            "allocation_order": order,
            "allocation_stance": allocation_stance or "",
            "year_days": sim.year_days,
            "rate_events": rate_events_sorted,
            "lump_penalty": _sm(sim.lump_outstanding),
            "shift_due_to_workday": sim.shift_due_to_workday,
            "step_up_rate": step_up,
            "step_up_trigger_days": sim.step_up_trigger_days,
            "rounding_mode": sim.rounding_mode,
            "fees_offset": sim.fees_offset,
            "claim_mode": sim.claim_mode,
            "claim_taken": sim.claim_taken,
            "accelerated": sim.accelerated,
            "accelerate_date": accel_date,
            "accelerate_penalty_start": accel_start,
            "first_due_date": first_due,
            "term_months": sim.term_months,
            "cap_penalty_annual": cap_p,
            "cap_total_mode": sim.cap_total_mode,
            "cap_total_value": _sm(sim.cap_total_value),
            "capped_total": sim.capped_total,
            "interest_cut_inclusive": sim.interest_cut_inclusive,
            "pause_periods": [{"start": s.isoformat(), "end": e.isoformat()} for s, e in sim.pause_ranges],
        }
