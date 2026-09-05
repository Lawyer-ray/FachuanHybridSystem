"""房贷逾期违约债权计算的「数据模型」模块.

从 mortgage_calculator 中拆出常量、金额/日期工具与全部结果 dataclass，
让核心算法模块专注「怎么算」。数据契约独立维护，便于新增口径时不动算法。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, timedelta
from decimal import ROUND_HALF_UP, Decimal

CENT = Decimal("0.01")


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

# 冲抵顺序（penalty_lump=一次性违约金/逾期违约金；fee=诉讼费用，默认不参与核销，
# 仅当用户在冲抵顺序中显式放入 "fee" 时才按序核销费用，实现「费用可参与冲抵」）
VALID_ALLOCATION_KEYS = {"penalty", "interest", "compound", "principal", "penalty_lump", "fee"}
DEFAULT_ALLOCATION_ORDER = ["penalty", "interest", "compound", "principal"]
# 补齐缺失 bucket 时使用的顺序（违约金默认排在最后，不影响未配置违约金时的默认数字）
_ALLOCATION_FILL_ORDER = ["penalty", "interest", "compound", "principal", "penalty_lump"]

# 冲抵立场（其实是 order 的快捷预设，算法不做特殊分支，避免耦合）
ALLOCATION_STANCE_INTEREST_FIRST = "interest_first"  # 先息后本（常规主张）
ALLOCATION_STANCE_PRINCIPAL_FIRST = "principal_first"  # 先本后息（担保物权立场）
ALLOCATION_STANCE_PRESETS: dict[str, list[str]] = {
    "interest_first": ["penalty", "interest", "compound", "penalty_lump", "principal"],
    "principal_first": ["principal", "penalty", "interest", "compound", "penalty_lump"],
}

# 复利计算方式
COMPOUND_METHOD_DAILY = "daily"  # 逐日按当日罚息利率分段计算
COMPOUND_METHOD_FLAT = "flat"  # 不分段：积数 × 收取复利时适用的罚息利率（如交行 13.1）

# 首期计息方式
FIRST_PERIOD_PRORATE = "prorate"  # 按放款日→首期扣款日实际天数计息（含零头天数）
FIRST_PERIOD_FULL_MONTH = "full_month"  # 首期按整月计息

# 舍入规则
ROUNDING_PERIOD = "period"  # 逐期四舍五入到分再求和
ROUNDING_CUMULATIVE = "cumulative"  # 全程保持精度，仅在诉讼请求汇总时一次性四舍五入到分
VALID_ROUNDING_MODES = {ROUNDING_PERIOD, ROUNDING_CUMULATIVE}

# 违约金与罚息主张口径
CLAIM_MODE_BOTH = "both"  # 并行叠加：罚息与一次性违约金同时计入诉请
CLAIM_MODE_EITHER = "either"  # 择一从高：取罚息与违约金中较大者计入诉请
VALID_CLAIM_MODES = {CLAIM_MODE_BOTH, CLAIM_MODE_EITHER}

# 状态
STATUS_PAID = "paid"
STATUS_PARTIAL = "partial"
STATUS_UNPAID = "unpaid"


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
    to_penalty_lump: Decimal = field(default_factory=lambda: Decimal("0"))
    to_interest: Decimal = field(default_factory=lambda: Decimal("0"))
    to_compound: Decimal = field(default_factory=lambda: Decimal("0"))
    to_principal: Decimal = field(default_factory=lambda: Decimal("0"))
    to_fee: Decimal = field(default_factory=lambda: Decimal("0"))
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
    lump_penalty: Decimal = field(default_factory=lambda: Decimal("0"))  # 一次性违约金/逾期违约金
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
                "lump_penalty": _str_money(self.claim.lump_penalty),
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
                            "to_penalty_lump": _str_money(a.to_penalty_lump),
                            "to_interest": _str_money(a.to_interest),
                            "to_compound": _str_money(a.to_compound),
                            "to_principal": _str_money(a.to_principal),
                            "to_fee": _str_money(a.to_fee),
                        }
                        for a in r.allocations
                    ],
                }
                for r in self.default_rows
            ],
            "warnings": self.warnings,
            "meta": self.meta,
        }
