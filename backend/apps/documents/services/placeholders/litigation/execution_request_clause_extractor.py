"""强制执行申请书 - 条款提取."""

from __future__ import annotations

import re
from datetime import date
from decimal import Decimal

from .execution_request_models import InterestSegment, OverdueInterestRule, ParsedInterestParams
from .execution_request_utils import AMOUNT_WITH_UNIT_PATTERN, build_date, format_amount, parse_amount_value, parse_multiplier_value


def has_double_interest_clause(main_text: str) -> bool:
    return bool(re.search(r"加倍支付\s*迟\s*延履行期间(?:的)?债务利息", main_text))


def extract_supplementary_liability_text(main_text: str) -> str:
    for sentence in re.split(r"[。；\n]", main_text):
        text = sentence.strip()
        if not text:
            continue
        text = re.sub(r"^[一二三四五六七八九十\d]+[、.]\s*", "", text)
        if not text:
            continue
        if "责任" in text:
            if (
                "补充" in text
                and any(keyword in text for keyword in ("补充赔偿责任", "补充清偿责任", "承担补充责任", "补充责任"))
                and any(keyword in text for keyword in ("不能清偿", "未出资", "未出资本息", "清偿部分", "上述债务"))
            ):
                return text
            if (
                any(
                    keyword in text
                    for keyword in ("财产不足清偿部分", "财产不足以清偿部分", "不能清偿部分", "不足清偿部分")
                )
                and "承担" in text
                and "清偿责任" in text
            ):
                return text
    return ""


def extract_joint_liability_text(main_text: str) -> str:
    for sentence in re.split(r"[。；\n]", main_text):
        text = sentence.strip()
        if not text:
            continue
        text = re.sub(r"^[一二三四五六七八九十\d]+[、.]\s*", "", text)
        if not text:
            continue
        if "连带" not in text or "责任" not in text:
            continue
        if "承担" not in text:
            continue
        if any(k in text for k in ("债务", "清偿", "本判决第一项", "判决第一项")):
            return text
    return ""


def extract_priority_execution_texts(main_text: str) -> list[str]:
    results: list[str] = []
    for sentence in re.split(r"[。；\n]", main_text):
        text = sentence.strip()
        if not text:
            continue
        text = re.sub(r"^[一二三四五六七八九十\d]+[、.]\s*", "", text)
        if not text:
            continue
        if "优先受偿权" not in text:
            continue
        if not any(keyword in text for keyword in ("折价", "拍卖", "变卖", "土地", "股权", "不动产", "抵押顺位")):
            continue
        if text not in results:
            results.append(text)
    return results


def extract_manual_review_clauses(main_text: str, *, recognized_texts: list[str]) -> list[str]:
    clauses = extract_numbered_clauses(main_text)
    if not clauses:
        return []

    recognized_compact = {
        re.sub(r"\s+", "", str(text or "")) for text in recognized_texts if str(text or "").strip()
    }
    disposal_keywords = ("折价", "拍卖", "变卖")
    asset_keywords = ("土地", "不动产", "股权", "应收账款", "机器设备", "房产", "车辆")

    results: list[str] = []
    for clause in clauses:
        text = clause.strip()
        if not text:
            continue
        compact = re.sub(r"\s+", "", text)
        is_priority_like = "优先受偿权" in text or (
            any(keyword in text for keyword in disposal_keywords)
            and any(keyword in text for keyword in asset_keywords)
        )
        if not is_priority_like:
            continue
        if any(keyword in text for keyword in ("受理费", "保全费", "公告费", "律师费", "担保费", "抵扣")):
            continue
        if any(rc and rc in compact for rc in recognized_compact):
            continue
        if text not in results:
            results.append(text.rstrip("。；"))
    return results


def extract_numbered_clauses(main_text: str) -> list[str]:
    marker_pattern = re.compile(r"(?:^|(?<=[。；\n]))\s*([一二三四五六七八九十\d]+[、.])")
    markers = list(marker_pattern.finditer(main_text))
    if not markers:
        return []

    clauses: list[str] = []
    for index, marker in enumerate(markers):
        start = marker.start(1)
        end = markers[index + 1].start(1) if index + 1 < len(markers) else len(main_text)
        clause = main_text[start:end].strip()
        if clause:
            clauses.append(clause)
    return clauses


