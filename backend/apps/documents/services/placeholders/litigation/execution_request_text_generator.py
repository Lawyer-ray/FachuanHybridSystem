"""强制执行申请书 - 文本生成."""

from __future__ import annotations

from datetime import date
from decimal import Decimal

from .execution_request_models import InterestSegment, ParsedAmounts, ParsedInterestParams
from .execution_request_utils import format_amount


def generate_request_text(
    *,
    full_case_number: str,
    amounts: ParsedAmounts,
    params: ParsedInterestParams,
    overdue_interest: Decimal,
    interest_base: Decimal,
    cutoff_date: date,
    total: Decimal,
    has_double_interest_clause: bool,
    interest_segments: list[InterestSegment] | None = None,
    custom_interest_summary: str = "",
    joint_liability_text: str = "",
    supplementary_liability_text: str = "",
    priority_execution_texts: list[str] | None = None,
    manual_review_clauses: list[str] | None = None,
    original_segmented_interest_expression: str = "",
) -> str:
    segments = interest_segments or []
    priority_texts = priority_execution_texts or []
    review_clauses = manual_review_clauses or []
    principal = amounts.principal or Decimal("0")
    overdue_label = params.overdue_item_label or "利息"
    fee_desc = build_fee_desc(amounts)
    fee_as_primary_item = False

    if principal > 0:
        item_segments = [
            f"申请强制执行{full_case_number}，被申请人向申请人支付{amounts.principal_label}{format_amount(principal)}元"
        ]
    elif fee_desc:
        item_segments = [f"申请强制执行{full_case_number}，被申请人向申请人支付{fee_desc}"]
        fee_as_primary_item = True
    else:
        item_segments = [f"申请强制执行{full_case_number}，被申请人向申请人支付款项"]

    if amounts.confirmed_interest > 0:
        item_segments.append(f"利息{format_amount(amounts.confirmed_interest)}元")

    if custom_interest_summary:
        item_segments.append(custom_interest_summary)
    elif (segments or params.start_date) and (
        params.multiplier is not None or params.custom_rate_value is not None
    ):
        cutoff_text = f"{cutoff_date.year}年{cutoff_date.month}月{cutoff_date.day}日"
        rate_desc = params.rate_description or "约定利率"
        if len(segments) >= 2:
            original_segmented_text = (original_segmented_interest_expression or "").strip().rstrip("。；")
            if original_segmented_text:
                item_segments.append(
                    f"{original_segmented_text}，暂计至{cutoff_text}{overdue_label}为{format_amount(overdue_interest)}元"
                )
            else:
                segment_desc = build_interest_segment_desc(segments)
                item_segments.append(
                    f"{overdue_label}按分段基数计算（{segment_desc}），按{rate_desc}计至实际清偿之日，截至{cutoff_text}{overdue_label}为{format_amount(overdue_interest)}元"
                )
        else:
            start_date_text = f"{params.start_date.year}年{params.start_date.month}月{params.start_date.day}日"  # type: ignore[union-attr]
            item_segments.append(
                f"{overdue_label}自{start_date_text}起以{format_amount(interest_base)}元为基数，按{rate_desc}计算至实际清偿之日，截至{cutoff_text}{overdue_label}为{format_amount(overdue_interest)}元"
            )

    if fee_desc and not fee_as_primary_item:
        item_segments.append(fee_desc)

    first_item = "，".join(item_segments) + "。"
    lines = [first_item, f"以上合计：{format_amount(total)}元。"]

    if has_double_interest_clause:
        lines.append("被申请人加倍支付迟延履行期间的债务利息。")
    if joint_liability_text:
        line = joint_liability_text.rstrip("。；")
        if line:
            lines.append(f"{line}。")
    if supplementary_liability_text:
        line = supplementary_liability_text.rstrip("。；")
        if line:
            lines.append(f"{line}。")
    for text in priority_texts:
        line = str(text or "").strip().rstrip("。；")
        if line:
            lines.append(f"{line}。")
    for text in review_clauses:
        line = str(text or "").strip().rstrip("。；")
        if line:
            lines.append(f"【人工核对】{line}。")
    lines.append("由被申请人承担本案执行费用。")

    return "\n".join(lines)


def build_fee_desc(amounts: ParsedAmounts) -> str:
    parts: list[str] = []
    if amounts.litigation_fee > 0:
        parts.append(f"受理费{format_amount(amounts.litigation_fee)}元")
    if amounts.preservation_fee > 0:
        parts.append(f"财产保全费{format_amount(amounts.preservation_fee)}元")
    if amounts.announcement_fee > 0:
        parts.append(f"公告费{format_amount(amounts.announcement_fee)}元")
    if amounts.attorney_fee > 0:
        parts.append(f"律师代理费{format_amount(amounts.attorney_fee)}元")
    if amounts.guarantee_fee > 0:
        parts.append(f"财产保全担保费{format_amount(amounts.guarantee_fee)}元")
    return "、".join(parts)


def build_interest_segment_desc(segments: list[InterestSegment]) -> str:
    desc_parts: list[str] = []
    ordered_segments = sorted(segments, key=lambda s: (s.start_date, s.end_date or date.max))
    for segment in ordered_segments:
        start_text = f"{segment.start_date.year}年{segment.start_date.month}月{segment.start_date.day}日"
        if segment.end_date:
            end_text = f"{segment.end_date.year}年{segment.end_date.month}月{segment.end_date.day}日止"
        else:
            end_text = "实际清偿之日止"
        desc_parts.append(f"以{format_amount(segment.base_amount)}元为基数，自{start_text}起至{end_text}")
    return "；".join(desc_parts)
