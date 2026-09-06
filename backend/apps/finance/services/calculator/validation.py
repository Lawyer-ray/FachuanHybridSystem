"""房贷逾期计算：输入校验（纯函数，无状态）."""

from __future__ import annotations

from datetime import date, timedelta
from decimal import Decimal

from apps.core.exceptions import ValidationException
from apps.finance.services.calculator.mortgage_models import (
    CAP_TOTAL_NONE,
    COMPOUND_METHOD_DAILY,
    COMPOUND_METHOD_FLAT,
    FIRST_PERIOD_FULL_MONTH,
    FIRST_PERIOD_PRORATE,
    PAYMENT_TYPE_NORMAL,
    PENALTY_MODE_SPECIFIED,
    RATE_MODE_FIXED,
    RATE_MODE_LPR,
    VALID_ALLOCATION_KEYS,
    VALID_CAP_TOTAL_MODES,
    VALID_CLAIM_MODES,
    VALID_PAYMENT_TYPES,
    VALID_REPAYMENT_METHODS,
    VALID_ROUNDING_MODES,
    PausePeriod,
    PaymentRecord,
)


def validate_inputs(
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
    """校验贷款基本参数."""
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


def validate_lump(
    *,
    lump_penalty_rate: Decimal | None,
    lump_penalty_amount: Decimal | None,
    lump_penalty_threshold_days: int,
) -> None:
    """校验一次性违约金参数."""
    if lump_penalty_rate is not None and lump_penalty_rate < 0:
        raise ValidationException(message="一次性违约金率不能为负", code="INVALID_LUMP_RATE")
    if lump_penalty_amount is not None and lump_penalty_amount < 0:
        raise ValidationException(message="一次性违约金金额不能为负", code="INVALID_LUMP_AMOUNT")
    if lump_penalty_threshold_days < 0:
        raise ValidationException(message="违约金触发天数不能为负", code="INVALID_LUMP_THRESHOLD")


def validate_step_up(*, step_up_rate: Decimal | None, step_up_trigger_days: int) -> None:
    """校验逾期自动加码参数."""
    if step_up_rate is not None and step_up_rate < 0:
        raise ValidationException(message="逾期加码比例不能为负", code="INVALID_STEP_UP_RATE")
    if step_up_trigger_days < 0:
        raise ValidationException(message="逾期加码触发天数不能为负", code="INVALID_STEP_UP_TRIGGER")


def validate_claim_config(
    *,
    rounding_mode: str,
    claim_mode: str,
    accelerate_grace_days: int,
    cap_penalty_annual: Decimal | None,
    cap_total_mode: str,
    cap_total_value: Decimal,
    claim: date,
    start_date: date,
) -> None:
    """校验主张口径/加速宽限/封顶/截止日 等通用配置."""
    if rounding_mode not in VALID_ROUNDING_MODES:
        raise ValidationException(
            message="舍入规则仅支持 period（逐期）或 cumulative（累计）", code="INVALID_ROUNDING_MODE"
        )
    if claim_mode not in VALID_CLAIM_MODES:
        raise ValidationException(
            message="主张口径仅支持 both（并行叠加）或 either（择一从高）", code="INVALID_CLAIM_MODE"
        )
    if accelerate_grace_days < 0:
        raise ValidationException(message="加速到期宽限天数不能为负", code="INVALID_ACCELERATE_GRACE")
    if cap_penalty_annual is not None and cap_penalty_annual < 0:
        raise ValidationException(message="罚息/复利年利率封顶值不能为负", code="INVALID_CAP_PENALTY_ANNUAL")
    if cap_total_mode not in VALID_CAP_TOTAL_MODES:
        raise ValidationException(
            message="总债权封顶模式仅支持 none/amount/principal_ratio/interest_ratio",
            code="INVALID_CAP_TOTAL_MODE",
        )
    if cap_total_mode != CAP_TOTAL_NONE and cap_total_value <= 0:
        raise ValidationException(message="总债权封顶值必须大于 0", code="INVALID_CAP_TOTAL_VALUE")
    if claim <= start_date:
        raise ValidationException(message="计算截止日必须晚于放款日期", code="INVALID_CLAIM_DATE")


def build_pause_ranges(pause_periods: list[PausePeriod] | None) -> list[tuple[date, date]]:
    """把停息区间转换为 (start, end) 列表并做合法性校验（end 含当日）."""
    ranges: list[tuple[date, date]] = []
    for p in pause_periods or []:
        if p.start > p.end:
            raise ValidationException(
                message=f"停息区间 {p.start}~{p.end} 起始日不能晚于结束日",
                code="INVALID_PAUSE_PERIOD",
            )
        ranges.append((p.start, p.end))
    return ranges


def resolve_accelerate_penalty_start(
    *,
    accelerate_date: date | None,
    accelerate_grace_days: int,
    start_date: date,
    claim: date,
    warnings: list[str],
) -> date | None:
    """校验加速到期日并返回加速后罚息起算日；不触发时返回 None."""
    if accelerate_date is None:
        return None
    if accelerate_date <= start_date:
        raise ValidationException(message="加速到期日必须晚于放款日期", code="INVALID_ACCELERATE_DATE")
    if accelerate_date >= claim:
        warnings.append(f"加速到期日 {accelerate_date} 不早于计算截止日，本次不触发加速到期")
        return None
    return accelerate_date + timedelta(days=accelerate_grace_days) + timedelta(days=1)


def normalize_allocation_order(allocation_order: list[str] | None) -> list[str]:
    """规范化冲抵顺序：去重、过滤非法项、按补全顺序补齐缺失 bucket."""
    from apps.finance.services.calculator.mortgage_models import _ALLOCATION_FILL_ORDER, DEFAULT_ALLOCATION_ORDER

    if not allocation_order:
        return list(DEFAULT_ALLOCATION_ORDER)
    cleaned = [k for k in allocation_order if k in VALID_ALLOCATION_KEYS]
    seen: set[str] = set()
    ordered: list[str] = []
    for k in cleaned:
        if k not in seen:
            seen.add(k)
            ordered.append(k)
    for key in _ALLOCATION_FILL_ORDER:
        if key not in ordered:
            ordered.append(key)
    return ordered


def normalize_payments(payments: list[PaymentRecord], start_date: date, warnings: list[str]) -> list[PaymentRecord]:
    """过滤无效还款记录并按日期排序."""
    cleaned: list[PaymentRecord] = []
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
