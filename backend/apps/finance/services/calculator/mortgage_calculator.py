"""房贷逾期违约债权计算器.

面向银行诉讼场景：在等额本息/等额本金摊销的基础上，叠加：
- 还款流水冲抵（冲抵顺序可配置，预设 罚息→利息→复利→本金）
- 罚息（执行利率×倍数 或 直接指定罚息利率）
- 复利（对欠付利息计复利，可选对罚息再计复利）
- 提前还款重排（缩短期限 / 月供递减）
- LPR 浮动利率 + 重定价日

输出诉讼请求金额汇总（本金/利息/罚息/复利）与逐期违约明细。
全部使用 Decimal 计算，金额输出保留两位小数（字符串）。
"""

from __future__ import annotations

import logging
import math
from dataclasses import dataclass, field
from datetime import date, timedelta
from decimal import ROUND_CEILING, ROUND_HALF_UP, Decimal
from typing import TYPE_CHECKING, Callable

from apps.core.exceptions import ValidationException

if TYPE_CHECKING:
    from apps.finance.services.lpr.rate_service import LPRRateService

logger = logging.getLogger(__name__)

CENT = Decimal("0.01")

# 还款方式
REPAYMENT_EQUAL_INSTALLMENT = "equal_installment"
REPAYMENT_EQUAL_PRINCIPAL = "equal_principal"
VALID_REPAYMENT_METHODS = {REPAYMENT_EQUAL_INSTALLMENT, REPAYMENT_EQUAL_PRINCIPAL}

# 利率模式
RATE_MODE_FIXED = "fixed"
RATE_MODE_LPR = "lpr"

# 罚息利率模式
PENALTY_MODE_MULTIPLIER = "multiplier"
PENALTY_MODE_SPECIFIED = "specified"

# 还款流水类型
PAYMENT_TYPE_NORMAL = "normal"
PAYMENT_TYPE_PREPAYMENT = "prepayment_principal"
VALID_PAYMENT_TYPES = {PAYMENT_TYPE_NORMAL, PAYMENT_TYPE_PREPAYMENT}

# 提前还款重排方式
PREPAY_SHORTEN_TERM = "shorten_term"
PREPAY_REDUCE_PAYMENT = "reduce_payment"

# 冲抵顺序
VALID_ALLOCATION_KEYS = {"penalty", "interest", "compound", "principal"}
DEFAULT_ALLOCATION_ORDER = ["penalty", "interest", "compound", "principal"]

# 复利计算方式
COMPOUND_METHOD_DAILY = "daily"  # 逐日按当日罚息利率分段计算
COMPOUND_METHOD_FLAT = "flat"  # 不分段：积数 × 收取复利时适用的罚息利率（如交行 13.1）

# 首期计息方式
FIRST_PERIOD_PRORATE = "prorate"  # 按放款日→首期扣款日实际天数计息（含零头天数）
FIRST_PERIOD_FULL_MONTH = "full_month"  # 首期按整月计息

# 状态
STATUS_PAID = "paid"
STATUS_PARTIAL = "partial"
STATUS_UNPAID = "unpaid"


def _q(value: Decimal) -> Decimal:
    """金额四舍五入到分."""
    return value.quantize(CENT, rounding=ROUND_HALF_UP)


def _str_money(value: Decimal) -> str:
    return str(_q(value))


def add_months(d: date, months: int) -> date:
    """加 N 个月，日超出月末时钳制到月末（1/31 + 1月 → 2/28）."""
    total = (d.month - 1) + months
    year = d.year + total // 12
    month = total % 12 + 1
    if month == 12:
        next_month = date(year + 1, 1, 1)
    else:
        next_month = date(year, month + 1, 1)
    last_day = (next_month - timedelta(days=1)).day
    return date(year, month, min(d.day, last_day))


@dataclass
class _Lot:
    """欠款批次.

    每期未按时支付的金额形成一个批次，用于按日计收罚息/复利，
    并支持按期归属展示（FIFO 冲抵）。
    """

    due_date: date
    amount: Decimal
    accrued_penalty: Decimal = field(default_factory=lambda: Decimal("0"))
    accrued_compound: Decimal = field(default_factory=lambda: Decimal("0"))
    cleared_date: date | None = None


@dataclass
class PaymentRecord:
    """还款流水记录."""

    payment_date: date
    amount: Decimal
    payment_type: str = PAYMENT_TYPE_NORMAL
    note: str = ""


@dataclass
class ScheduleRow:
    """还款计划行（重排后的当前计划）."""

    period_no: int
    due_date: date
    monthly_payment: Decimal
    principal_part: Decimal
    interest_part: Decimal
    annual_rate: Decimal
    remaining_principal: Decimal
    rescheduled: bool = False


@dataclass
class AllocationDetail:
    """单笔还款对某期的冲抵明细."""

    payment_date: date
    amount: Decimal
    to_penalty: Decimal = field(default_factory=lambda: Decimal("0"))
    to_interest: Decimal = field(default_factory=lambda: Decimal("0"))
    to_compound: Decimal = field(default_factory=lambda: Decimal("0"))
    to_principal: Decimal = field(default_factory=lambda: Decimal("0"))
    touched_due_dates: set = field(default_factory=set)
    # 按期次记录的冲抵金额（一笔还款可跨多期）
    interest_by_due: dict = field(default_factory=dict)
    principal_by_due: dict = field(default_factory=dict)
    # 溢缴款支付当期应还的分配（已在行级 paid_* 中计入，回填时跳过）
    direct: bool = False


