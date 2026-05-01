"""强制执行申请书 - 利息参数解析与计算."""

from __future__ import annotations

import logging
import re
from datetime import date
from decimal import Decimal

from apps.cases.models import Case
from apps.finance.services.calculator.interest_calculator import InterestCalculator

from .execution_request_models import InterestSegment, ParsedAmounts, ParsedInterestParams
from .execution_request_utils import (
    AMOUNT_WITH_UNIT_PATTERN,
    build_date,
    format_amount,
    parse_amount_value,
    parse_decimal,
    parse_multiplier_value,
    safe_decimal,
)

logger = logging.getLogger(__name__)


def parse_interest_params(main_text: str) -> ParsedInterestParams:
    params = ParsedInterestParams()
    clause = extract_interest_clause(main_text)
    params.overdue_item_label = detect_overdue_item_label(main_text)

    lpr_pattern = re.compile(
        r"(?:LPR|贷款市场报价利率|一年期贷款市场报价利率)[^。；\n]{0,24}?([0-9]+(?:\.[0-9]+)?|[零一二两三四五六七八九十]+)\s*倍"
    )
    lpr_markup_pattern = re.compile(
        r"(?:LPR|贷款市场报价利率|一年期贷款市场报价利率)[^。；\n]{0,24}?上浮\s*([0-9]+(?:\.[0-9]+)?)\s*%"
    )
    fixed_pattern = re.compile(r"(?:(?:按|起按|按照)\s*)?(年利率|年化率|年化利率)\s*([0-9]+(?:\.[0-9]+)?)\s*%")
    unit_rate_pattern = r"([0-9]+(?:\.[0-9]+)?|[零一二两三四五六七八九十]+)"
    daily_permille_pattern = re.compile(rf"(?:日利率|每日)\s*千分之\s*{unit_rate_pattern}")
    daily_permyriad_pattern = re.compile(rf"(?:日利率|每日)\s*万分之\s*{unit_rate_pattern}")
    daily_percent_pattern = re.compile(r"(?:日利率|每日)\s*([0-9]+(?:\.[0-9]+)?)\s*%")

    rate_text = clause or main_text
    lpr_match = lpr_pattern.search(rate_text)
    lpr_markup_match = lpr_markup_pattern.search(rate_text)
    fixed_match = fixed_pattern.search(rate_text)
    permille_match = daily_permille_pattern.search(rate_text)
    permyriad_match = daily_permyriad_pattern.search(rate_text)
    daily_percent_match = daily_percent_pattern.search(rate_text)

    if lpr_match:
        multiplier = parse_multiplier_value(lpr_match.group(1))
        if multiplier is not None:
            params.multiplier = multiplier
            params.rate_type = "1y"
            params.rate_description = (
                f"全国银行间同业拆借中心公布的一年期贷款市场报价利率的{format_amount(multiplier)}倍"
            )
    elif lpr_markup_match:
        markup_percent = parse_decimal(lpr_markup_match.group(1))
        if markup_percent is not None:
            multiplier = Decimal("1") + (markup_percent / Decimal("100"))
            params.multiplier = multiplier
            params.rate_type = "1y"
            params.rate_description = (
                f"全国银行间同业拆借中心公布的一年期贷款市场报价利率的{format_amount(multiplier)}倍"
            )
    elif re.search(r"(?:LPR|贷款市场报价利率|一年期贷款市场报价利率)", rate_text):
        params.multiplier = Decimal("1")
        params.rate_type = "1y"
        params.rate_description = "全国银行间同业拆借中心公布的一年期贷款市场报价利率"
    elif fixed_match:
        annual_rate = parse_decimal(fixed_match.group(2))
        if annual_rate is not None:
            params.custom_rate_unit = "percent"
            params.custom_rate_value = annual_rate
            params.rate_description = f"{fixed_match.group(1)}{format_amount(annual_rate)}%"
    elif permille_match:
        unit_rate = parse_multiplier_value(permille_match.group(1))
        if unit_rate is not None:
            params.custom_rate_unit = "permille"
            params.custom_rate_value = unit_rate
            params.rate_description = f"日利率千分之{format_amount(unit_rate)}"
    elif permyriad_match:
        unit_rate = parse_multiplier_value(permyriad_match.group(1))
        if unit_rate is not None:
            params.custom_rate_unit = "permyriad"
            params.custom_rate_value = unit_rate
            params.rate_description = f"日利率万分之{format_amount(unit_rate)}"
    elif daily_percent_match:
        # 日利率 x% => 转换为万分之(x * 100)
        percent_rate = parse_decimal(daily_percent_match.group(1))
        if percent_rate is not None:
            params.custom_rate_unit = "permyriad"
            params.custom_rate_value = (percent_rate * Decimal("100")).quantize(Decimal("0.0001"))
            percent_text = format(percent_rate.normalize(), "f")
            params.rate_description = f"日利率{percent_text}%"

    date_match = re.search(r"(?:自|从)\s*(\d{4})\s*年\s*(\d{1,2})\s*月\s*(\d{1,2})\s*日(?:起|开始|计)?", rate_text)
    if date_match:
        params.start_date = build_date(date_match.group(1), date_match.group(2), date_match.group(3))

    cap_patterns = [
        re.compile(rf"以\s*不超过\s*{AMOUNT_WITH_UNIT_PATTERN}\s*元\s*为限"),
        re.compile(rf"利息总额[^。；\n]{{0,40}}?不超过\s*{AMOUNT_WITH_UNIT_PATTERN}\s*元"),
    ]
    for cap_pattern in cap_patterns:
        cap_match = cap_pattern.search(main_text)
        if cap_match:
            cap_amount = parse_decimal(cap_match.group(1))
            if cap_amount is not None:
                params.interest_cap = cap_amount
                break

    params.base_mode, params.base_amount = parse_interest_base_rule(rate_text=rate_text, full_text=main_text)
    return params


