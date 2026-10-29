"""Module for validators."""

from __future__ import annotations

import re
from collections.abc import Iterable
from datetime import date

from apps.core.exceptions import ValidationException
from apps.core.models.enums import CaseStage, CaseType

APPLICABLE_TYPES = {CaseType.CIVIL, CaseType.CRIMINAL, CaseType.ADMINISTRATIVE, CaseType.LABOR, CaseType.INTL}


# ---------------------------------------------------------------------------
# 顾问合同标题-日期一致性校验
# ---------------------------------------------------------------------------

# 完整中文日期: 2026年08月12日 / 2026年8月12日 / 2026年08月 / 2026年8月
_DATE_FULL_RE = re.compile(r"(\d{4})\s*年\s*(\d{1,2})\s*月\s*(\d{1,2})\s*日")

# "YYYY-YYYY" 或 "YYYY～YYYY" 年度范围（中间可选"年""至"等文字）
_YEAR_RANGE_RE = re.compile(r"(?<!\d)(\d{4})\s*[-–—~～]\s*(\d{4})(?!\d)")

# 独立四位年份（不在已被 _YEAR_RANGE_RE 匹配的范围内）
_YEAR_RE = re.compile(r"(?<!\d)(\d{4})(?!\d)")

# 两位年份缩写: 26-27 / 26~27
_SHORT_YEAR_RANGE_RE = re.compile(r"(?<!\d)(\d{2})\s*[-–—~～]\s*(\d{2})(?!\d)")


def _normalize_2digit_year(y: int) -> int:
    """把两位年份映射到 2000+Y（假设在 2000-2099 范围内）。"""
    return y + 2000 if y < 100 else y


def validate_advisor_contract_title_dates(
    case_type: str | None,
    title: str | None,
    start_date: date | None,
    end_date: date | None,
) -> None:
    """
    校验常法顾问合同标题中的日期/年度信息是否与开始/结束日期一致。

    只在 case_type == ADVISOR 且标题含可识别日期模式时才校验。
    不含任何日期信息的标题不做校验。

    Raises:
        ValidationException: 标题日期与实际日期不匹配时抛出。
    """
    if case_type != CaseType.ADVISOR:
        return

    if not title or not start_date or not end_date:
        return

    title = title.strip()

    # ---- 1. 提取完整中文日期 ----
    raw_dates = _DATE_FULL_RE.findall(title)
    specific_dates: list[int] = []
    for m_y, m_m, m_d in raw_dates:
        try:
            dt = date(int(m_y), int(m_m), int(m_d))
        except ValueError:
            continue
        specific_dates.append(dt.year * 10000 + dt.month * 100 + dt.day)

    # ---- 2. 提取年份范围 (优先匹配短横线连接的) ----
    years: list[int] = []

    short_range = _SHORT_YEAR_RANGE_RE.search(title)
    if short_range:
        y1 = _normalize_2digit_year(int(short_range.group(1)))
        y2 = _normalize_2digit_year(int(short_range.group(2)))
        years.extend([y1, y2])
    else:
        full_range = _YEAR_RANGE_RE.search(title)
        if full_range:
            years.extend([int(full_range.group(1)), int(full_range.group(2))])

    # 独立年份（排除已被范围匹配的年份）
    if not years:
        seen_spans: list[tuple[int, int]] = []
        for m in _YEAR_RANGE_RE.finditer(title):
            seen_spans.append((m.start(), m.end()))
        for m in _YEAR_RE.finditer(title):
            if any(s <= m.start() < e for s, e in seen_spans):
                continue
            years.append(int(m.group(1)))

    # ---- 3. 没有可校验信息则跳过 ----
    if not years and not specific_dates:
        return

    # ---- 4. 如果有完整日期，要求精确匹配 ----
    if specific_dates:
        actual_start_int = start_date.year * 10000 + start_date.month * 100 + start_date.day
        actual_end_int = end_date.year * 10000 + end_date.month * 100 + end_date.day

        first_int = specific_dates[0]
        last_int = specific_dates[-1]

        def _fmt_date_int(v: int) -> str:
            y, rem = divmod(v, 10000)
            m, d = divmod(rem, 100)
            return "%d年%d月%d日" % (y, m, d)

        if first_int != actual_start_int:
            raise ValidationException(
                "顾问合同标题中的开始日期（%(title_date)s）与实际开始日期（%(actual_date)s）不一致"
                % {"title_date": _fmt_date_int(first_int), "actual_date": start_date.strftime("%Y年%m月%d日")},
                code="ADVISOR_TITLE_DATE_MISMATCH",
            )
        if last_int != actual_end_int:
            raise ValidationException(
                "顾问合同标题中的结束日期（%(title_date)s）与实际结束日期（%(actual_date)s）不一致"
                % {"title_date": _fmt_date_int(last_int), "actual_date": end_date.strftime("%Y年%m月%d日")},
                code="ADVISOR_TITLE_DATE_MISMATCH",
            )
        return

    # ---- 5. 只有年份范围时，校验年份是否覆盖实际日期 ----
    if len(years) >= 2:
        title_start_year, title_end_year = years[0], years[1]
        if title_start_year > title_end_year:
            title_start_year, title_end_year = title_end_year, title_start_year

        if not (start_date.year <= title_start_year and end_date.year >= title_end_year):
            raise ValidationException(
                "顾问合同标题年度范围（%(ty_start)s-%(ty_end)s）与实际日期（%(as)s ~ %(ae)s）不匹配"
                % {
                    "ty_start": title_start_year,
                    "ty_end": title_end_year,
                    "as": start_date.strftime("%Y-%m-%d"),
                    "ae": end_date.strftime("%Y-%m-%d"),
                },
                code="ADVISOR_TITLE_YEAR_MISMATCH",
            )
    elif len(years) == 1:
        # 只有一个年份，检查是否在合同期间内
        y = years[0]
        if not (start_date.year <= y <= end_date.year):
            raise ValidationException(
                "顾问合同标题中的年份（%(ty)s）不在合同期（%(as)s ~ %(ae)s）范围内"
                % {"ty": y, "as": start_date.strftime("%Y-%m-%d"), "ae": end_date.strftime("%Y-%m-%d")},
                code="ADVISOR_TITLE_YEAR_MISMATCH",
            )