@dataclass
class DefaultRow:
    """逐期违约明细行."""

    period_no: int
    due_date: date
    due_principal: Decimal
    due_interest: Decimal
    paid_principal: Decimal
    paid_interest: Decimal
    status: str
    overdue_days: int
    accrued_penalty: Decimal
    accrued_compound: Decimal
    annual_rate: Decimal
    note: str = ""
    allocations: list[AllocationDetail] = field(default_factory=list)


@dataclass
class ClaimSummary:
    """诉讼请求金额汇总."""

    claim_date: date
    outstanding_principal: Decimal
    unpaid_interest: Decimal
    penalty_interest: Decimal
    compound_interest: Decimal
    total_claim: Decimal
    daily_accrual: Decimal
    other_fees: Decimal = field(default_factory=lambda: Decimal("0"))  # 其他费用（律师费等）
    fee_items: list[dict] = field(default_factory=list)  # 费用明细 [{"name", "amount"}]


@dataclass
class MortgageDefaultResult:
    """违约债权计算结果."""

    claim: ClaimSummary
    schedule_rows: list[ScheduleRow]
    default_rows: list[DefaultRow]
    warnings: list[str]
    meta: dict = field(default_factory=dict)

    def to_dict(self) -> dict:
        """转换为可 JSON 序列化的字典（金额为两位小数字符串）."""
        return {
            "claim": {
                "claim_date": self.claim.claim_date.isoformat(),
                "outstanding_principal": _str_money(self.claim.outstanding_principal),
                "unpaid_interest": _str_money(self.claim.unpaid_interest),
                "penalty_interest": _str_money(self.claim.penalty_interest),
                "compound_interest": _str_money(self.claim.compound_interest),
                "other_fees": _str_money(self.claim.other_fees),
                "fee_items": self.claim.fee_items,
                "total_claim": _str_money(self.claim.total_claim),
                "daily_accrual": _str_money(self.claim.daily_accrual),
            },
            "schedule_rows": [
                {
                    "period_no": r.period_no,
                    "due_date": r.due_date.isoformat(),
                    "monthly_payment": _str_money(r.monthly_payment),
                    "principal_part": _str_money(r.principal_part),
                    "interest_part": _str_money(r.interest_part),
                    "annual_rate": str(r.annual_rate),
                    "remaining_principal": _str_money(r.remaining_principal),
                    "rescheduled": r.rescheduled,
                }
                for r in self.schedule_rows
            ],
            "default_rows": [
                {
                    "period_no": r.period_no,
                    "due_date": r.due_date.isoformat(),
                    "due_principal": _str_money(r.due_principal),
                    "due_interest": _str_money(r.due_interest),
                    "paid_principal": _str_money(r.paid_principal),
                    "paid_interest": _str_money(r.paid_interest),
                    "status": r.status,
                    "overdue_days": r.overdue_days,
                    "accrued_penalty": _str_money(r.accrued_penalty),
                    "accrued_compound": _str_money(r.accrued_compound),
                    "annual_rate": str(r.annual_rate),
                    "note": r.note,
                    "allocations": [
                        {
                            "payment_date": a.payment_date.isoformat(),
                            "amount": _str_money(a.amount),
                            "to_penalty": _str_money(a.to_penalty),
                            "to_interest": _str_money(a.to_interest),
                            "to_compound": _str_money(a.to_compound),
                            "to_principal": _str_money(a.to_principal),
                        }
                        for a in r.allocations
                    ],
                }
                for r in self.default_rows
            ],
            "warnings": self.warnings,
            "meta": self.meta,
        }


