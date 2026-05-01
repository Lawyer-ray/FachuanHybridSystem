"""强制执行申请书 - 金额解析."""

from __future__ import annotations

import re
from decimal import ROUND_HALF_UP, Decimal

from .execution_request_models import FeeItem, ParsedAmounts
from .execution_request_utils import AMOUNT_WITH_UNIT_PATTERN, extract_sentence, parse_amount_value, parse_decimal


def parse_confirmed_amounts(main_text: str) -> ParsedAmounts:
    amounts = ParsedAmounts()

    principal_patterns = [
        re.compile(
            rf"(?:偿还|支付|归还|清偿|尚欠(?:原告|申请人)?|尚欠)\s*((?:借款|货款)(?:本金)?)\s*{AMOUNT_WITH_UNIT_PATTERN}"
        ),
        re.compile(rf"((?:借款|货款)本金)\s*{AMOUNT_WITH_UNIT_PATTERN}"),
        re.compile(
            rf"(?:偿还|支付|给付|返还|清偿|尚欠(?:原告|申请人)?|尚欠)\s*"
            rf"(广告费|广告发布费|服务费|技术服务费|工程款|佣金|居间费|租金|货物款|材料款|采购款|合同款|设备款|推广费|管理费|设计费|咨询费|回购价款|回购基本价款)"
            rf"\s*{AMOUNT_WITH_UNIT_PATTERN}"
        ),
    ]
    principal_matches: list[tuple[int, int, Decimal, str]] = []
    for pattern in principal_patterns:
        for match in pattern.finditer(main_text):
            start, end = match.span()
            if any(not (end <= s or start >= e) for s, e, _, _ in principal_matches):
                continue
            suffix = main_text[end : end + 12]
            # "以…为基数/为本金"属于计息基数，不应重复记入待执行本金
            if "为基数" in suffix or "为本金" in suffix:
                continue
            kind = match.group(1)
            amount_value = parse_amount_value(match.group(2), match.group(3))
            if amount_value is None:
                continue
            principal_matches.append((start, end, amount_value, kind))

    if principal_matches:
        amounts.principal = sum((item[2] for item in principal_matches), Decimal("0"))
        kinds = {item[3] for item in principal_matches}
        if len(kinds) == 1:
            amounts.principal_label = next(iter(kinds))
        else:
            amounts.principal_label = "款项本金"

    confirmed_interest = Decimal("0")
    confirmed_interest_pattern = re.compile(rf"(利息|罚息|复利)\s*(?:为|计为|计)?\s*{AMOUNT_WITH_UNIT_PATTERN}")
    for interest_match in confirmed_interest_pattern.finditer(main_text):
        label = interest_match.group(1)
        prefix = main_text[max(0, interest_match.start() - 6) : interest_match.start()]
        suffix = main_text[interest_match.end() : interest_match.end() + 10]
        if "为基数" in suffix:
            continue
        if "欠付" in prefix and label == "利息":
            continue
        if "逾期" in prefix and label == "利息":
            continue
        amount_value = parse_amount_value(interest_match.group(2), interest_match.group(3))
        if amount_value is not None:
            confirmed_interest += amount_value
    amounts.confirmed_interest = confirmed_interest

    fee_items = parse_fee_items(main_text)
    for fee in fee_items:
        if not fee.include:
            amounts.excluded_fees.append(fee)
            continue
        if fee.key == "litigation_fee":
            amounts.litigation_fee += fee.amount
        elif fee.key == "preservation_fee":
            amounts.preservation_fee += fee.amount
        elif fee.key == "announcement_fee":
            amounts.announcement_fee += fee.amount
        elif fee.key == "attorney_fee":
            amounts.attorney_fee += fee.amount
        elif fee.key == "guarantee_fee":
            amounts.guarantee_fee += fee.amount

    return amounts


def parse_fee_items(main_text: str) -> list[FeeItem]:
    patterns: list[tuple[str, str, re.Pattern[str]]] = [
        (
            "litigation_fee",
            "受理费",
            re.compile(rf"受理费(?:减半收取)?(?:\s*(?:为|计))?\s*{AMOUNT_WITH_UNIT_PATTERN}"),
        ),
        (
            "preservation_fee",
            "财产保全费",
            re.compile(rf"(?:诉前)?(?:财产保全申请费|保全申请费|财产保全费|保全费)\s*{AMOUNT_WITH_UNIT_PATTERN}"),
        ),
        ("announcement_fee", "公告费", re.compile(rf"公告费\s*{AMOUNT_WITH_UNIT_PATTERN}")),
        ("attorney_fee", "律师代理费", re.compile(rf"(?:律师代理费|律师费)\s*{AMOUNT_WITH_UNIT_PATTERN}")),
        ("guarantee_fee", "财产保全担保费", re.compile(rf"(?:财产保全)?担保费\s*{AMOUNT_WITH_UNIT_PATTERN}")),
    ]
    fee_items: list[FeeItem] = []

    for key, label, pattern in patterns:
        for match in pattern.finditer(main_text):
            amount_value = parse_amount_value(match.group(1), match.group(2))
            if amount_value is None:
                continue
            sentence = extract_sentence(main_text, match.start(), match.end())
            include, reason = should_include_fee(sentence=sentence, key=key)
            fee_items.append(
                FeeItem(
                    key=key,
                    label=label,
                    amount=amount_value,
                    include=include,
                    reason=reason,
                    sentence=sentence,
                )
            )

    apply_split_burden_adjustment(fee_items)
    return fee_items


