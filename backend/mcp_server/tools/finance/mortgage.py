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

from typing import Any

from mcp_server.client import client


def mortgage_amortize(
    principal: float,
    start_date: str,
    term_months: int,
    repayment_method: str = "equal_installment",
    payment_day: int | None = None,
    rate_mode: str = "fixed",
    fixed_rate: float | None = None,
    lpr_type: str = "5y",
    basis_points: float = 0.0,
    repricing_day: str = "01-01",
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
    principal: float,
    start_date: str,
    term_months: int,
    repayment_method: str = "equal_installment",
    rate_mode: str = "fixed",
    fixed_rate: float | None = None,
    lpr_type: str = "5y",
    basis_points: float = 0.0,
    repricing_day: str = "01-01",
    payment_day: int | None = None,
    penalty_mode: str = "multiplier",
    penalty_multiplier: float = 1.5,
    penalty_rate: float | None = None,
    compound_on_interest: bool = True,
    compound_on_penalty: bool = False,
    compound_method: str = "daily",
    grace_period_days: int = 0,
    first_period_interest: str = "prorate",
    charge_interest_on_payment_day: bool = False,
    year_days: int = 360,
    allocation_order: list[str] | None = None,
    prepayment_handling: str = "shorten_term",
    prepayment_compensation_rate: float | None = None,
    other_fees: list[dict[str, Any]] | None = None,
    payments: list[dict[str, Any]] | None = None,
    claim_date: str | None = None,
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
        other_fees: 其他费用列表，每项 {"name": "律师费", "amount": 50000}，仅计入诉讼请求合计。
        payments: 借款人实际还款流水列表，每项 {"payment_date": "YYYY-MM-DD", "amount": 金额,
            "payment_type": "normal"(正常还款，可省略) 或 "prepayment_principal"(提前冲减本金), "note": 备注(可省略)}。
        claim_date: 计算截止日（起诉日），格式 YYYY-MM-DD，默认今天。

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
    if other_fees:
        payload["other_fees"] = other_fees
    if allocation_order:
        payload["allocation_order"] = allocation_order
    if payments:
        payload["payments"] = payments
    if claim_date:
        payload["claim_date"] = claim_date
    return client.post("/lpr/mortgage-default-calculate", json=payload)  # type: ignore[no-any-return]