class MortgageDefaultCalculator:
    """房贷逾期违约债权计算器.

    单次模拟同时产出：
    - schedule_rows：重排后的还款计划（对照表）
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
        prepayment_handling: str = PREPAY_SHORTEN_TERM,
        prepayment_compensation_rate: Decimal | None = None,
        other_fees: list[dict] | None = None,
        payments: list[PaymentRecord] | None = None,
        claim_date: date | None = None,
    ) -> MortgageDefaultResult:
        """计算逾期违约债权.

        Args:
            principal: 贷款本金
            start_date: 放款日期
            term_months: 贷款期限（月）
            repayment_method: 还款方式，equal_installment=等额本息，equal_principal=等额本金
            payment_day: 每月扣款日（1-31），None 表示放款日对应日；29-31 在无对应日的月份钳制到月末
            rate_mode: fixed=固定利率，lpr=LPR+基点浮动
            fixed_rate: 固定年利率（%），固定利率模式必填
            lpr_type: LPR 期限品种，1y 或 5y（LPR 模式）
            basis_points: 在 LPR 基础上加的基点（bp，100bp=1%，可为负）
            repricing_day: 重定价日，"01-01"、"anniversary"（放款对应日）或 "MM-DD"
            penalty_mode: multiplier=执行利率×倍数，specified=直接指定罚息年利率
            penalty_multiplier: 罚息倍数（如 1.5）
            penalty_rate: 罚息年利率（%），specified 模式必填
            compound_on_interest: 是否对欠付利息计收复利
            compound_on_penalty: 是否对罚息再计收复利
            compound_method: 复利计算方式，daily=逐日按当日罚息利率分段，flat=不分段
                （积数×收取复利时适用的罚息利率，如交行合同 13.1 条）
            grace_period_days: 宽限期天数（还款日+宽限期内还款视为按时，不计罚息复利），默认 0
            first_period_interest: 首期计息方式，prorate=按放款日→首期扣款日实际天数计息
                （含零头天数），full_month=首期按整月计息
            charge_interest_on_payment_day: 逾期天数是否包含还款日当日。
                False=算至实际还款日前一日（如交行 13.2 条），True=含当日
            year_days: 罚息/复利计息基准天数（360 或 365）
            allocation_order: 冲抵顺序，默认 罚息→利息→复利→本金
            prepayment_handling: 提前还款重排方式，shorten_term=缩短期限，reduce_payment=月供递减
            prepayment_compensation_rate: 提前还款补偿金率（%，如 1.00 表示本金 1%），
                None 表示无；提前还款时计入 other_fees 性质的费用（不参与利息计算）
            other_fees: 其他费用列表 [{"name": "律师费", "amount": 50000}]，
                不参与利息计算，仅计入诉讼请求合计
            payments: 还款流水（实际还款记录）
            claim_date: 计算截止日（默认今天，即起诉日）

        Returns:
            MortgageDefaultResult
        """
        self._validate_inputs(
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

        claim = claim_date or date.today()
        if claim <= start_date:
            raise ValidationException(message="计算截止日必须晚于放款日期", code="INVALID_CLAIM_DATE")

        warnings: list[str] = []
        pay_records = self._normalize_payments(payments or [], start_date, warnings)
        order = self._normalize_allocation_order(allocation_order)

        # ---- 利率解析 ----
        contract_annual = self._build_contract_rate_resolver(
            rate_mode=rate_mode,
            fixed_rate=fixed_rate,
            lpr_type=lpr_type,
            basis_points=basis_points,
            repricing_day=repricing_day,
            start_date=start_date,
        )

        def penalty_annual(on: date) -> Decimal:
            if penalty_mode == PENALTY_MODE_SPECIFIED:
                assert penalty_rate is not None  # _validate_inputs 已保证
                return penalty_rate
            return contract_annual(on) * penalty_multiplier

        # ---- 模拟状态 ----
        balance = principal  # 剩余本金（含逾期部分）
        remaining_periods = term_months
        monthly_payment = Decimal("0")
        principal_part_plan = (
            principal / Decimal(term_months) if repayment_method == REPAYMENT_EQUAL_PRINCIPAL else Decimal("0")
        )
        credit = Decimal("0")  # 溢缴款
        current_rate = Decimal("0")  # 当前执行的合同年利率
        principal_lots: list[_Lot] = []  # 逾期本金批次
        interest_lots: list[_Lot] = []  # 欠付利息批次
        penalty_accrued_total = Decimal("0")
        penalty_paid = Decimal("0")
        compound_accrued_total = Decimal("0")
        compound_paid = Decimal("0")
        penalty_compound_total = Decimal("0")  # 对罚息计收的复利（daily 模式）
        compound_interest_accrued = Decimal("0")  # 欠息复利积数（flat 模式）
        penalty_compound_accrued = Decimal("0")  # 罚息复利积数（flat 模式）
        compound_days_total = 0  # 复利计息天数（flat 模式，用于展示）
        reschedule_count = 0
        prepayment_compensation = Decimal("0")  # 提前还款补偿金累计
        overdue_start_dates: dict[date, date] = {}  # 批次 due_date → 起罚日（含宽限期）

        schedule_rows: list[ScheduleRow] = []
        default_rows: list[DefaultRow] = []

        first_due = self._first_due_date(start_date, payment_day)
        if first_due > claim:
            # 起诉日早于首期扣款日：仅截算一段合同利息
            stub_days = (claim - start_date).days
            annual = contract_annual(start_date)
            stub_interest = _q(principal * annual / Decimal("100") * stub_days / Decimal(year_days))
            claim_summary = ClaimSummary(
                claim_date=claim,
                outstanding_principal=principal,
                unpaid_interest=stub_interest,
                penalty_interest=Decimal("0"),
                compound_interest=Decimal("0"),
                total_claim=principal + stub_interest,
                daily_accrual=Decimal("0"),
            )
            warnings.append("计算截止日早于首期扣款日，仅按天截算合同利息，无违约金额")
            return MortgageDefaultResult(
                claim=claim_summary, schedule_rows=[], default_rows=[], warnings=warnings, meta={}
            )

        payment_idx = 0
        prev_event_date = start_date
        period_no = 0

        def accrue(d_from: date, d_to: date) -> None:
            """对逾期本金计罚息、对欠息计复利（按日）.

            flat 复利模式下，复利按积数累计：Σ(欠息余额×天数) × 收取时罚息利率，
            即积数在计息过程中逐日累计，利率在汇总时统一适用（复利不分段）。
            各批次罚息/复利从其起罚日（还款日+宽限期次日）起算。
            """
            nonlocal penalty_accrued_total, compound_accrued_total, penalty_compound_total
            nonlocal compound_interest_accrued, penalty_compound_accrued, compound_days_total
            if d_to <= d_from:
                return
            p_rate = penalty_annual(d_from) / Decimal("100") / Decimal(year_days)

            def effective_days(lot_due: date) -> int:
                """扣除宽限期后的实际计罚天数：起罚日 = 还款日+宽限期+1."""
                start = overdue_start_dates.get(lot_due)
                if start is None:
                    return (d_to - d_from).days
                # 计罚区间与 [start, d_to) 求交集
                eff_from = max(d_from, start)
                return max((d_to - eff_from).days, 0)

            for lot in principal_lots:
                if lot.amount <= 0:
                    continue
                days_eff = effective_days(lot.due_date)
                if days_eff <= 0:
                    continue
                x = lot.amount * p_rate * days_eff
                lot.accrued_penalty += x
                penalty_accrued_total += x
            if compound_on_interest:
                for lot in interest_lots:
                    if lot.amount <= 0:
                        continue
                    days_eff = effective_days(lot.due_date)
                    if days_eff <= 0:
                        continue
                    if compound_method == COMPOUND_METHOD_FLAT:
                        # 积数法：累计欠息余额×天数，汇总时统一乘以收取时的罚息利率
                        compound_interest_accrued += lot.amount * days_eff
                        compound_days_total += days_eff
                    else:
                        x = lot.amount * p_rate * days_eff
                        lot.accrued_compound += x
                        compound_accrued_total += x
            if compound_on_penalty:
                penalty_outstanding = penalty_accrued_total - penalty_paid
                if penalty_outstanding > 0:
                    if compound_method == COMPOUND_METHOD_FLAT:
                        penalty_compound_accrued += penalty_outstanding * (d_to - d_from).days
                    else:
                        penalty_compound_total += penalty_outstanding * p_rate * (d_to - d_from).days

        def pay_toward(key: str, amount: Decimal, pay_date: date, alloc: AllocationDetail) -> Decimal:
            """向指定 bucket 支付，返回实际消耗金额."""
            nonlocal penalty_paid, compound_paid, balance
            remaining = amount
            if key == "penalty":
                outstanding = penalty_accrued_total - penalty_paid
                take = min(remaining, outstanding)
                if take > 0:
                    penalty_paid += take
                    alloc.to_penalty += take
                    remaining -= take
            elif key == "interest":
                for lot in interest_lots:
                    if remaining <= 0:
                        break
                    take = min(remaining, lot.amount)
                    if take > 0:
                        lot.amount -= take
                        if lot.amount <= 0 and lot.cleared_date is None:
                            lot.cleared_date = pay_date
                        alloc.to_interest += take
                        alloc.touched_due_dates.add(lot.due_date)
                        alloc.interest_by_due[lot.due_date] = (
                            alloc.interest_by_due.get(lot.due_date, Decimal("0")) + take
                        )
                        remaining -= take
            elif key == "compound":
                outstanding = compound_accrued_total + penalty_compound_total - compound_paid
                take = min(remaining, outstanding)
                if take > 0:
                    compound_paid += take
                    alloc.to_compound += take
                    remaining -= take
            elif key == "principal":
                for lot in principal_lots:
                    if remaining <= 0:
                        break
                    take = min(remaining, lot.amount)
                    if take > 0:
                        lot.amount -= take
                        balance -= take
                        if lot.amount <= 0 and lot.cleared_date is None:
                            lot.cleared_date = pay_date
                        alloc.to_principal += take
                        alloc.touched_due_dates.add(lot.due_date)
                        alloc.principal_by_due[lot.due_date] = (
                            alloc.principal_by_due.get(lot.due_date, Decimal("0")) + take
                        )
                        remaining -= take
            interest_lots[:] = [lot for lot in interest_lots if lot.amount > 0]
            principal_lots[:] = [lot for lot in principal_lots if lot.amount > 0]
            return amount - remaining

        def allocate_by_order(amount: Decimal, pay_date: date, order: list[str]) -> tuple[Decimal, AllocationDetail]:
            """按冲抵顺序核销，返回 (剩余金额, 冲抵明细)."""
            remaining = amount
            alloc = AllocationDetail(payment_date=pay_date, amount=amount)
            for key in order:
                if remaining <= 0:
                    break
                consumed = pay_toward(key, remaining, pay_date, alloc)
                remaining -= consumed
            return remaining, alloc

        def _attach_allocation(alloc: AllocationDetail) -> None:
            """把冲抵明细按批次归属挂到受影响的违约期行."""
            row_by_due = {row.due_date: row for row in default_rows}
            for due_date in sorted(alloc.touched_due_dates):
                row = row_by_due.get(due_date)
                if row is not None:
                    row.allocations.append(alloc)

        def annuity_payment(bal: Decimal, annual: Decimal, months: int) -> Decimal:
            """等额本息月供公式."""
            i = annual / Decimal("100") / Decimal("12")
            if i == 0:
                return (bal / Decimal(months)).quantize(CENT, rounding=ROUND_CEILING)
            factor = (Decimal(1) + i) ** months
            return bal * i * factor / (factor - Decimal(1))

        def reschedule(pay_date: date, reason: str) -> None:
            """提前还款后重排后续计划."""
            nonlocal \
                monthly_payment, \
                principal_part_plan, \
                remaining_periods, \
                reschedule_count, \
                current_rate, \
                prepayment_handling
            reschedule_count += 1
            if remaining_periods <= 0 or balance <= 0:
                return
            i = current_rate / Decimal("100") / Decimal("12")
            if repayment_method == REPAYMENT_EQUAL_PRINCIPAL:
                if prepayment_handling == PREPAY_REDUCE_PAYMENT:
                    principal_part_plan = balance / Decimal(remaining_periods)
                # 缩短期限：每期本金不变，期限自然缩短（余额减少）
                return
            # 等额本息
            if prepayment_handling == PREPAY_SHORTEN_TERM:
                if monthly_payment <= i * balance:
                    warnings.append("提前还款金额不足以在剩余期限内摊清（月供低于当期利息），已按月供递减方式重排")
                    prepayment_handling = PREPAY_REDUCE_PAYMENT
                    monthly_payment = annuity_payment(balance, current_rate, remaining_periods)
                    return
                growth = (Decimal(1) + i) ** 1
                ratio = Decimal(1) - i * balance / monthly_payment
                if ratio <= 0:
                    monthly_payment = annuity_payment(balance, current_rate, remaining_periods)
                    return
                months_needed = math.ceil(-math.log(float(ratio)) / math.log(float(growth)))
                remaining_periods = min(months_needed, remaining_periods)
                # 月供保持不变，仅缩短期限
            else:
                monthly_payment = annuity_payment(balance, current_rate, remaining_periods)

        # ---- 主事件循环 ----
        settled = False
        while not settled:
            period_no += 1
            due_date = add_months(first_due, period_no - 1)
            # 宽限期截止日：还款日+宽限期内还款视为按时
            grace_end = due_date + timedelta(days=grace_period_days) if grace_period_days else due_date

            # 1) 处理本期内（上一事件日, 宽限期截止日] 的还款事件
            while payment_idx < len(pay_records) and pay_records[payment_idx].payment_date <= grace_end:
                rec = pay_records[payment_idx]
                payment_idx += 1
                accrue(prev_event_date, rec.payment_date)
                prev_event_date = rec.payment_date

                if rec.payment_type == PAYMENT_TYPE_PREPAYMENT:
                    # 先按冲抵顺序清欠款（不含本金），余下直接冲减本金并重排
                    remaining_amt = rec.amount
                    alloc = AllocationDetail(payment_date=rec.payment_date, amount=rec.amount)
                    for key in order:
                        if remaining_amt <= 0:
                            break
                        if key == "principal":
                            break
                        consumed = pay_toward(key, remaining_amt, rec.payment_date, alloc)
                        remaining_amt -= consumed
                    if remaining_amt < rec.amount:
                        _attach_allocation(alloc)
                    if remaining_amt > 0:
                        # 提前还款补偿金：提前归还本金 × 补偿金率
                        if prepayment_compensation_rate is not None:
                            prepayment_compensation += remaining_amt * prepayment_compensation_rate / Decimal("100")
                        balance -= remaining_amt
                        if balance <= 0:
                            balance = Decimal("0")
                            settled = True
                            break
                        reschedule(rec.payment_date, "提前还款")
                else:
                    leftover, alloc = allocate_by_order(rec.amount, rec.payment_date, order)
                    if leftover > 0:
                        credit += leftover
                    if alloc.to_penalty or alloc.to_interest or alloc.to_compound or alloc.to_principal:
                        _attach_allocation(alloc)

                if settled:
                    break

            if settled:
                break

            if due_date > claim:
                # 截止日落在最后一期之后：退出，走尾期截算
                period_no -= 1
                break

            # 2) 罚息/复利按日累计至本期扣款日
            accrue(prev_event_date, due_date)
            prev_event_date = due_date

            # 3) 计息：本期利率（以扣款日为准）
            annual = contract_annual(due_date)
            i = annual / Decimal("100") / Decimal("12")
            rate_changed = annual != current_rate and period_no > 1
            current_rate = annual

            # 4) 本期应还
            if repayment_method == REPAYMENT_EQUAL_INSTALLMENT:
                if period_no == 1 or rate_changed:
                    if rate_changed:
                        reschedule_count += 1
                    monthly_payment = annuity_payment(balance, annual, remaining_periods)
                if period_no == 1 and first_period_interest == FIRST_PERIOD_PRORATE:
                    # 首期不规则：按放款日→首期扣款日实际天数计息（含零头天数）
                    stub_days = Decimal((due_date - start_date).days)
                    interest_due = _q(balance * annual / Decimal("100") * stub_days / Decimal(year_days))
                else:
                    interest_due = _q(balance * i)
                principal_due = monthly_payment - interest_due
                if principal_due > balance:
                    principal_due = balance
            else:
                if period_no == 1 and first_period_interest == FIRST_PERIOD_PRORATE:
                    stub_days = Decimal((due_date - start_date).days)
                    interest_due = _q(balance * annual / Decimal("100") * stub_days / Decimal(year_days))
                else:
                    interest_due = _q(balance * i)
                principal_due = principal_part_plan if principal_part_plan <= balance else balance

            if principal_due <= 0:
                # 本金已还清，无需继续生成期次
                period_no -= 1
                break

            # 4) 用溢缴款支付本期应还（按冲抵顺序在 利息/本金 之间分配）
            due_alloc = AllocationDetail(payment_date=due_date, amount=credit, direct=True)
            credit_remaining = credit
            for key in order:
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
            credit = credit_remaining

            # 5) 未付部分形成欠款批次（起罚日 = 宽限期截止日次日起算）
            shortfall_interest = interest_due - paid_interest
            shortfall_principal = principal_due - paid_principal
            penalty_start = grace_end + timedelta(days=1)
            if shortfall_interest > 0:
                lot = _Lot(due_date=due_date, amount=shortfall_interest)
                interest_lots.append(lot)
                overdue_start_dates[due_date] = penalty_start
            if shortfall_principal > 0:
                lot = _Lot(due_date=due_date, amount=shortfall_principal)
                principal_lots.append(lot)
                overdue_start_dates[due_date] = penalty_start
                # 逾期本金仍计合同利息（包含在 balance 中），不再重复计提

            balance -= paid_principal

            # 6) 记录计划行与违约行
            interest_part = interest_due
            schedule_rows.append(
                ScheduleRow(
                    period_no=period_no,
                    due_date=due_date,
                    monthly_payment=_q(principal_due + interest_due),
                    principal_part=_q(principal_due),
                    interest_part=interest_part,
                    annual_rate=annual,
                    remaining_principal=_q(balance),
                    rescheduled=rate_changed,
                )
            )
            default_rows.append(
                DefaultRow(
                    period_no=period_no,
                    due_date=due_date,
                    due_principal=_q(principal_due),
                    due_interest=interest_due,
                    paid_principal=_q(paid_principal),
                    paid_interest=_q(paid_interest),
                    status=self._status(shortfall_principal, shortfall_interest),
                    overdue_days=0,
                    accrued_penalty=Decimal("0"),
                    accrued_compound=Decimal("0"),
                    annual_rate=annual,
                    allocations=[due_alloc] if (paid_principal or paid_interest) else [],
                )
            )

            remaining_periods -= 1
            if balance <= 0:
                settled = True
                break
            if remaining_periods <= 0:
                # 贷款到期但本金未清：此后仅计罚息/复利
                break

        # ---- 尾期截算：从最后事件日到 claim ----
        if prev_event_date < claim:
            accrue(prev_event_date, claim)
            # 未到期期间的合同利息按天截算
            if balance > 0 and remaining_periods > 0:
                annual = contract_annual(prev_event_date)
                stub_days = (claim - prev_event_date).days
                stub_interest = balance * annual / Decimal("100") * stub_days / Decimal(year_days)
                if stub_interest > 0:
                    interest_lots.append(_Lot(due_date=claim, amount=stub_interest))

        # ---- 汇总 ----
        unpaid_interest = sum((lot.amount for lot in interest_lots), Decimal("0"))
        penalty_outstanding = penalty_accrued_total - penalty_paid
        if compound_method == COMPOUND_METHOD_FLAT:
            # 复利不分段：积数 × 收取复利时（截止日）适用的罚息利率
            flat_rate = penalty_annual(claim) / Decimal("100") / Decimal(year_days)
            compound_from_interest = compound_interest_accrued * flat_rate
            compound_from_penalty = penalty_compound_accrued * flat_rate
            compound_outstanding = compound_from_interest + compound_from_penalty - compound_paid
        else:
            compound_outstanding = compound_accrued_total - compound_paid + penalty_compound_total
        outstanding_principal = max(balance, Decimal("0"))
        p_daily = penalty_annual(claim) / Decimal("100") / Decimal(year_days)
        daily_accrual = outstanding_principal * p_daily + unpaid_interest * p_daily
        if compound_on_penalty:
            daily_accrual += (penalty_accrued_total - penalty_paid) * p_daily

        # 其他费用（律师费/诉讼费/提前还款补偿金等，不参与利息计算）
        fee_items: list[dict] = list(other_fees or [])
        if prepayment_compensation > 0:
            fee_items.append({"name": "提前还款补偿金", "amount": _str_money(prepayment_compensation)})
        other_fees_total = sum((Decimal(str(f.get("amount", 0))) for f in fee_items), Decimal("0"))

        if reschedule_count:
            warnings.append(f"因提前还款/利率重定价共重排还款计划 {reschedule_count} 次，明细以重排后计划为准")
        if compound_on_penalty:
            warnings.append("已开启「对罚息再计复利」，该口径依赖合同约定，请核对后再引用")
        if compound_method == COMPOUND_METHOD_FLAT and (compound_on_interest or compound_on_penalty):
            warnings.append("复利按「不分段」口径计算（积数×收取时罚息利率），如合同约定分段计收请改用逐日模式")
        if grace_period_days:
            warnings.append(
                f"宽限期 {grace_period_days} 天：还款日+宽限期内还款视为按时，罚息/复利自宽限期届满次日起算"
            )
        if charge_interest_on_payment_day:
            warnings.append("逾期天数包含还款日当日（算至实际还款日）口径")

        # 批次归属回填违约行：逾期天数、罚息/复利、还款冲抵金额
        row_by_due = {row.due_date: row for row in default_rows}
        penalty_by_due: dict[date, Decimal] = {}
        compound_by_due: dict[date, Decimal] = {}
        for lot in principal_lots:
            penalty_by_due[lot.due_date] = penalty_by_due.get(lot.due_date, Decimal("0")) + lot.accrued_penalty
        for lot in interest_lots:
            compound_by_due[lot.due_date] = compound_by_due.get(lot.due_date, Decimal("0")) + lot.accrued_compound
        for row in default_rows:
            row.accrued_penalty += penalty_by_due.get(row.due_date, Decimal("0"))
            row.accrued_compound += compound_by_due.get(row.due_date, Decimal("0"))
            if row.status != STATUS_PAID:
                # 逾期天数：默认从计划还款日起算至实际还款日前一日/截止日；
                # 有宽限期时从宽限期届满次日起算；charge_interest_on_payment_day 时含还款日当日
                start = overdue_start_dates.get(row.due_date, row.due_date)
                end_adj = claim + timedelta(days=1) if charge_interest_on_payment_day else claim
                row.overdue_days = max(row.overdue_days, max((end_adj - start).days, 0))
            # 还款事件冲抵的利息/本金按期次并入行级已还金额（due_alloc 已直接计入）
            for alloc in row.allocations:
                if alloc.direct:
                    continue
                row.paid_interest += alloc.interest_by_due.get(row.due_date, Decimal("0"))
                row.paid_principal += alloc.principal_by_due.get(row.due_date, Decimal("0"))

        claim_summary = ClaimSummary(
            claim_date=claim,
            outstanding_principal=_q(outstanding_principal),
            unpaid_interest=_q(unpaid_interest),
            penalty_interest=_q(penalty_outstanding),
            compound_interest=_q(compound_outstanding),
            total_claim=_q(
                _q(outstanding_principal)
                + _q(unpaid_interest)
                + _q(penalty_outstanding)
                + _q(compound_outstanding)
                + _q(other_fees_total)
            ),
            daily_accrual=_q(daily_accrual),
            other_fees=_q(other_fees_total),
            fee_items=[
                {"name": f.get("name", ""), "amount": _str_money(Decimal(str(f.get("amount", 0))))} for f in fee_items
            ],
        )
        # 逐期罚息/复利四舍五入展示
        for row in default_rows:
            row.paid_interest = _q(row.paid_interest)
            row.paid_principal = _q(row.paid_principal)
            row.accrued_penalty = _q(row.accrued_penalty)
            row.accrued_compound = _q(row.accrued_compound)
        return MortgageDefaultResult(
            claim=claim_summary,
            schedule_rows=schedule_rows,
            default_rows=default_rows,
            warnings=warnings,
            meta={
                "repayment_method": repayment_method,
                "rate_mode": rate_mode,
                "penalty_mode": penalty_mode,
                "compound_method": compound_method,
                "grace_period_days": grace_period_days,
                "first_period_interest": first_period_interest,
                "charge_interest_on_payment_day": charge_interest_on_payment_day,
                "allocation_order": order,
                "year_days": year_days,
                "first_due_date": first_due.isoformat(),
                "term_months": term_months,
            },
        )

    # ------------------------------------------------------------------
    # 内部工具
    # ------------------------------------------------------------------

    @staticmethod
    def _status(shortfall_principal: Decimal, shortfall_interest: Decimal) -> str:
        if shortfall_principal <= 0 and shortfall_interest <= 0:
            return STATUS_PAID
        if shortfall_principal >= 0 and shortfall_interest >= 0:
            # 部分支付时两者至少一个为正
            return STATUS_PARTIAL if (shortfall_principal < 1 or shortfall_interest < 1) else STATUS_UNPAID
        return STATUS_PARTIAL

    @staticmethod
    def _first_due_date(start_date: date, payment_day: int | None) -> date:
        """首期扣款日：payment_day 指定日（1-31）或放款日对应日，至少在放款日之后一个月.

        指定日超出当月天数时钳制到月末（如每月31日，2月取28/29日）。
        """
        day = payment_day or start_date.day
        first_candidate = add_months(start_date.replace(day=1), 1)
        # 钳制到当月最后一天
        if day > first_candidate.day:
            day = first_candidate.day
        first_candidate = first_candidate.replace(day=day)
        # 放款对应日场景：保证首期在放款日之后
        if first_candidate <= start_date:
            first_candidate = add_months(first_candidate, 1)
        return first_candidate

    def _build_contract_rate_resolver(
        self,
        *,
        rate_mode: str,
        fixed_rate: Decimal | None,
        lpr_type: str,
        basis_points: Decimal,
        repricing_day: str,
        start_date: date,
    ) -> Callable[[date], Decimal]:
        """构建合同年利率解析函数：给定日期返回适用年利率(%)."""
        if rate_mode == RATE_MODE_FIXED:
            assert fixed_rate is not None  # _validate_inputs 已保证
            return lambda on: fixed_rate

        cache: dict[date, Decimal] = {}

        def resolve(on: date) -> Decimal:
            rdate = self._last_repricing_date(start_date, on, repricing_day)
            if rdate not in cache:
                rate = self.rate_service.get_rate_at(rdate)
                base = rate.rate_5y if lpr_type == "5y" else rate.rate_1y
                cache[rdate] = base + basis_points / Decimal("100")
            return cache[rdate]

        return resolve

    @staticmethod
    def _last_repricing_date(start_date: date, on: date, repricing_day: str) -> date:
        """返回 on 之前（含）最近的重定价日；无则返回放款日（初始定价）."""
        if repricing_day == "anniversary":
            month, day = start_date.month, start_date.day
        else:
            month_s, day_s = repricing_day.split("-")
            month, day = int(month_s), int(day_s)

        for year in range(on.year, start_date.year - 1, -1):
            candidate = MortgageDefaultCalculator._safe_date(year, month, day)
            if candidate <= on and candidate >= start_date:
                return candidate
            if candidate < start_date and year == start_date.year:
                break
        return start_date

    @staticmethod
    def _safe_date(year: int, month: int, day: int) -> date:
        day = min(day, 28 if month == 2 else 30)
        return date(year, month, day)

    @staticmethod
    def _normalize_allocation_order(allocation_order: list[str] | None) -> list[str]:
        if not allocation_order:
            return list(DEFAULT_ALLOCATION_ORDER)
        cleaned = [k for k in allocation_order if k in VALID_ALLOCATION_KEYS]
        # 去重并保持顺序
        seen: set[str] = set()
        ordered: list[str] = []
        for k in cleaned:
            if k not in seen:
                seen.add(k)
                ordered.append(k)
        # 补齐缺失的 bucket（追加到末尾）
        for key in DEFAULT_ALLOCATION_ORDER:
            if key not in ordered:
                ordered.append(key)
        return ordered

    @staticmethod
    def _normalize_payments(
        payments: list[PaymentRecord], start_date: date, warnings: list[str]
    ) -> list[PaymentRecord]:
        cleaned = []
        for rec in payments:
            if rec.amount <= 0:
                warnings.append(f"忽略无效还款记录：{rec.payment_date} 金额 {rec.amount}")
                continue
            if rec.payment_date < start_date:
                warnings.append(f"忽略早于放款日的还款记录：{rec.payment_date}")
                continue
            if rec.payment_type not in VALID_PAYMENT_TYPES:
                warnings.append(f"未知还款类型 {rec.payment_type}，按正常还款处理：{rec.payment_date}")
                rec = PaymentRecord(rec.payment_date, rec.amount, PAYMENT_TYPE_NORMAL, rec.note)
            cleaned.append(rec)
        cleaned.sort(key=lambda r: (r.payment_date, 0 if r.payment_type == PAYMENT_TYPE_NORMAL else 1))
        return cleaned

    @staticmethod
    def _validate_inputs(
        *,
        principal: Decimal,
        start_date: date,
        term_months: int,
        repayment_method: str,
        rate_mode: str,
        fixed_rate: Decimal | None,
        penalty_mode: str,
        penalty_rate: Decimal | None,
        year_days: int,
        compound_method: str = COMPOUND_METHOD_DAILY,
        first_period_interest: str = FIRST_PERIOD_PRORATE,
        grace_period_days: int = 0,
    ) -> None:
        if principal <= 0:
            raise ValidationException(message="贷款本金必须大于0", code="INVALID_PRINCIPAL")
        if term_months < 1:
            raise ValidationException(message="贷款期限至少为1个月", code="INVALID_TERM")
        if repayment_method not in VALID_REPAYMENT_METHODS:
            raise ValidationException(
                message="还款方式仅支持 equal_installment（等额本息）或 equal_principal（等额本金）",
                code="INVALID_REPAYMENT_METHOD",
            )
        if rate_mode not in (RATE_MODE_FIXED, RATE_MODE_LPR):
            raise ValidationException(message="利率模式仅支持 fixed 或 lpr", code="INVALID_RATE_MODE")
        if rate_mode == RATE_MODE_FIXED and (fixed_rate is None or fixed_rate <= 0):
            raise ValidationException(message="固定利率模式必须提供大于0的年利率", code="INVALID_FIXED_RATE")
        if penalty_mode == PENALTY_MODE_SPECIFIED and (penalty_rate is None or penalty_rate <= 0):
            raise ValidationException(message="直接指定罚息利率时必须提供大于0的年利率", code="INVALID_PENALTY_RATE")
        if year_days not in (360, 365):
            raise ValidationException(message="计息基准仅支持 360 或 365 天", code="INVALID_YEAR_DAYS")
        if compound_method not in (COMPOUND_METHOD_DAILY, COMPOUND_METHOD_FLAT):
            raise ValidationException(message="复利计算方式仅支持 daily 或 flat", code="INVALID_COMPOUND_METHOD")
        if first_period_interest not in (FIRST_PERIOD_PRORATE, FIRST_PERIOD_FULL_MONTH):
            raise ValidationException(
                message="首期计息方式仅支持 prorate 或 full_month", code="INVALID_FIRST_PERIOD_INTEREST"
            )
        if grace_period_days < 0:
            raise ValidationException(message="宽限期天数不能为负", code="INVALID_GRACE_PERIOD")
