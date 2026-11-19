"""房贷摊销与逾期违约债权计算 MCP tools（银行诉讼场景）.

法律口径说明（供 AI 正确构造参数）：
- 罚息：逾期本金按罚息利率按日计息。罚息利率两种模式：
  multiplier = 执行利率 × 倍数（常见 1.5 倍，依据央行规定上浮 30%-50%）
  specified  = 合同直接约定的罚息年利率
- 复利：对未按时支付的利息按罚息利率计收的利息；是否对罚息再计复利取决于合同约定与司法裁判口径。
- 冲抵顺序：还款金额核销顺序，默认 罚息→利息→复利→本金，不同银行合同约定不同，可自定义。
- 金额输出均为两位小数字符串。
"""

from __future__ import annotations

from typing import Annotated, Any, Literal

from pydantic import Field

from mcp_server.client import client

#: 与后端 MortgageDefaultCalculateRequest 的 Literal 逐值对账(门禁 test_schema_param_descriptions)。
_RepayL = Literal["equal_installment", "equal_principal"]
_RateModeL = Literal["fixed", "lpr"]
_LprTypeL = Literal["1y", "5y"]
_PenaltyModeL = Literal["multiplier", "specified"]
_CompoundMethodL = Literal["daily", "flat"]
_FirstPeriodL = Literal["prorate", "full_month"]
_AllocationStanceL = Literal["interest_first", "principal_first"]
_PrepayHandlingL = Literal["shorten_term", "reduce_payment"]
_RoundingL = Literal["period", "cumulative"]
_ClaimModeL = Literal["both", "either"]
_CapTotalModeL = Literal["none", "amount", "principal_ratio", "interest_ratio"]


def mortgage_amortize(
    principal: Annotated[float, Field(description="贷款本金(元)", gt=0)],
    start_date: Annotated[str, Field(description="放款日期,YYYY-MM-DD")],
    term_months: Annotated[int, Field(description="贷款期限(月)", ge=1)],
    repayment_method: Annotated[Literal["equal_installment", "equal_principal"], Field(description="还款方式:equal_installment 等额本息(月供固定)/equal_principal 等额本金(月供递减)")] = "equal_installment",
    payment_day: Annotated[int | None, Field(description="每月扣款日(1-28),不填取放款日对应日", ge=1, le=28)] = None,
    rate_mode: Annotated[Literal["fixed", "lpr"], Field(description="利率模式:fixed 固定利率/lpr=LPR+基点浮动")] = "fixed",
    fixed_rate: Annotated[float | None, Field(description="固定年利率(%),rate_mode=fixed 时必填,如 4.2", gt=0)] = None,
    lpr_type: Annotated[Literal["1y", "5y"], Field(description="LPR 期限品种,1y 或 5y(房贷一般 5y),rate_mode=lpr 时使用")] = "5y",
    basis_points: Annotated[float, Field(description="LPR 加点基点,100bp=1%,可为负(如 LPR-30bp 传 -30)")] = 0.0,
    repricing_day: Annotated[str, Field(description='重定价日,"MM-DD"(如 "01-01")或 "anniversary"(放款日对应日)')] = "01-01",
) -> dict[str, Any]:
    """生成房贷还款计划（等额本息/等额本金摊销表）。

    Args:
        principal: 贷款本金（元）。
        start_date: 放款日期，格式 YYYY-MM-DD。
        term_months: 贷款期限（月）。
        repayment_method: 还款方式，equal_installment=等额本息（月供固定），equal_principal=等额本金（月供递减）。
        payment_day: 每月扣款日（1-28），不填则取放款日对应日。
        rate_mode: 利率模式，fixed=固定利率，lpr=LPR+基点浮动。
        fixed_rate: 固定年利率（%），rate_mode=fixed 时必填，如 4.2。
        lpr_type: LPR 期限品种，1y 或 5y（房贷一般用 5y），rate_mode=lpr 时使用。
        basis_points: 在 LPR 基础上加的基点，100bp=1%，可为负，如 LPR-30bp 传 -30。
        repricing_day: 重定价日，"MM-DD"（如 "01-01"）或 "anniversary"（放款日对应日）。

    Returns:
        还款计划：schedule_rows（逐期：期次/应还日/月供/本金/利息/年利率/剩余本金）、首期扣款日、总期数。
    """
    payload: dict[str, Any] = {
        "principal": principal,
        "start_date": start_date,
        "term_months": term_months,
        "repayment_method": repayment_method,
        "rate_mode": rate_mode,
        "lpr_type": lpr_type,
        "basis_points": basis_points,
        "repricing_day": repricing_day,
    }
    if payment_day is not None:
        payload["payment_day"] = payment_day
    if fixed_rate is not None:
        payload["fixed_rate"] = fixed_rate
    return client.post("/lpr/amortize", json=payload)  # type: ignore[no-any-return]