def extract_original_segmented_interest_expression(*, main_text: str, overdue_label: str) -> str:
    label = (overdue_label or "").strip()
    if not label:
        return ""

    pattern = re.compile(rf"({re.escape(label)}\s*[（(][^（）()]{{10,4000}}[）)])")
    for match in pattern.finditer(main_text):
        text = match.group(1).strip()
        base_count = text.count("为基数") + text.count("为本金")
        if base_count < 2:
            continue
        if not any(keyword in text for keyword in ("计算至", "计至", "付清之日", "清偿之日", "履行之日")):
            continue
        return text
    return ""


def parse_overdue_interest_rules(main_text: str) -> list[OverdueInterestRule]:
    from .execution_request_interest import parse_interest_params

    rules: list[OverdueInterestRule] = []
    candidates: list[str] = []
    seen: set[str] = set()

    parenthesized_pattern = re.compile(r"逾期利息[^。；\n]{0,30}?[（(]([^（）()]{6,1000})[）)]")
    for match in parenthesized_pattern.finditer(main_text):
        clause = match.group(1).strip()
        if not clause:
            continue
        key = clause.replace(" ", "")
        if key in seen:
            continue
        seen.add(key)
        candidates.append(clause)

    # 兼容"并支付利息、罚息、复利（...）"等未直接出现"逾期利息（"前缀的复杂写法
    if not candidates:
        generic_parenthesized_pattern = re.compile(r"[（(]([^（）()]{6,1000})[）)]")
        for match in generic_parenthesized_pattern.finditer(main_text):
            clause = match.group(1).strip()
            if not clause:
                continue
            has_interest_keywords = any(keyword in clause for keyword in ("逾期利息", "罚息", "复利"))
            has_base_and_rate = "为基数" in clause and (
                "年利率" in clause or bool(re.search(r"(?:LPR|贷款市场报价利率|一年期贷款市场报价利率)", clause))
            )
            if not (has_interest_keywords or has_base_and_rate):
                continue
            if not any(keyword in clause for keyword in ("计算至", "清偿之日", "偿还之日", "付清之日", "履行之日")):
                continue
            key = clause.replace(" ", "")
            if key in seen:
                continue
            seen.add(key)
            candidates.append(clause)

    if not candidates:
        for sentence in re.split(r"[。；\n]", main_text):
            text = sentence.strip()
            if not text or "逾期利息" not in text:
                continue
            key = text.replace(" ", "")
            if key in seen:
                continue
            seen.add(key)
            candidates.append(text)

    for clause in candidates:
        dual_phase_rules = _parse_dual_phase_overdue_interest_rules(clause)
        if dual_phase_rules:
            rules.extend(dual_phase_rules)
            continue
        params = parse_interest_params(clause)
        segments = parse_interest_segments(clause)
        if segments and params.start_date is None:
            params.start_date = min(segment.start_date for segment in segments)
        if params.multiplier is None and params.custom_rate_value is None:
            continue
        if params.start_date is None and not segments:
            continue
        rules.append(OverdueInterestRule(params=params, segments=segments, source_text=clause))

    return rules