def apply_split_burden_adjustment(fee_items: list[FeeItem]) -> None:
    """处理"原告负担X + 被告负担Y并迳付原告"的费用分摊句式。"""
    sentence_groups: dict[str, list[int]] = {}
    for idx, item in enumerate(fee_items):
        if not item.include:
            continue
        sentence = (item.sentence or "").strip()
        if not sentence:
            continue
        sentence_groups.setdefault(sentence, []).append(idx)

    for sentence, indices in sentence_groups.items():
        if "迳付" not in sentence and "支付给原告" not in sentence and "支付给申请人" not in sentence:
            continue

        defendant_burden = extract_party_burden_amount(sentence, parties=("被告", "被申请人"))
        if defendant_burden is None or defendant_burden <= 0:
            continue

        key_totals: dict[str, Decimal] = {}
        for idx in indices:
            key = fee_items[idx].key
            key_totals[key] = key_totals.get(key, Decimal("0")) + fee_items[idx].amount
        original_total = sum(key_totals.values(), Decimal("0"))
        if original_total <= 0 or defendant_burden >= original_total:
            continue

        plaintiff_burden = extract_party_burden_amount(sentence, parties=("原告", "申请人"))
        if plaintiff_burden is None or plaintiff_burden <= 0:
            continue

        if len(indices) == 1:
            fee_items[indices[0]].amount = defendant_burden
            continue

        adjusted = dict(key_totals)
        remaining_plaintiff = plaintiff_burden
        for key in ("litigation_fee", "preservation_fee", "announcement_fee"):
            if remaining_plaintiff <= 0:
                break
            available = adjusted.get(key, Decimal("0"))
            if available <= 0:
                continue
            deduct = min(available, remaining_plaintiff)
            adjusted[key] = available - deduct
            remaining_plaintiff -= deduct

        adjusted_total = sum(adjusted.values(), Decimal("0"))
        if abs(adjusted_total - defendant_burden) > Decimal("0.05"):
            continue

        for key, new_total in adjusted.items():
            key_indices = [i for i in indices if fee_items[i].key == key]
            if not key_indices:
                continue
            if len(key_indices) == 1:
                fee_items[key_indices[0]].amount = max(new_total, Decimal("0"))
                continue

            old_total = sum((fee_items[i].amount for i in key_indices), Decimal("0"))
            if old_total <= 0:
                continue
            assigned = Decimal("0")
            for i in key_indices[:-1]:
                scaled = (fee_items[i].amount * new_total / old_total).quantize(
                    Decimal("0.01"), rounding=ROUND_HALF_UP
                )
                fee_items[i].amount = max(scaled, Decimal("0"))
                assigned += fee_items[i].amount
            fee_items[key_indices[-1]].amount = max(new_total - assigned, Decimal("0"))


def extract_party_burden_amount(sentence: str, *, parties: tuple[str, ...]) -> Decimal | None:
    party_pattern = "|".join(re.escape(p) for p in parties if p)
    if not party_pattern:
        return None
    pattern = re.compile(rf"(?:由)?(?:{party_pattern})[^。；\n]{{0,50}}?(?:负担|承担)\s*{AMOUNT_WITH_UNIT_PATTERN}")
    match = pattern.search(sentence)
    if not match:
        return None
    return parse_amount_value(match.group(1), match.group(2))


def should_include_fee(*, sentence: str, key: str) -> tuple[bool, str]:
    # 律师费/担保费通常为"应向原告支付的款项构成部分"，默认纳入
    if key in {"attorney_fee", "guarantee_fee"}:
        return True, ""

    compact = sentence.replace(" ", "")
    pay_to_applicant_markers = (
        "支付给原告",
        "支付给申请人",
        "支付至原告",
        "支付至申请人",
        "返还给原告",
        "返还给申请人",
        "返还至原告",
        "返还至申请人",
        "直接支付给原告",
        "直接支付给申请人",
        "迳付原告",
        "迳付申请人",
        "迳付予原告",
        "迳付予申请人",
        "迳付给原告",
        "迳付给申请人",
        "向原告支付",
        "向申请人支付",
    )
    court_markers = ("向本院缴纳", "向法院缴纳", "缴纳至本院", "本院退回", "法院退回", "交至本院")

    if any(marker in compact for marker in pay_to_applicant_markers):
        return True, ""
    if ("向原告" in compact or "向申请人" in compact) and any(k in compact for k in ("支付", "返还", "迳付")):
        return True, ""
    if any(marker in compact for marker in court_markers):
        return False, "向法院缴纳/法院退回"
    prepaid_markers = ("原告已预交", "原告已缴纳", "原告已交", "申请人已预交", "申请人已缴纳", "申请人已交")
    burden_by_respondent = any(marker in compact for marker in ("由被告", "由两被告", "由各被告"))
    if (
        burden_by_respondent
        and "负担" in compact
        and "原告负担" not in compact
        and "申请人负担" not in compact
        and any(marker in compact for marker in prepaid_markers)
    ):
        return True, ""
    return False, "未明确支付给申请人/原告"