def mortgage_default_calculate(
    principal: Annotated[float, Field(description="贷款本金(元)", gt=0)],
    start_date: Annotated[str, Field(description="放款日期,YYYY-MM-DD")],
    term_months: Annotated[int, Field(description="贷款期限(月)", ge=1)],
    repayment_method: Annotated[_RepayL, Field(description="equal_installment 等额本息/equal_principal 等额本金")] = "equal_installment",
    rate_mode: Annotated[_RateModeL, Field(description="fixed 固定利率/lpr=LPR+基点浮动")] = "fixed",
    fixed_rate: Annotated[float | None, Field(description="固定年利率(%),rate_mode=fixed 时必填", gt=0)] = None,
    lpr_type: Annotated[_LprTypeL, Field(description="LPR 期限品种(房贷一般 5y)")] = "5y",
    basis_points: Annotated[float, Field(description="LPR 加点基点,可为负(如 -30)")] = 0.0,
    repricing_day: Annotated[str, Field(description='重定价日,"MM-DD" 或 "anniversary"')] = "01-01",
    payment_day: Annotated[int | None, Field(description="每月扣款日(1-31,29-31 小月自动钳到月末)", ge=1, le=31)] = None,
    penalty_mode: Annotated[_PenaltyModeL, Field(description="multiplier=执行利率×倍数/specified=合同直接约定罚息率")] = "multiplier",
    penalty_multiplier: Annotated[float, Field(description="罚息倍数(penalty_mode=multiplier 用,常见 1.5)")] = 1.5,
    penalty_rate: Annotated[float | None, Field(description="罚息年利率%(penalty_mode=specified 必填,如 6.15)")] = None,
    compound_on_interest: Annotated[bool, Field(description="对欠付利息计复利(默认是)")] = True,
    compound_on_penalty: Annotated[bool, Field(description="对罚息再计复利(默认否;合同约定对罚息计复利才开)")] = False,
    compound_method: Annotated[_CompoundMethodL, Field(description="daily 逐日分段(默认)/flat 不分段积数法")] = "daily",
    grace_period_days: Annotated[int, Field(description="宽限期天数(期内还款视为按时)", ge=0)] = 0,
    first_period_interest: Annotated[_FirstPeriodL, Field(description="prorate 按实际天数(默认)/full_month 整月")] = "prorate",
    charge_interest_on_payment_day: Annotated[bool, Field(description="逾期天数是否含还款日当日(默认否=算至前一日)")] = False,
    year_days: Annotated[int, Field(description="罚息/复利计息基准天数,360 或 365")] = 360,
    allocation_order: Annotated[list[str] | None, Field(description='还款冲抵顺序,可选值 penalty/interest/compound/principal,如 ["penalty","interest","compound","principal"]')] = None,
    allocation_stance: Annotated[_AllocationStanceL | None, Field(description="冲抵立场快捷预设(与 allocation_order 二选一,显式 order 优先):interest_first 先息后本/principal_first 先本后息")] = None,
    rate_events: Annotated[list[dict[str, Any]] | None, Field(description="利率变动事件列表(自定义重定价时间线)")] = None,
    lump_penalty_rate: Annotated[float | None, Field(description="一次性违约金率(%)")] = None,
    lump_penalty_amount: Annotated[float | None, Field(description="一次性违约金固定金额(元)")] = None,
    lump_penalty_threshold_days: Annotated[int, Field(description="一次性违约金触发所需逾期天数", ge=0)] = 0,
    shift_due_to_workday: Annotated[bool, Field(description="到期日顺延到工作日")] = False,
    holidays: Annotated[list[str] | None, Field(description="节假日列表(YYYY-MM-DD,配合 shift_due_to_workday)")] = None,
    prepayment_handling: Annotated[_PrepayHandlingL, Field(description="提前还款重排:shorten_term 缩短期限/reduce_payment 月供递减")] = "shorten_term",
    prepayment_compensation_rate: Annotated[float | None, Field(description="提前还款补偿金率(%,如 1.0=本金 1%)")] = None,
    fees_offset: Annotated[bool, Field(description="诉讼费用是否参与还款冲抵(默认否,仅计入诉请合计)")] = False,
    step_up_rate: Annotated[float | None, Field(description="逾期自动加码比例(%,如 50=上浮 50%;不传=不加码)")] = None,
    step_up_trigger_days: Annotated[int, Field(description="加码触发所需连续逾期天数(0=首批欠款即加码)", ge=0)] = 0,
    rounding_mode: Annotated[_RoundingL, Field(description="period 逐期四舍五入到分(默认)/cumulative 汇总一次性舍入")] = "period",
    interest_cutoff_date: Annotated[str | None, Field(description="合同利息止算日,YYYY-MM-DD(默认=claim_date)")] = None,
    cutoff_continues_penalty: Annotated[bool, Field(description="止算日后罚息是否继续算至截止日(默认否)")] = False,
    cutoff_continues_compound: Annotated[bool, Field(description="止算日后复利是否继续算至截止日(默认否)")] = False,
    other_fees: Annotated[list[dict[str, Any]] | None, Field(description='其他费用列表,每项 {"name": "律师费", "amount": 50000}')] = None,
    claim_mode: Annotated[_ClaimModeL, Field(description="违约金与罚息主张:both 并行叠加(默认)/either 择一从高")] = "both",
    accelerate_date: Annotated[str | None, Field(description="加速到期日(宣布全部本金提前到期,YYYY-MM-DD);不填或不早于截止日=不触发")] = None,
    accelerate_grace_days: Annotated[int, Field(description="加速到期宽限天数(期内还款视为按时)", ge=0)] = 0,
    cap_penalty_annual: Annotated[float | None, Field(description="罚息/复利年利率封顶(%);不传=不封顶")] = None,
    cap_total_mode: Annotated[_CapTotalModeL, Field(description="总债权封顶:none 不封顶(默认)/amount 固定金额/principal_ratio 本金倍数/interest_ratio 利息倍数")] = "none",
    cap_total_value: Annotated[float, Field(description="总债权封顶值:amount 模式为元,ratio 模式为倍数(如 1.5)")] = 0.0,
    interest_cut_inclusive: Annotated[bool, Field(description="计息边界含截止日当天(算头算尾;默认 False=算头不算尾)")] = False,
    pause_periods: Annotated[list[dict[str, Any]] | None, Field(description='停息区间列表,每项 {"start","end","note"}(end 含当日;停息挂账/展期场景)')] = None,
    payments: Annotated[list[dict[str, Any]] | None, Field(description='借款人还款流水,每项 {"payment_date","amount","payment_type"?,"note"?}')] = None,
    claim_date: Annotated[str | None, Field(description="计算截止日(起诉日),YYYY-MM-DD,默认今天")] = None,
) -> dict[str, Any]:
    """计算银行起诉断供借款人的逾期违约债权（诉讼请求金额）。

    输出剩余本金、未付利息、罚息、复利、其他费用及合计，以及逐期违约明细与每日
    新增利息，可直接引用进起诉状。银行口径差异（罚息 penalty_mode/penalty_rate、
    复利 compound_on_interest/compound_method、宽限期、首期计息、冲抵
    allocation_order、还款流水 payments、停息 pause_periods、加速到期、封顶
    cap_total_mode 等）逐项写在参数说明里，对照贷款合同填写。

    Returns:
        claim: 诉请金额汇总（剩余本金/未付利息/罚息/复利/其他费用/合计/每日新增）。
        default_rows: 逐期违约明细（欠本/欠息/逾期天数/罚息/复利/还款冲抵明细）。
        schedule_rows: 重排后的还款计划对照表。
        warnings: 口径提示，引用金额前务必阅读。
    """
    payload: dict[str, Any] = {
        "principal": principal,
        "start_date": start_date,
        "term_months": term_months,
        "repayment_method": repayment_method,
        "rate_mode": rate_mode,
        "lpr_type": lpr_type,
        "basis_points": basis_points,
        "repricing_day": repricing_day,
        "penalty_mode": penalty_mode,
        "penalty_multiplier": penalty_multiplier,
        "compound_on_interest": compound_on_interest,
        "compound_on_penalty": compound_on_penalty,
        "compound_method": compound_method,
        "grace_period_days": grace_period_days,
        "first_period_interest": first_period_interest,
        "charge_interest_on_payment_day": charge_interest_on_payment_day,
        "year_days": year_days,
        "prepayment_handling": prepayment_handling,
    }
    if payment_day is not None:
        payload["payment_day"] = payment_day
    if fixed_rate is not None:
        payload["fixed_rate"] = fixed_rate
    if penalty_rate is not None:
        payload["penalty_rate"] = penalty_rate
    if prepayment_compensation_rate is not None:
        payload["prepayment_compensation_rate"] = prepayment_compensation_rate
    if fees_offset:
        payload["fees_offset"] = fees_offset
    if step_up_rate is not None:
        payload["step_up_rate"] = step_up_rate
        payload["step_up_trigger_days"] = step_up_trigger_days
    if rounding_mode and rounding_mode != "period":
        payload["rounding_mode"] = rounding_mode
    if interest_cutoff_date:
        payload["interest_cutoff_date"] = interest_cutoff_date
        if cutoff_continues_penalty:
            payload["cutoff_continues_penalty"] = True
        if cutoff_continues_compound:
            payload["cutoff_continues_compound"] = True
    if other_fees:
        payload["other_fees"] = other_fees
    if allocation_order:
        payload["allocation_order"] = allocation_order
    if allocation_stance:
        payload["allocation_stance"] = allocation_stance
    if rate_events:
        payload["rate_events"] = rate_events
    if lump_penalty_rate is not None:
        payload["lump_penalty_rate"] = lump_penalty_rate
    if lump_penalty_amount is not None:
        payload["lump_penalty_amount"] = lump_penalty_amount
    if lump_penalty_threshold_days:
        payload["lump_penalty_threshold_days"] = lump_penalty_threshold_days
    if shift_due_to_workday:
        payload["shift_due_to_workday"] = shift_due_to_workday
    if holidays:
        payload["holidays"] = holidays
    if claim_mode and claim_mode != "both":
        payload["claim_mode"] = claim_mode
    if accelerate_date:
        payload["accelerate_date"] = accelerate_date
    if accelerate_grace_days:
        payload["accelerate_grace_days"] = accelerate_grace_days
    if cap_penalty_annual is not None:
        payload["cap_penalty_annual"] = cap_penalty_annual
    if cap_total_mode and cap_total_mode != "none":
        payload["cap_total_mode"] = cap_total_mode
        payload["cap_total_value"] = cap_total_value
    if interest_cut_inclusive:
        payload["interest_cut_inclusive"] = True
    if pause_periods:
        payload["pause_periods"] = pause_periods
    if payments:
        payload["payments"] = payments
    if claim_date:
        payload["claim_date"] = claim_date
    return client.post("/lpr/mortgage-default-calculate", json=payload)  # type: ignore[no-any-return]
