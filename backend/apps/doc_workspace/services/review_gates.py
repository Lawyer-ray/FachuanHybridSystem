"""三道闸与立场对齐 —— 从 ``review_pipeline`` 拆出的纯规则模块。

这里只放「不碰 IO、不碰 DB、只对 dict 清单做判断」的规则：立场对齐决定同一条缺失
对哪一方算高风险，三道闸决定哪些条目能进清单。三条判据都可单元测试钉住，因此
独立成模块、不再和执行链（模型调用 / 落库）混在一个文件里。

依赖方向单向：``review_parse``（归一化时定严重度）与 ``review_pipeline``（执行链、
一页纸）都 import 本模块；本模块**不**反向 import 回 ``review_pipeline``（会成环）。
原模块 ``review_pipeline`` 按原路径 re-export 本模块全部符号，历史 import 不断裂。
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any

from ..models import Beneficiary, FindingKind, RuleClass, Severity, Stance, Verdict

MAX_MAIN_ITEMS = 25
FORMAT_RATIO_MAX = 0.20
TOP_N = 3

_SEVERITY_ORDER = [Severity.LOW, Severity.MEDIUM, Severity.HIGH]

#: 量化后果的判据：出现数字 + 单位/比例/期限，才算「说不改会亏什么」。
_QUANTIFIED_RE = re.compile(r"\d+(?:\.\d+)?\s*(?:%|％|万|亿|元|日|天|个月|年|倍|次|条|页)")


@dataclass
class GateReport:
    """三道闸的执行结果（写进 `run.summary`，可观测才叫闸）。"""

    dropped_format: int = 0
    dropped_cap: int = 0
    dropped_no_impact_from_top: int = 0
    mandatory_protected: int = 0
    """被闸门豁免的强制性条目数（它们既不被格式闸丢、也不被条数闸截）"""
    format_ratio_before: float = 0.0
    format_ratio_after: float = 0.0
    kept: int = 0
    top: list[str] = field(default_factory=list)


def _downgrade(severity: str) -> str:
    try:
        index = _SEVERITY_ORDER.index(severity)  # type: ignore[arg-type]
    except ValueError:
        return severity
    return _SEVERITY_ORDER[max(0, index - 1)]


def align_to_stance(
    *,
    beneficiary: str,
    stance: str,
    verdict: str,
    severity: str,
    rule_class: str = RuleClass.CONTRACTUAL,
) -> tuple[str, str, str]:
    """按立场调整结论。返回 `(verdict, severity, direction)`。

    `direction`：
    - `favor_us`  —— 这条标准保护我们，偏离 = 我们吃亏
    - `favor_them`—— 这条标准保护对方，偏离对我们无害 → 降一档
    - `neutral`   —— 对等条款或中立复核，不调整
    """
    # **强制性规则免疫立场对齐**：抵押未解除就转让、投资未达 25%、划拨地未审批……
    # 这些不是「对谁有利」的问题，是「转让本身可能无效」的问题。把它们的严重度
    # 按立场降一档，等于告诉律师「这条对你不重要」，而它会让整笔交易落空。
    if rule_class == RuleClass.MANDATORY:
        return verdict, severity, "mandatory"
    if stance == Stance.NEUTRAL or beneficiary == Beneficiary.NEUTRAL:
        return verdict, severity, "neutral"
    if beneficiary == stance:
        # 保护我们：缺失/偏离都要按标准库给的严重度算，不能降
        return verdict, severity, "favor_us"
    # 保护对方：偏离对我们反而是有利的，降一档并保留「观察到偏离」的事实
    return verdict, _downgrade(severity), "favor_them"


def has_quantified_consequence(text: str) -> bool:
    return bool(_QUANTIFIED_RE.search(text or ""))


def enforce_gates(
    items: list[dict[str, Any]],
    *,
    max_items: int = MAX_MAIN_ITEMS,
    format_ratio_max: float = FORMAT_RATIO_MAX,
    top_n: int = TOP_N,
) -> tuple[list[dict[str, Any]], GateReport]:
    """三道闸。返回 `(保留下来的条目, 报告)`。"""
    report = GateReport()
    total = len(items)
    if not total:
        return [], report

    formats = [i for i in items if i.get("kind") == FindingKind.FORMAT]
    report.format_ratio_before = round(len(formats) / total, 4)

    kept = list(items)

    # 闸一：格式类占比超限 → 从**低严重度**的格式条目开始丢。
    #
    # 注意分母会跟着变小：丢掉一条格式条目，分子和分母同时 -1，所以不能一次
    # 算好「该丢几条」，只能循环到占比真的落进阈值内。若清单里只有 2 条实质
    # 结论，20% 意味着格式条目标本应为 0 —— 这正是想要的结果（没有实质内容时
    # 不要拿格式条目凑数）。
    def _protected(item: dict[str, Any]) -> bool:
        """强制性规则不参与任何一道丢弃。"""
        return item.get("rule_class") == RuleClass.MANDATORY

    while kept:
        format_count = len([i for i in kept if i.get("kind") == FindingKind.FORMAT])
        if not format_count or format_count / len(kept) <= format_ratio_max:
            break
        victims = [i for i in kept if i.get("kind") == FindingKind.FORMAT and not _protected(i)]
        if not victims:
            break
        victim = min(victims, key=lambda i: _SEVERITY_ORDER.index(i.get("severity", Severity.LOW)))
        kept = [i for i in kept if i is not victim]
        report.dropped_format += 1

    # 闸二：条数上限 → 按严重度保留（高在前），**不是砍尾部**。
    # 强制性条目先占位、永不被截：条数闸治的是「格式/措辞类噪音」，
    # 把一条「合同可能无效」挤出去，等于用降噪的理由制造漏判。
    protected = [i for i in kept if _protected(i)]
    report.mandatory_protected = len(protected)
    if len(kept) > max_items:
        rest = [i for i in kept if not _protected(i)]
        room = max(0, max_items - len(protected))
        ranked = sorted(rest, key=lambda i: -_SEVERITY_ORDER.index(i.get("severity", Severity.LOW)))
        keep_ids = {id(i) for i in ranked[:room]} | {id(i) for i in protected}
        report.dropped_cap = len(kept) - len(keep_ids)
        kept = [i for i in kept if id(i) in keep_ids]

    live = len(kept)
    report.format_ratio_after = round(
        (len([i for i in kept if i.get("kind") == FindingKind.FORMAT]) / live) if live else 0.0, 4
    )
    report.kept = live

    # 闸三：Top-N 必须带量化后果；写不出来的降级回清单（不给上台）
    top_candidates = sorted(
        (i for i in kept if i.get("verdict") != Verdict.NOT_APPLICABLE),
        key=lambda i: -_SEVERITY_ORDER.index(i.get("severity", Severity.LOW)),
    )
    for item in top_candidates:
        if len(report.top) >= top_n:
            break
        impact = str(item.get("impact") or item.get("reason") or "")
        if not has_quantified_consequence(impact):
            item["in_top"] = False
            report.dropped_no_impact_from_top += 1
            continue
        item["in_top"] = True
        report.top.append(str(item.get("title") or item.get("rule_key") or ""))
    return kept, report