def normalize_representation_stages(
    case_type: str | None,
    representation_stages: Iterable[str] | None,
    strict: bool = False,
) -> list[str]:
    if not case_type or case_type not in APPLICABLE_TYPES:
        rep = list(representation_stages or [])
        if strict and rep:
            raise ValidationException("代理阶段不适用于此合同类型", code="STAGES_NOT_APPLICABLE")
        return []

    rep = list(representation_stages or [])
    allowed = {c[0] for c in CaseStage.choices}
    invalid = set(rep) - allowed
    if invalid:
        raise ValidationException(
            "无效的代理阶段",
            code="INVALID_STAGES",
            errors={"invalid_stages": sorted(invalid)},
        )
    return rep


# ---------------------------------------------------------------------------
# 非诉专项阶段树（Contract.stages）校验
# ---------------------------------------------------------------------------

# 阶段树最多 3 级（1 / 1.1 / 1.1.2），与原型的拖动升降级上限一致
STAGE_MAX_DEPTH = 3


def _stage_depth(nodes: Iterable[object]) -> int:
    """树的实际深度（根层为 1，空树为 0）。"""
    depth = 0
    level: list[object] = list(nodes)
    while level:
        depth += 1
        level = [c for node in level if isinstance(node, dict) for c in node.get("children") or []]
    return depth


def _stage_nodes(nodes: Iterable[object]) -> list[dict]:
    """先序展开全部阶段节点（非 dict 的子项已在上游被拒）。"""
    out: list[dict] = []
    level: list[object] = list(nodes)
    while level:
        out.extend(node for node in level if isinstance(node, dict))
        level = [c for node in level if isinstance(node, dict) for c in node.get("children") or []]
    return out


def validate_stages(stages: object) -> list[dict]:
    """校验非诉专项阶段树，返回节点列表。

    结构由前端定形（键名必须一致，前端已按此实现）：

        {"key": "ph_x", "name": "尽职调查", "acceptance": "《尽调报告》定稿",
         "templates": ["模板名"], "date": "2026-10-26",
         "deliverables": [{"date": "", "doc": "《报告》", "ver": "v1",
                           "state": "ok|doing|todo", "planned": true}],
         "children": [...]}

    只校验结构不变量（深度 ≤ 3、key 唯一且非空、name 非空），字段值不替前端改写——
    阶段名可改、顺序可调，服务端没有比前端更权威的默认值。

    Raises:
        ValidationException: 不是列表 / 超过 3 级 / key 重复或缺失 / name 为空时抛出。
    """
    if stages is None:
        return []
    if not isinstance(stages, list):
        raise ValidationException("阶段树必须是数组", code="INVALID_STAGES_TREE")
    if any(not isinstance(node, dict) for node in stages):
        raise ValidationException("阶段节点必须是对象", code="INVALID_STAGES_TREE")

    depth = _stage_depth(stages)
    if depth > STAGE_MAX_DEPTH:
        raise ValidationException(
            "阶段树最多 %(max_depth)d 级" % {"max_depth": STAGE_MAX_DEPTH},
            code="STAGES_TOO_DEEP",
            errors={"depth": depth, "max_depth": STAGE_MAX_DEPTH},
        )

    nodes = _stage_nodes(stages)
    # 先收窄成 str：空 key 已在上一步抛错，后续判重/取值不再面对 Any | None
    keys = [str(node.get("key") or "") for node in nodes]
    if not all(keys):
        raise ValidationException("阶段 key 不能为空", code="INVALID_STAGE_KEY")
    duplicates = sorted({k for k in keys if keys.count(k) > 1})
    if duplicates:
        raise ValidationException(
            "阶段 key 重复",
            code="DUPLICATE_STAGE_KEY",
            errors={"duplicate_keys": duplicates},
        )

    nameless = [key for key, node in zip(keys, nodes, strict=True) if not _stage_name(node)]
    if nameless:
        raise ValidationException(
            "阶段名称不能为空",
            code="INVALID_STAGE_NAME",
            errors={"keys": nameless},
        )
    return stages


def _stage_name(node: dict) -> str:
    name = node.get("name")
    return name.strip() if isinstance(name, str) else ""