def _parse_dual_phase_overdue_interest_rules(clause: str) -> list[OverdueInterestRule]:
    compact = clause.replace(" ", "")
    if not any(token in compact for token in ("年利率", "年化率", "年化利率")):
        return []
    if not re.search(r"(?:LPR|贷款市场报价利率|一年期贷款市场报价利率)", clause):
        return []
    if "为基数" not in clause:
        return []

    chunks = [chunk.strip() for chunk in re.split(r"[；;]", clause) if "为基数" in chunk]
    if not chunks:
        return []

    fixed_pattern_a = re.compile(
        r"(?:从|自)\s*(?P<sy>\d{4})\s*年\s*(?P<sm>\d{1,2})\s*月\s*(?P<sd>\d{1,2})\s*日(?:起)?"
        r"[^。；;\n]{0,80}?(?:按|按照)\s*(?P<rate_label>年利率|年化率|年化利率)\s*(?P<rate>[0-9]+(?:\.[0-9]+)?)\s*%\s*计算至\s*"
        r"(?P<ey>\d{4})\s*年\s*(?P<em>\d{1,2})\s*月\s*(?P<ed>\d{1,2})\s*日"
    )
    fixed_pattern_b = re.compile(
        r"(?:从|自)\s*(?P<sy>\d{4})\s*年\s*(?P<sm>\d{1,2})\s*月\s*(?P<sd>\d{1,2})\s*日(?:起)?\s*至\s*"
        r"(?P<ey>\d{4})\s*年\s*(?P<em>\d{1,2})\s*月\s*(?P<ed>\d{1,2})\s*日"
        r"[^。；;\n]{0,40}?(?:按|按照)\s*(?P<rate_label>年利率|年化率|年化利率)\s*(?P<rate>[0-9]+(?:\.[0-9]+)?)\s*%\s*计算"
    )
    lpr_core_pattern = re.compile(
        r"(?:LPR|贷款市场报价利率|一年期贷款市场报价利率)[^。；;\n]{0,40}?"
        r"(?P<mult>[0-9]+(?:\.[0-9]+)?|[零一二两三四五六七八九十]+)\s*倍"
    )
    date_from_pattern = re.compile(
        r"(?:从|自)\s*(?P<sy>\d{4})\s*年\s*(?P<sm>\d{1,2})\s*月\s*(?P<sd>\d{1,2})\s*日(?:起)?"
    )
    base_pattern = re.compile(rf"以[^，,；;。\n]{{0,30}}?{AMOUNT_WITH_UNIT_PATTERN}\s*为基数")

    fixed_groups: dict[tuple[str, Decimal], list[InterestSegment]] = {}
    lpr_groups: dict[Decimal, list[InterestSegment]] = {}

    for chunk in chunks:
        base_match = base_pattern.search(chunk)
        if not base_match:
            continue
        base_amount = parse_amount_value(base_match.group(1), base_match.group(2))
        if base_amount is None:
            continue

        fixed_match = fixed_pattern_a.search(chunk) or fixed_pattern_b.search(chunk)
        if fixed_match:
            start_date = build_date(fixed_match.group("sy"), fixed_match.group("sm"), fixed_match.group("sd"))
            end_date = build_date(fixed_match.group("ey"), fixed_match.group("em"), fixed_match.group("ed"))
            fixed_rate = Decimal(fixed_match.group("rate"))
            fixed_rate_label = str(fixed_match.group("rate_label") or "年利率")
            if start_date and end_date and fixed_rate is not None and end_date >= start_date:
                fixed_groups.setdefault((fixed_rate_label, fixed_rate), []).append(
                    InterestSegment(base_amount=base_amount, start_date=start_date, end_date=end_date)
                )

        lpr_match = lpr_core_pattern.search(chunk)
        if lpr_match:
            multiplier = parse_multiplier_value(lpr_match.group("mult"))
            prefix = chunk[: lpr_match.start()]
            date_matches = list(date_from_pattern.finditer(prefix))
            start_date = None
            if date_matches:
                nearest = date_matches[-1]
                start_date = build_date(nearest.group("sy"), nearest.group("sm"), nearest.group("sd"))
            if start_date and multiplier is not None:
                lpr_groups.setdefault(multiplier, []).append(
                    InterestSegment(base_amount=base_amount, start_date=start_date, end_date=None)
                )

    if not fixed_groups or not lpr_groups:
        return []

    rules: list[OverdueInterestRule] = []
    for (fixed_rate_label, fixed_rate), segments in sorted(fixed_groups.items(), key=lambda item: item[0][1]):
        ordered_segments = sorted(segments, key=lambda s: (s.start_date, s.end_date or date.max))
        params = ParsedInterestParams(
            start_date=ordered_segments[0].start_date,
            custom_rate_unit="percent",
            custom_rate_value=fixed_rate,
            rate_description=f"{fixed_rate_label}{format_amount(fixed_rate)}%",
        )
        rules.append(OverdueInterestRule(params=params, segments=ordered_segments, source_text=clause))

    for multiplier, segments in sorted(lpr_groups.items(), key=lambda item: item[0]):
        ordered_segments = sorted(segments, key=lambda s: (s.start_date, s.end_date or date.max))
        if multiplier == Decimal("1"):
            desc = "全国银行间同业拆借中心公布的一年期贷款市场报价利率"
        else:
            desc = f"全国银行间同业拆借中心公布的一年期贷款市场报价利率的{format_amount(multiplier)}倍"
        params = ParsedInterestParams(
            start_date=ordered_segments[0].start_date,
            rate_type="1y",
            multiplier=multiplier,
            rate_description=desc,
        )
        rules.append(OverdueInterestRule(params=params, segments=ordered_segments, source_text=clause))

    return rules


