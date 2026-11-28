"""模型输出解析与归一化 —— 从 ``review_pipeline`` 拆出的纯函数模块。

上游只管一件事：把模型返回的任意文本变成「可归一化的 finding 清单」，再把清单
归一化成落库字段。两种形状（新契约对象 / 老契约裸数组）的兼容、截断抢救、
立场对齐都在这里，全部无 IO——唯一副作用是 logger.warning，用来留下
「输出被截断」的痕迹（那意味着模型把预算花在了分析文字上）。

依赖方向单向：``review_parse`` → ``review_gates``；``review_pipeline`` import 本模块；
本模块**不**反向 import ``review_pipeline``（会成环）。原模块按原路径 re-export
本模块全部符号，历史 import 不断裂。
"""

from __future__ import annotations

import json
import logging
import re
from dataclasses import dataclass, field
from typing import Any

from ..models import (
    Beneficiary,
    Consequence,
    Delivery,
    FindingKind,
    RiskSource,
    RuleClass,
    Severity,
    SourceWeight,
    Stage,
    Verdict,
)
from .review_gates import align_to_stance

logger = logging.getLogger(__name__)

_JSON_ARRAY_RE = re.compile(r"\[.*\]", re.DOTALL)


@dataclass
class ReviewOutput:
    """一次审查的完整产出：标的画像 + 关系网 + 结论。"""

    findings: list[dict[str, Any]] = field(default_factory=list)
    subject_profile: list[str] = field(default_factory=list)
    relations: list[dict[str, str]] = field(default_factory=list)


def parse_review_output(raw: str) -> ReviewOutput:
    """解析模型输出。**同时兼容两种形状**：

    - 新契约：`{"subject_profile": [...], "relations": [...], "findings": [...]}`；
    - 老契约：裸 JSON 数组（早期版本 / 测试桩）。

    兼容不是偷懒：模型遵守新契约的比例永远不是 100%，而「因为整体结构不合规就把
    整份审查结果丢掉」是不可接受的——宁可少拿标的画像，也要把结论留下。
    """
    if not (raw or "").strip():
        return ReviewOutput()
    text = raw.strip()
    fenced = re.search(r"```(?:json)?\s*(.*?)```", text, re.DOTALL)
    if fenced:
        text = fenced.group(1).strip()

    # 先试对象
    obj = re.search(r"\{.*\}", text, re.DOTALL)
    if obj:
        try:
            parsed = json.loads(obj.group(0))
        except json.JSONDecodeError:
            parsed = None
        # **必须确认它真是新契约**：模型返回单元素数组 `[{...}]` 时，上面的
        # `\{.*\}` 只会截到内层那个对象，那个对象里没有 findings 键——若直接当成
        # 新契约，结论就被整份丢掉了（真机踩过：一份只有 1 条意见的合同永远空清单）。
        if isinstance(parsed, dict) and ({"findings", "subject_profile", "relations"} & set(parsed)):
            findings = parsed.get("findings")
            profile = parsed.get("subject_profile")
            relations = parsed.get("relations")
            return ReviewOutput(
                findings=[i for i in findings if isinstance(i, dict)] if isinstance(findings, list) else [],
                subject_profile=[str(p_) for p_ in profile if str(p_).strip()] if isinstance(profile, list) else [],
                relations=[
                    {
                        "relation": str(r.get("relation") or "").strip(),
                        "why": str(r.get("why") or "").strip(),
                        "risk": str(r.get("risk") or "").strip(),
                    }
                    for r in relations
                    if isinstance(r, dict) and str(r.get("relation") or "").strip()
                ]
                if isinstance(relations, list)
                else [],
            )

    # 截断抢救：模型把预算花在前面的口语分析上时，JSON 会被切在半句。
    # 整份丢弃的代价是「AI 审了半天，清单空白」——比拿到 3 条不完整结论严重得多。
    salvaged = _salvage_findings(text)
    if salvaged:
        logger.warning("审查输出被截断，已抢救出 %d 条结论", len(salvaged))
        return ReviewOutput(findings=salvaged)

    # 退回老契约：裸数组
    match = _JSON_ARRAY_RE.search(text)
    if not match:
        logger.warning("审查结果无法解析（既不是对象也不是数组），前 200 字：%s", text[:200])
        return ReviewOutput()
    try:
        data = json.loads(match.group(0))
    except json.JSONDecodeError:
        logger.warning("审查结果不是合法 JSON，前 200 字：%s", text[:200])
        return ReviewOutput()
    return ReviewOutput(findings=[i for i in data if isinstance(i, dict)] if isinstance(data, list) else [])


def _load_complete_object(chunk: str) -> dict[str, Any] | None:
    """`json.loads` 一个括号已配对的片段；不是合法 JSON 对象就返回 `None`。"""
    try:
        parsed = json.loads(chunk)
    except json.JSONDecodeError:
        return None
    return parsed if isinstance(parsed, dict) else None