def detect_overdue_item_label(main_text: str) -> str:
    compact = (main_text or "").replace(" ", "")
    if "逾期付款违约金" in compact:
        return "逾期付款违约金"
    if "违约金" in compact and any(
        marker in compact
        for marker in (
            "计算方法",
            "计算至",
            "计至",
            "清偿之日",
            "付清之日",
            "履行之日",
            "万分之",
            "千分之",
            "年利率",
            "日利率",
            "LPR",
            "利率",
        )
    ):
        return "违约金"
    if "逾期付款损失" in compact:
        return "逾期付款损失"
    if "逾期付款利息" in compact:
        return "逾期付款利息"
    if "逾期利息" in compact:
        return "逾期利息"
    return "利息"


def infer_principal_from_interest_base(params: ParsedInterestParams) -> Decimal | None:
    if params.base_mode in {"fixed_amount", "fixed_amount_remaining"} and params.base_amount is not None:
        if params.base_amount > 0:
            return params.base_amount
    return None


def parse_interest_base_rule(*, rate_text: str, full_text: str) -> tuple[str, Decimal | None]:
    base_match = re.search(r"以\s*([^，,；。\n]{1,60}?)\s*为(?:本金|基数)", rate_text)
    if base_match:
        base_text = base_match.group(1)
        amount_match = re.search(AMOUNT_WITH_UNIT_PATTERN, base_text)
        if amount_match:
            amount_value = parse_amount_value(amount_match.group(1), amount_match.group(2))
            if amount_value is not None:
                if any(k in base_text for k in ("剩余", "未付", "未偿还")):
                    return "fixed_amount_remaining", amount_value
                return "fixed_amount", amount_value
        if any(k in base_text for k in ("借款", "货款", "本金")):
            return "remaining_principal", None
        if any(k in base_text for k in ("未付款项", "未支付", "上述款项", "剩余款项")):
            return "remaining_total", None

    compact_text = full_text.replace(" ", "")
    if any(
        k in compact_text for k in ("未偿还的借款为基数", "未偿还借款为基数", "剩余借款为基数", "未偿还货款为基数")
    ):
        return "remaining_principal", None
    if any(
        k in compact_text
        for k in ("剩余未付款项为基数", "未支付的上述款项为基数", "未付款项为基数", "上述款项为基数")
    ):
        return "remaining_total", None
    return "fallback_target", None