def parse_interest_segments(main_text: str) -> list[InterestSegment]:
    segment_pattern = re.compile(
        rf"以[^，,；。\n]{{0,30}}?{AMOUNT_WITH_UNIT_PATTERN}\s*为(?:基数|本金)\s*"
        r"(?:，|,)?\s*(?:自|从)\s*(\d{4})\s*年\s*(\d{1,2})\s*月\s*(\d{1,2})\s*日(?:起|起算|开始|计)?"
        r"[^，,；。\n]{0,120}?计算至\s*"
        r"(?:(\d{4})\s*年\s*(\d{1,2})\s*月\s*(\d{1,2})\s*日(?:止)?|实际(?:清偿|付清|履行|还清)(?:之日)?(?:止)?)"
    )
    segment_start_only_pattern = re.compile(
        rf"以[^，,；。\n]{{0,30}}?{AMOUNT_WITH_UNIT_PATTERN}\s*为(?:基数|本金)\s*"
        r"(?:，|,)?\s*(?:自|从)\s*(\d{4})\s*年\s*(\d{1,2})\s*月\s*(\d{1,2})\s*日(?:起|起算|开始|计)?"
    )

    segments: list[InterestSegment] = []

    for match in segment_pattern.finditer(main_text):
        base_amount = parse_amount_value(match.group(1), match.group(2))
        start_date = build_date(match.group(3), match.group(4), match.group(5))
        end_date: date | None = None
        if match.group(6) and match.group(7) and match.group(8):
            end_date = build_date(match.group(6), match.group(7), match.group(8))
        if base_amount is None or start_date is None:
            continue
        if match.group(6) and end_date is None:
            continue
        candidate = InterestSegment(base_amount=base_amount, start_date=start_date, end_date=end_date)
        if any(
            seg.base_amount == candidate.base_amount
            and seg.start_date == candidate.start_date
            and seg.end_date == candidate.end_date
            for seg in segments
        ):
            continue
        segments.append(candidate)

    # 兼容"分段起算 + 统一尾句计算至…"的写法
    if len(segments) < 2:
        shared_end_date = _extract_shared_segment_end_date(main_text)
        for match in segment_start_only_pattern.finditer(main_text):
            base_amount = parse_amount_value(match.group(1), match.group(2))
            start_date = build_date(match.group(3), match.group(4), match.group(5))
            if base_amount is None or start_date is None:
                continue
            candidate = InterestSegment(base_amount=base_amount, start_date=start_date, end_date=shared_end_date)
            if any(
                seg.base_amount == candidate.base_amount
                and seg.start_date == candidate.start_date
                and seg.end_date == candidate.end_date
                for seg in segments
            ):
                continue
            segments.append(candidate)

    # 兼容"日期在前 + 多基数在后"的写法
    if len(segments) < 2:
        date_first_pattern = re.compile(
            r"(?:自|从)\s*(\d{4})\s*年\s*(\d{1,2})\s*月\s*(\d{1,2})\s*日(?:起|起算|开始|计)?"
        )
        base_pattern = re.compile(rf"以[^，,；。\n]{{0,30}}?{AMOUNT_WITH_UNIT_PATTERN}\s*为(?:基数|本金)")
        for sentence in re.split(r"[。；\n]", main_text):
            sentence = sentence.strip()
            if not sentence:
                continue
            date_match = date_first_pattern.search(sentence)
            if not date_match:
                continue
            if "为基数" not in sentence and "为本金" not in sentence:
                continue
            start_date = build_date(date_match.group(1), date_match.group(2), date_match.group(3))
            if start_date is None:
                continue
            sentence_end_date = _extract_shared_segment_end_date(sentence)
            for match in base_pattern.finditer(sentence):
                base_amount = parse_amount_value(match.group(1), match.group(2))
                if base_amount is None:
                    continue
                candidate = InterestSegment(
                    base_amount=base_amount, start_date=start_date, end_date=sentence_end_date
                )
                if any(
                    seg.base_amount == candidate.base_amount
                    and seg.start_date == candidate.start_date
                    and seg.end_date == candidate.end_date
                    for seg in segments
                ):
                    continue
                segments.append(candidate)

    return sorted(segments, key=lambda s: (s.start_date, s.end_date or date.max))


def _extract_shared_segment_end_date(main_text: str) -> date | None:
    shared_date_match = re.search(
        r"(?:均|并|分别)?[^。；\n]{0,80}?计算至\s*(\d{4})\s*年\s*(\d{1,2})\s*月\s*(\d{1,2})\s*日(?:止)?",
        main_text,
    )
    if shared_date_match:
        return build_date(shared_date_match.group(1), shared_date_match.group(2), shared_date_match.group(3))

    shared_actual_match = re.search(
        r"(?:均|并|分别)?[^。；\n]{0,80}?计算至\s*实际(?:清偿|付清|履行|还清)(?:之日)?(?:止)?",
        main_text,
    )
    if shared_actual_match:
        return None

    return None
