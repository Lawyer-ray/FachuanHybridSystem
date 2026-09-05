"""LPR相关API Schema定义."""

from __future__ import annotations

from datetime import date
from decimal import Decimal
from typing import Literal

from ninja import Field, Schema


class LPRRateSchema(Schema):
    """LPR利率数据Schema."""

    id: int
    effective_date: date
    rate_1y: Decimal = Field(..., description="一年期LPR(%)")
    rate_5y: Decimal = Field(..., description="五年期LPR(%)")
    source: str = Field("", description="数据来源")
    is_auto_synced: bool = Field(False, description="是否自动同步")
    created_at: str
    updated_at: str


class LPRRateListResponse(Schema):
    """LPR利率列表响应."""

    items: list[LPRRateSchema]
    total: int


class LPRSyncRequest(Schema):
    """LPR同步请求."""

    force: bool = Field(False, description="强制同步，忽略缓存")


class LPRSyncResponse(Schema):
    """LPR同步响应."""

    success: bool
    message: str
    created: int = Field(0, description="新增记录数")
    updated: int = Field(0, description="更新记录数")
    skipped: int = Field(0, description="跳过记录数")
    task_id: str | None = Field(None, description="后台任务ID（异步模式下返回）")


class LPRSyncStatusResponse(Schema):
    """LPR同步状态响应."""

    latest_rate_date: date | None
    total_records: int
    auto_synced_records: int
    manual_records: int


class PrincipalChangeSchema(Schema):
    """本金变动Schema."""

    start_date: date = Field(..., description="开始日期")
    end_date: date = Field(..., description="结束日期")
    principal: Decimal = Field(..., description="本金金额")


class InterestCalculateRequest(Schema):
    """利息计算请求."""

    start_date: date | None = Field(None, description="开始日期（固定本金模式必填）")
    end_date: date | None = Field(None, description="结束日期（固定本金模式必填）")
    principal: Decimal | None = Field(None, description="本金（固定本金模式必填）")
    # 利率模式
    rate_mode: Literal["lpr", "custom"] = Field("lpr", description="利率模式: lpr=LPR利率, custom=自定义利率")
    # LPR模式参数
    rate_type: Literal["1y", "5y"] = Field("1y", description="利率类型（LPR模式）")
    multiplier: Decimal = Field(Decimal("1"), description="利率倍数（LPR模式）")
    # 自定义利率模式参数
    custom_rate_unit: Literal["percent", "permille", "permyriad"] = Field(
        "percent", description="自定义利率单位: percent=百分之, permille=千分之, permyriad=万分之"
    )
    custom_rate_value: Decimal | None = Field(None, description="自定义利率数值（如5表示千分之5）")
    # 通用参数
    year_days: int = Field(360, description="年基准天数(360/365/0实际天数)")
    date_inclusion: Literal["both", "start_only", "end_only", "neither"] = Field(
        "both",
        description="日期计算方式: both=均计算在内, start_only=仅起始日期, end_only=仅截止日期, neither=均不计算",
    )
    principal_changes: list[PrincipalChangeSchema] | None = Field(
        None, description="本金变动列表（如提供则使用变动本金计算，此时不需要start_date/end_date/principal）"
    )


class CalculationPeriodSchema(Schema):
    """计算分段明细Schema."""

    start_date: date
    end_date: date
    principal: Decimal
    rate: Decimal
    rate_unit: str | None = Field(None, description="利率单位: percent/permille/permyriad")
    days: int
    year_days: int
    interest: Decimal


class InterestCalculateResponse(Schema):
    """利息计算响应."""

    success: bool
    total_interest: Decimal | None = None
    total_principal: Decimal | None = None
    total_days: int | None = None
    start_date: date | None = None
    end_date: date | None = None
    periods: list[CalculationPeriodSchema] | None = None
    message: str | None = None
    code: str | None = None
    sync_info: str | None = Field(None, description="自动同步提示信息")


# ---------------------------------------------------------------------------
# 房贷逾期违约债权计算（mortgage default）
# ---------------------------------------------------------------------------


class MortgagePaymentSchema(Schema):
    """还款流水记录Schema."""

    payment_date: date = Field(..., description="还款日期")
    amount: Decimal = Field(..., description="还款金额（元）")
    payment_type: Literal["normal", "prepayment_principal"] = Field(
        "normal", description="类型: normal=正常还款, prepayment_principal=提前冲减本金"
    )
    note: str = Field("", description="备注")