def resolve_interest_base(
    *,
    case: Case,
    amounts: ParsedAmounts,
    params: ParsedInterestParams,
    principal_paid: Decimal,
) -> Decimal:
    principal = amounts.principal or Decimal("0")
    target_amount = safe_decimal(case.target_amount)

    if params.base_mode in {"fixed_amount", "fixed_amount_remaining"} and params.base_amount is not None:
        base = max(params.base_amount - principal_paid, Decimal("0"))
    elif params.base_mode == "remaining_principal":
        base = principal
    elif params.base_mode == "remaining_total":
        base = principal + amounts.confirmed_interest
    else:
        base = target_amount if target_amount > 0 else (principal + amounts.confirmed_interest)

    if base <= 0:
        if target_amount > 0:
            return target_amount
        return max(principal, Decimal("0"))
    return base


def parse_deduction_order(main_text: str) -> list[str]:
    patterns = [
        re.compile(r"按\s*([^。；\n]{2,120}?)\s*顺序(?:优先)?(?:进行)?抵扣"),
        re.compile(r"按\s*([^。；\n]{2,120}?)\s*抵扣顺序"),
        re.compile(r"按顺序(?:优先)?(?:进行)?抵扣\s*([^。；\n]{2,120})"),
    ]
    for pattern in patterns:
        match = pattern.search(main_text)
        if not match:
            continue
        segment = match.group(1)
        tokens = [t.strip() for t in re.split(r"[、，,]", segment) if t.strip()]
        mapped: list[str] = []
        for token in tokens:
            key = _map_deduction_token(token)
            if key and key not in mapped:
                mapped.append(key)
        if mapped:
            return mapped
    return []


def _map_deduction_token(token: str) -> str | None:
    if "受理费" in token:
        return "litigation_fee"
    if "保全" in token and "担保" not in token:
        return "preservation_fee"
    if "公告费" in token:
        return "announcement_fee"
    if "律师" in token:
        return "attorney_fee"
    if "担保" in token:
        return "guarantee_fee"
    if "利息" in token or "逾期付款利息" in token or "逾期利息" in token:
        return "interest"
    if any(k in token for k in ("借款", "货款", "本金", "未付款", "剩余未付款")):
        return "principal"
    return None


DEDUCTION_KEY_TO_COMPONENT: dict[str, str] = {
    "litigation_fee": "litigation_fee",
    "preservation_fee": "preservation_fee",
    "announcement_fee": "announcement_fee",
    "attorney_fee": "attorney_fee",
    "guarantee_fee": "guarantee_fee",
    "interest": "confirmed_interest",
    "principal": "principal",
}

DEDUCTION_KEY_TO_LABEL: dict[str, str] = {
    "litigation_fee": "受理费",
    "preservation_fee": "财产保全费",
    "announcement_fee": "公告费",
    "attorney_fee": "律师代理费",
    "guarantee_fee": "财产保全担保费",
    "interest": "利息",
    "principal": "本金",
}


def apply_paid_amount(
    *,
    amounts: ParsedAmounts,
    paid_amount: Decimal,
    deduction_order: list[str],
) -> tuple[ParsedAmounts, Decimal, list[dict[str, str | Decimal]]]:
    principal = amounts.principal or Decimal("0")
    components: dict[str, Decimal] = {
        "principal": principal,
        "confirmed_interest": amounts.confirmed_interest,
        "litigation_fee": amounts.litigation_fee,
        "preservation_fee": amounts.preservation_fee,
        "announcement_fee": amounts.announcement_fee,
        "attorney_fee": amounts.attorney_fee,
        "guarantee_fee": amounts.guarantee_fee,
    }
    remain_paid = max(paid_amount, Decimal("0"))
    applied: list[dict[str, object]] = []

    if deduction_order:
        for key in deduction_order:
            component_name = DEDUCTION_KEY_TO_COMPONENT.get(key)
            if not component_name:
                continue
            available = components.get(component_name, Decimal("0"))
            if available <= 0 or remain_paid <= 0:
                continue
            current_deduct = min(available, remain_paid)
            components[component_name] = available - current_deduct
            remain_paid -= current_deduct
            applied.append({"key": key, "amount": current_deduct})

    if remain_paid > 0 and components["principal"] > 0:
        extra_deduct = min(components["principal"], remain_paid)
        components["principal"] -= extra_deduct
        remain_paid -= extra_deduct
        applied.append({"key": "principal", "amount": extra_deduct})

    principal_paid = principal - components["principal"]

    amounts.principal = components["principal"]
    amounts.confirmed_interest = components["confirmed_interest"]
    amounts.litigation_fee = components["litigation_fee"]
    amounts.preservation_fee = components["preservation_fee"]
    amounts.announcement_fee = components["announcement_fee"]
    amounts.attorney_fee = components["attorney_fee"]
    amounts.guarantee_fee = components["guarantee_fee"]
    return amounts, principal_paid, applied