def _salvage_findings(text: str) -> list[dict[str, Any]]:
    """从**被截断**的模型输出里捞出所有完整的 finding 对象。

    只做一件事：从 `"findings"` 后面的 `[` 开始按括号配对扫，遇到配对完整的
    `{...}` 就 `json.loads` 一次，遇到不完整的（被截断）就停。`subject_profile`
    与 `relations` 在截断场景下一律放弃——结论优先，画像可以下一轮再拿。

    刻意**不猜**：不补引号、不补逗号、不把半截对象当完整对象。捞不出来就返回空，
    让上层走「零结论 + 失败提示」这条确定路径，而不是拿一份改过的 JSON 去写库。
    """
    start = text.find('"findings"')
    if start < 0:
        return []
    array_start = text.find("[", start)
    if array_start < 0:
        return []

    findings: list[dict[str, Any]] = []
    depth = 0
    obj_start: int | None = None
    in_string = False
    escaped = False
    for index in range(array_start, len(text)):
        char = text[index]
        if in_string:
            if escaped:
                escaped = False
            elif char == "\\":
                escaped = True
            elif char == '"':
                in_string = False
            continue
        if char == '"':
            in_string = True
            continue
        if char == "]" and depth == 0:
            break
        if char == "}":
            depth -= 1
            if depth != 0 or obj_start is None:
                continue
            chunk = text[obj_start : index + 1]
            obj_start = None
            parsed = _load_complete_object(chunk)
            if parsed is not None:
                findings.append(parsed)
            continue
        if char == "{":
            if depth == 0:
                obj_start = index
            depth += 1
    return findings


def parse_findings(raw: str) -> list[dict[str, Any]]:
    """兼容旧调用方：只取结论。"""
    return parse_review_output(raw).findings


def _normalize_item(
    item: dict[str, Any], *, rules_by_key: dict[str, dict[str, Any]], stance: str
) -> dict[str, Any] | None:
    rule_key = str(item.get("rule_key") or "").strip()
    rule = rules_by_key.get(rule_key)
    if rule is None:
        # 模型自创检查项：不入库。闸一拦不住的东西必须在这里拦。
        logger.info("丢弃自创检查项：%s", rule_key or "(空)")
        return None

    verdict = str(item.get("verdict") or Verdict.DEVIATION)
    if verdict not in Verdict.values:
        verdict = Verdict.DEVIATION
    severity = str(item.get("severity") or rule.get("severity_if_missing") or Severity.MEDIUM)
    if severity not in Severity.values:
        severity = Severity.MEDIUM

    rule_class = str(rule.get("rule_class") or RuleClass.CONTRACTUAL)
    verdict, severity, direction = align_to_stance(
        beneficiary=str(rule.get("beneficiary") or Beneficiary.NEUTRAL),
        stance=stance,
        verdict=verdict,
        severity=severity,
        rule_class=rule_class,
    )

    replacement = str(item.get("suggestion_replacement") or "").strip()
    note = str(item.get("suggestion_note") or "").strip()
    if replacement:
        delivery = Delivery.BOTH if note else Delivery.REVISION
    elif note:
        delivery = Delivery.COMMENT
    else:
        delivery = Delivery.LIST_ONLY

    risk_source = str(item.get("risk_source") or RiskSource.STATUTE)
    if risk_source not in RiskSource.values:
        risk_source = RiskSource.STATUTE
    source_weight = str(item.get("source_weight") or SourceWeight.CORE)
    if source_weight not in SourceWeight.values:
        source_weight = SourceWeight.CORE

    case_ref = str(item.get("case_ref") or "").strip()[:255]
    if risk_source == RiskSource.CASE and not case_ref:
        # 声称「据类案」却给不出案号 = 无法回指。降为辅助来源：可以留作线索，
        # 但不能当决定性依据（编案号比不提类案严重得多）。
        source_weight = SourceWeight.SUPPORTING

    return {
        "rule_key": rule_key,
        "case_ref": case_ref,
        "clause_type": str(rule.get("clause_type") or ""),
        "rule_class": rule_class,
        "stage": str(rule.get("stage") or Stage.GENERAL),
        "risk_source": risk_source,
        "source_weight": source_weight,
        "consequence": str(rule.get("consequence") or Consequence.BREACH),
        # 强制性条目的严重度不由模型决定：标准库里写的是什么就是什么。
        # 否则模型一句「这里影响不大」就能把「可能无效」降成低危。
        "severity": str(rule.get("severity_if_missing") or severity) if rule_class == RuleClass.MANDATORY else severity,
        "legal_basis": str(rule.get("legal_basis") or ""),
        "verdict": verdict,
        "kind": FindingKind.RISK,
        "quote": str(item.get("quote") or "").strip(),
        "title": (str(item.get("title") or "") or rule_key)[:200],
        "reason": str(item.get("reason") or ""),
        "impact": str(item.get("impact") or ""),
        "suggestion_original": str(item.get("suggestion_original") or "").strip(),
        "suggestion_replacement": replacement,
        "suggestion_note": note,
        "delivery": delivery,
        "direction": direction,
        "in_top": False,
    }
