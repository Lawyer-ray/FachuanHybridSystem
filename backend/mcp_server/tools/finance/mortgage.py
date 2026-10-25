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

    输出诉讼请求金额：剩余本金、未付利息、罚息、复利、其他费用及合计，
    以及逐期违约明细（含每笔还款的冲抵明细）和每日新增利息，可直接引用进起诉状。

    银行口径差异参数（对照贷款合同填写）：
    - 罚息利率：multiplier=执行利率×倍数（常见上浮50%，如交行 23.5 条）；specified=合同直接约定
    - 复利：compound_on_interest 对欠付利息计复利；compound_on_penalty 对罚息再计复利
      （如交行 13.1 条对"应付未付利息（包括罚息）"计收复利，两者都开）
    - compound_method: flat=复利不分段，积数×收取时罚息利率（交行 13.1 条口径）；
      daily=逐日按当日罚息利率分段（多数银行）
    - grace_period_days: 宽限期（如合同 25.4 条），宽限期内还款视为按时
    - first_period_interest: prorate=首期按放款日→首期扣款日实际天数计息（含零头天数，
      如交行 3.1(3) 条），full_month=整月
    - charge_interest_on_payment_day: 逾期天数是否含还款日当日
      （交行 13.2 条约定算至实际还款日前一日，传 false）
    - prepayment_compensation_rate: 提前还款补偿金率（如交行 25.5 条为 1%）

    Args:
        principal: 贷款本金（元）。
        start_date: 放款日期，格式 YYYY-MM-DD。
        term_months: 贷款期限（月）。
        repayment_method: 还款方式，equal_installment=等额本息，equal_principal=等额本金。
        rate_mode: 利率模式，fixed=固定利率，lpr=LPR+基点浮动。
        fixed_rate: 固定年利率（%），rate_mode=fixed 时必填。
        lpr_type: LPR 期限品种，1y 或 5y（房贷一般用 5y）。
        basis_points: LPR 加点基点，100bp=1%，可为负。
        repricing_day: 重定价日，"MM-DD" 或 "anniversary"（放款日对应日）。
        payment_day: 每月扣款日（1-31），不填则取放款日对应日；29-31 在小月自动钳制到月末。
        penalty_mode: 罚息利率模式，multiplier=执行利率×倍数，specified=合同直接约定罚息利率。
        penalty_multiplier: 罚息倍数（penalty_mode=multiplier 时使用，常见 1.5）。
        penalty_rate: 罚息年利率%（penalty_mode=specified 时必填，如 6.15）。
        compound_on_interest: 是否对欠付利息计收复利，默认是。
        compound_on_penalty: 是否对罚息再计收复利，默认否（如交行约定对罚息计复利则传 true）。
        compound_method: 复利计算方式，daily=逐日分段（默认），flat=不分段积数法。
        grace_period_days: 宽限期天数，默认 0。
        first_period_interest: 首期计息方式，prorate=按实际天数（默认），full_month=整月。
        charge_interest_on_payment_day: 逾期天数是否含还款日当日，默认否（算至还款日前一日）。
        year_days: 罚息/复利计息基准天数，360 或 365，默认 360。
        allocation_order: 还款冲抵顺序，可选值 penalty/interest/compound/principal。
            默认 ["penalty", "interest", "compound", "principal"]，不同银行约定不同可自定义。
        prepayment_handling: 提前还款重排方式，shorten_term=缩短期限月供不变，reduce_payment=月供递减期限不变。
        prepayment_compensation_rate: 提前还款补偿金率(%)，如 1.0 表示提前归还本金的 1%，不传表示无。
        fees_offset: 是否让诉讼费用参与还款冲抵（追加 fee 到冲抵顺序末尾按序核销），默认否（费用仅计入诉讼请求合计）。
        step_up_rate: 逾期自动加码比例(%)，如 50 表示逾期触发后罚息/复利上浮 50%；不传=不加码。
        step_up_trigger_days: 加码触发所需连续逾期天数，0=首个欠款批次起即加码。
        rounding_mode: 舍入规则，period=逐期四舍五入到分再求和（默认），cumulative=汇总一次性舍入。
        interest_cutoff_date: 利息止算日（YYYY-MM-DD，可选）。合同利息计算至此日；
            默认=claim_date。止算日后罚息/复利是否继续由 cutoff_continues_penalty/compound 决定。
        cutoff_continues_penalty: 止算日后罚息是否继续计算至计算截止日（默认否，即罚息止算）。
        cutoff_continues_compound: 止算日后复利是否继续计算至计算截止日（默认否，即复利止算）。
        other_fees: 其他费用列表，每项 {"name": "律师费", "amount": 50000}，仅计入诉讼请求合计。
        payments: 借款人实际还款流水列表，每项 {"payment_date": "YYYY-MM-DD", "amount": 金额,
            "payment_type": "normal"(正常还款，可省略) 或 "prepayment_principal"(提前冲减本金), "note": 备注(可省略)}。
        claim_date: 计算截止日（起诉日），格式 YYYY-MM-DD，默认今天。
        claim_mode: 违约金与罚息主张口径，both=并行叠加（默认），either=择一从高（取较大者计入诉请，避免重复主张）。
        accelerate_date: 加速到期日（银行宣布全部本金提前到期之日，YYYY-MM-DD）。自该日起全部剩余本金转已到期本金，
            罚息/复利对全额计收并停止按月摊销；不填或不早于截止日=不触发。
        accelerate_grace_days: 加速到期宽限天数（加速日后该天数内还款视为按时，罚息自宽限期届满次日起算），默认 0。
        cap_penalty_annual: 罚息/复利年利率封顶(%)，实际罚息利率超过该上限时按封顶值计息；不传=不封顶。
        cap_total_mode: 总债权（违约金+罚息+复利）封顶模式，none=不封顶（默认）、amount=固定金额、
            principal_ratio=未还本金倍数、interest_ratio=未付利息倍数。
        cap_total_value: 总债权封顶值：amount 模式为固定金额（元），ratio 模式为倍数（如 1.5）。
        interest_cut_inclusive: 计息起止边界：True=含截止日当天（算头算尾，末日各 +1 天），默认 False=算头不算尾。
        pause_periods: 停息区间列表，每项 {"start": "YYYY-MM-DD", "end": "YYYY-MM-DD", "note": 备注}（end 含当日）；
            区间内罚息/复利及按天截算的合同利息暂停计息，还款流水照常核销（停息挂账/展期场景）。

    Returns:
        claim: 诉讼请求金额汇总（outstanding_principal 剩余本金 / unpaid_interest 未付利息 /
            penalty_interest 罚息 / compound_interest 复利 / other_fees 其他费用 /
            total_claim 合计 / daily_accrual 此后每日新增）。
        default_rows: 逐期违约明细（欠本/欠息/逾期天数/罚息/复利/每笔还款冲抵明细）。
        schedule_rows: 重排后的还款计划对照表。
        warnings: 口径提示（复利口径、宽限期、重排次数等），引用金额前务必阅读。
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