def calculate_interest(
    *,
    calculator: InterestCalculator,
    principal: Decimal,
    params: ParsedInterestParams,
    cutoff_date: date,
    year_days: int,
    date_inclusion: str,
    warnings: list[str],
) -> Decimal:
    if principal <= 0:
        return Decimal("0")
    if params.start_date is None:
        return Decimal("0")
    if params.multiplier is None and params.custom_rate_value is None:
        return Decimal("0")
    if cutoff_date < params.start_date:
        warnings.append("截止日早于利息起算日，逾期利息按 0 计算。")
        return Decimal("0")

    try:
        if params.custom_rate_value is not None:
            result = calculator.calculate(
                start_date=params.start_date,
                end_date=cutoff_date,
                principal=principal,
                custom_rate_unit=params.custom_rate_unit,
                custom_rate_value=params.custom_rate_value,
                year_days=year_days,
                date_inclusion=date_inclusion,
            )
        else:
            result = calculator.calculate(
                start_date=params.start_date,
                end_date=cutoff_date,
                principal=principal,
                rate_type=params.rate_type,
                multiplier=params.multiplier or Decimal("1"),
                year_days=year_days,
                date_inclusion=date_inclusion,
            )
    except Exception as exc:
        logger.error("利息计算失败: %s", exc, exc_info=True)
        warnings.append("利息计算失败，已按 0 处理。")
        return Decimal("0")

    interest = result.total_interest
    if params.interest_cap is not None and interest > params.interest_cap:
        warnings.append(f"利息触发上限，已按 {format_amount(params.interest_cap)} 元截断。")
        interest = params.interest_cap
    return interest


def calculate_interest_with_segments(
    *,
    calculator: InterestCalculator,
    segments: list[InterestSegment],
    params: ParsedInterestParams,
    cutoff_date: date,
    year_days: int,
    date_inclusion: str,
    warnings: list[str],
) -> Decimal:
    if not segments:
        return Decimal("0")
    if params.multiplier is None and params.custom_rate_value is None:
        return Decimal("0")

    from apps.finance.services.lpr.rate_service import PrincipalPeriod

    principal_periods: list[PrincipalPeriod] = []
    for segment in sorted(segments, key=lambda s: (s.start_date, s.end_date or date.max)):
        seg_end = segment.end_date or cutoff_date
        if seg_end > cutoff_date:
            seg_end = cutoff_date
        if seg_end < segment.start_date:
            continue
        principal_periods.append(
            PrincipalPeriod(
                start_date=segment.start_date,
                end_date=seg_end,
                principal=segment.base_amount,
            )
        )

    if not principal_periods:
        return Decimal("0")

    try:
        result = calculator.calculate_with_principal_changes(
            principal_periods=principal_periods,
            rate_type=params.rate_type,
            year_days=year_days,
            multiplier=params.multiplier or Decimal("1"),
            date_inclusion=date_inclusion,
            custom_rate_unit=params.custom_rate_unit,
            custom_rate_value=params.custom_rate_value,
        )
    except Exception as exc:
        logger.error("分段利息计算失败: %s", exc, exc_info=True)
        warnings.append("分段利息计算失败，已按 0 处理。")
        return Decimal("0")

    interest = result.total_interest
    if params.interest_cap is not None and interest > params.interest_cap:
        warnings.append(f"利息触发上限，已按 {format_amount(params.interest_cap)} 元截断。")
        interest = params.interest_cap
    return interest


def extract_interest_clause(main_text: str) -> str:
    patterns = [
        re.compile(r"(?:LPR|贷款市场报价利率|一年期贷款市场报价利率)[^。；\n]{0,120}"),
        re.compile(r"年利率[^。；\n]{0,120}"),
        re.compile(r"日利率[^。；\n]{0,120}"),
    ]
    for pattern in patterns:
        match = pattern.search(main_text)
        if match:
            from .execution_request_utils import extract_sentence

            return extract_sentence(main_text, match.start(), match.end())
    return main_text
