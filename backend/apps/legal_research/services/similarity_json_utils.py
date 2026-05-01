"""案例相似度 - JSON 提取 / 修复 / 元数据结构化."""

from __future__ import annotations

import json
import logging
import re
from typing import Any

from .similarity_scorers import coerce_score

logger = logging.getLogger(__name__)

HARD_CONFLICT_NEEDLES = (
    "主体", "身份", "当事人关系", "法律关系", "合同类型", "交易对象",
    "违约方式", "违约行为", "损失类型", "损失原因", "请求权基础", "法律后果", "交易结构",
)
MIN_EVIDENCE_SPAN_CHARS = 4


def extract_json(text: str) -> dict[str, object] | None:
    if not text:
        return None

    candidate = text.strip()
    if candidate.startswith("```"):
        candidate = re.sub(r"^```[a-zA-Z0-9_-]*", "", candidate).strip()
        candidate = candidate.removesuffix("```").strip()

    try:
        data = json.loads(candidate)
        if isinstance(data, dict):
            return data
    except json.JSONDecodeError:
        pass

    match = re.search(r"\{.*\}", text, flags=re.S)
    if not match:
        return None

    try:
        data = json.loads(match.group(0))
        if isinstance(data, dict):
            return data
    except json.JSONDecodeError:
        logger.warning("相似度JSON解析失败", extra={"preview": text[:200]})

    return None


def normalize_text_list(value: object) -> list[str]:
    if isinstance(value, list):
        return [str(item).strip() for item in value if str(item).strip()]
    if isinstance(value, str) and value.strip():
        return [value.strip()]
    return []


def normalize_match_text(text: str) -> str:
    if not text:
        return ""
    normalized = re.sub(r"\s+", "", text)
    normalized = re.sub(r"[，。；：、“”‘’\"'（）()【】\[\]《》<>、,.!?！？:;·\-]", "", normalized)
    return normalized.lower()


def evidence_span_hit_count(*, evidence_spans: list[str], context_text: str) -> tuple[int, int]:
    normalized_context = normalize_match_text(context_text)
    if not normalized_context:
        return 0, 0

    hits = 0
    total = 0
    for span in evidence_spans:
        normalized_span = normalize_match_text(span)
        if len(normalized_span) < MIN_EVIDENCE_SPAN_CHARS:
            continue
        total += 1
        if normalized_span in normalized_context:
            hits += 1
    return hits, total


def apply_structured_adjustments(
    *,
    score: float,
    payload: dict[str, object],
    context_text: str = "",
) -> float:
    adjusted = max(0.0, min(1.0, float(score)))

    decision = str(payload.get("decision", "") or "").strip().lower()
    if decision in {"reject", "不相似"}:
        adjusted = min(adjusted, 0.45)
    elif decision in {"low", "低"}:
        adjusted = min(adjusted, 0.6)
    elif decision in {"medium", "中"}:
        adjusted = min(adjusted, 0.85)

    component_scores = [
        coerce_score(payload.get("facts_match", 1.0)),
        coerce_score(payload.get("legal_relation_match", 1.0)),
        coerce_score(payload.get("dispute_match", 1.0)),
        coerce_score(payload.get("damage_match", 1.0)),
    ]
    min_component = min(component_scores)
    if min_component < 0.2:
        adjusted = min(adjusted, 0.55)
    elif min_component < 0.35:
        adjusted = min(adjusted, 0.68)

    conflicts = normalize_text_list(payload.get("key_conflicts"))
    if conflicts and any(any(needle in conflict for needle in HARD_CONFLICT_NEEDLES) for conflict in conflicts):
        adjusted = min(adjusted, 0.62)

    evidence_spans = normalize_text_list(payload.get("evidence_spans"))
    if evidence_spans and len(evidence_spans) < 2:
        adjusted = min(adjusted, 0.82)
    if evidence_spans:
        hit_count, valid_count = evidence_span_hit_count(
            evidence_spans=evidence_spans,
            context_text=context_text,
        )
        if valid_count >= 2:
            hit_ratio = hit_count / valid_count
            if hit_ratio < 0.5:
                adjusted = min(adjusted, 0.72)
            elif hit_ratio < 1.0:
                adjusted = min(adjusted, 0.82)
        elif valid_count == 1 and hit_count == 0:
            adjusted = min(adjusted, 0.78)

    return max(0.0, min(1.0, adjusted))


def extract_structured_metadata(
    *,
    payload: dict[str, object],
    adjusted_score: float,
    context_text: str = "",
) -> dict[str, Any]:
    metadata: dict[str, Any] = {"score_adjusted": round(max(0.0, min(1.0, adjusted_score)), 4)}
    raw_score = coerce_score(payload.get("score", 0.0))
    metadata["score_raw"] = round(max(0.0, min(1.0, raw_score)), 4)

    decision = str(payload.get("decision", "") or "").strip().lower()
    if decision:
        metadata["decision"] = decision

    for field_name in ("facts_match", "legal_relation_match", "dispute_match", "damage_match"):
        if field_name not in payload:
            continue
        value = coerce_score(payload.get(field_name, 0.0))
        metadata[field_name] = round(max(0.0, min(1.0, value)), 4)

    conflicts = [item[:120] for item in normalize_text_list(payload.get("key_conflicts"))[:6]]
    if conflicts:
        metadata["key_conflicts"] = conflicts

    evidence_spans = [item[:160] for item in normalize_text_list(payload.get("evidence_spans"))[:6]]
    if evidence_spans:
        metadata["evidence_spans"] = evidence_spans
        hit_count, valid_count = evidence_span_hit_count(
            evidence_spans=evidence_spans,
            context_text=context_text,
        )
        if valid_count > 0:
            metadata["evidence_hits"] = hit_count
            metadata["evidence_total"] = valid_count
            metadata["evidence_hit_ratio"] = round(hit_count / valid_count, 4)

    return metadata


def extract_transaction_tags(text: str) -> list[str]:
    normalized = (text or "").strip().lower()
    if not normalized:
        return []

    tag_rules: tuple[tuple[str, tuple[str, ...]], ...] = (
        ("转卖", ("转卖", "转售", "另行出售", "卖给他人")),
        ("交货迟延", ("未按时", "逾期交货", "迟延交货", "延迟交货", "未交货", "不交货")),
        ("质量瑕疵", ("质量", "瑕疵", "不合格")),
        ("价差争议", ("价格", "价差", "高价另购", "市场价格", "固定价格")),
        ("付款迟延", ("逾期付款", "迟延付款", "未付款", "不付款", "拖欠")),
    )
    tags: list[str] = []
    for label, needles in tag_rules:
        if any(needle in normalized for needle in needles):
            tags.append(label)
    return tags