class MortgageAmortizeRequest(Schema):
    """房贷摊销计算请求."""

    principal: Decimal = Field(..., description="贷款本金（元）")
    start_date: date = Field(..., description="放款日期")
    term_months: int = Field(..., description="贷款期限（月）")
    repayment_method: Literal["equal_installment", "equal_principal"] = Field(
        "equal_installment", description="还款方式"
    )
    payment_day: int | None = Field(None, ge=1, le=28, description="每月扣款日（1-28），不填取放款日对应日")
    rate_mode: Literal["fixed", "lpr"] = Field("fixed", description="利率模式")
    fixed_rate: Decimal | None = Field(None, description="固定年利率(%)，fixed 模式必填")
    lpr_type: Literal["1y", "5y"] = Field("5y", description="LPR 期限品种（lpr 模式）")
    basis_points: Decimal = Field(Decimal("0"), description="LPR 加点（基点，100bp=1%，可为负）")
    repricing_day: str = Field("01-01", description="重定价日：MM-DD 或 anniversary（放款对应日）")


class ScheduleRowSchema(Schema):
    """还款计划行Schema."""

    period_no: int
    due_date: date
    monthly_payment: str
    principal_part: str
    interest_part: str
    annual_rate: str
    remaining_principal: str
    rescheduled: bool


class OtherFeeSchema(Schema):
    """其他费用Schema."""

    name: str = Field("", description="费用名称，如 律师费/诉讼费/提前还款补偿金")
    amount: Decimal = Field(..., description="金额（元）")


class MortgageDefaultRequest(MortgageAmortizeRequest):
    """房贷逾期违约债权计算请求."""

    penalty_mode: Literal["multiplier", "specified"] = Field(
        "multiplier", description="罚息利率模式: multiplier=执行利率×倍数, specified=直接指定"
    )
    penalty_multiplier: Decimal = Field(Decimal("1.5"), description="罚息倍数（multiplier 模式）")
    penalty_rate: Decimal | None = Field(None, description="罚息年利率(%)（specified 模式必填）")
    compound_on_interest: bool = Field(True, description="是否对欠付利息计收复利")
    compound_on_penalty: bool = Field(False, description="是否对罚息再计收复利")
    year_days: Literal[360, 365] = Field(360, description="罚息/复利计息基准天数")
    allocation_order: list[str] | None = Field(
        None, description="冲抵顺序，可选值 penalty/interest/compound/principal，默认 罚息→利息→复利→本金"
    )
    prepayment_handling: Literal["shorten_term", "reduce_payment"] = Field(
        "shorten_term", description="提前还款重排方式"
    )
    prepayment_compensation_rate: Decimal | None = Field(
        None, description="提前还款补偿金率(%)，如 1.00 表示提前归还本金的 1%，不填表示无"
    )
    compound_method: Literal["daily", "flat"] = Field(
        "daily", description="复利计算方式: daily=逐日按当日罚息利率分段, flat=不分段(积数×收取时罚息利率，如交行)"
    )
    grace_period_days: int = Field(0, ge=0, description="宽限期天数（还款日+宽限期内还款视为按时）")
    first_period_interest: Literal["prorate", "full_month"] = Field(
        "prorate", description="首期计息: prorate=按放款日→首期扣款日实际天数, full_month=整月"
    )
    charge_interest_on_payment_day: bool = Field(
        False, description="逾期天数是否含还款日当日（交行等约定算至还款日前一日则为 false）"
    )
    other_fees: list[OtherFeeSchema] = Field(
        default_factory=list, description="其他费用（律师费/诉讼费等，仅计入合计）"
    )
    payments: list[MortgagePaymentSchema] = Field(default_factory=list, description="还款流水")
    claim_date: date | None = Field(None, description="计算截止日（默认今天）")


class AllocationDetailSchema(Schema):
    """冲抵明细Schema."""

    payment_date: date
    amount: str
    to_penalty: str
    to_interest: str
    to_compound: str
    to_principal: str


class DefaultRowSchema(Schema):
    """逐期违约明细Schema."""

    period_no: int
    due_date: date
    due_principal: str
    due_interest: str
    paid_principal: str
    paid_interest: str
    status: str
    overdue_days: int
    accrued_penalty: str
    accrued_compound: str
    annual_rate: str
    note: str
    allocations: list[AllocationDetailSchema]


class ClaimSummarySchema(Schema):
    """诉讼请求金额汇总Schema."""

    claim_date: date
    outstanding_principal: str
    unpaid_interest: str
    penalty_interest: str
    compound_interest: str
    other_fees: str = "0.00"
    fee_items: list[OtherFeeSchema] = Field(default_factory=list)
    total_claim: str
    daily_accrual: str


class MortgageDefaultResponse(Schema):
    """房贷逾期违约债权计算响应."""

    success: bool
    message: str | None = None
    code: str | None = None
    claim: ClaimSummarySchema | None = None
    schedule_rows: list[ScheduleRowSchema] | None = None
    default_rows: list[DefaultRowSchema] | None = None
    warnings: list[str] | None = None
    meta: dict | None = None


class MortgageAmortizeResponse(Schema):
    """房贷摊销计算响应."""

    success: bool
    message: str | None = None
    code: str | None = None
    schedule_rows: list[ScheduleRowSchema] | None = None
    first_due_date: str = Field("", description="首期扣款日")
    total_periods: int = Field(0, description="计划期数")
