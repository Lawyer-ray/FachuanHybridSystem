"""检索结果的排序与硬过滤：从 ``capability/service.py`` 拆出的纯函数。

两块判据都在这里：一是「这条命中该不该出现」的硬过滤（案由 / 法院层级 / 法院范围 /
年份区间），二是「留下的怎么排」的意图画像加权（``INTENT_PROFILE_WEIGHTS`` 决定四类
子分权重，同法院 / 有说理 / 有主文各有加成，同案号同标题还会被去重惩罚）。

原来这些是 ``LegalResearchCapabilityService`` 的 ``@classmethod``；下沉成模块级
函数后不持有实例或类状态，权重表与法院层级/省份前缀表也随之搬到模块级常量。

依赖方向单向：``service.py``（以及 ``trace_metrics`` 的 ``_normalize_text``）import
本模块；本模块不反向 import ``service.py``。原模块按原路径 re-export 本模块全部符号。
"""

from __future__ import annotations

import re
from collections import Counter
from typing import Any

from apps.legal_research.schemas.legal_research_schemas import AgentSearchRequestV1, RetrievalHitV1

HARD_CONFLICT_NEEDLES: tuple[str, ...] = (
    "主体",
    "身份",
    "当事人关系",
    "法律关系",
    "合同类型",
    "交易对象",
    "违约方式",
    "违约行为",
    "损失类型",
    "损失原因",
    "请求权基础",
    "法律后果",
    "交易结构",
)

INTENT_PROFILE_WEIGHTS: dict[str, dict[str, float]] = {
    "similar_case": {
        "base": 0.42,
        "facts": 0.23,
        "legal": 0.18,
        "dispute": 0.12,
        "damage": 0.05,
        "same_court_bonus": 0.0,
        "reasoning_bonus": 0.0,
        "holdings_bonus": 0.0,
    },
    "same_court_precedent": {
        "base": 0.32,
        "facts": 0.16,
        "legal": 0.24,
        "dispute": 0.09,
        "damage": 0.04,
        "same_court_bonus": 0.11,
        "reasoning_bonus": 0.03,
        "holdings_bonus": 0.01,
    },
}

COURT_LEVEL_KEYWORDS: tuple[tuple[str, str], ...] = (
    ("最高人民法院", "supreme"),
    ("高级人民法院", "high"),
    ("中级人民法院", "middle"),
    ("知识产权法院", "specialized"),
    ("互联网法院", "specialized"),
    ("海事法院", "specialized"),
    ("铁路运输法院", "specialized"),
    ("人民法院", "basic"),
)

REGION_CODE_PREFIX: dict[str, str] = {
    "11": "北京",
    "12": "天津",
    "13": "河北",
    "14": "山西",
    "15": "内蒙古",
    "21": "辽宁",
    "22": "吉林",
    "23": "黑龙江",
    "31": "上海",
    "32": "江苏",
    "33": "浙江",
    "34": "安徽",
    "35": "福建",
    "36": "江西",
    "37": "山东",
    "41": "河南",
    "42": "湖北",
    "43": "湖南",
    "44": "广东",
    "45": "广西",
    "46": "海南",
    "50": "重庆",
    "51": "四川",
    "52": "贵州",
    "53": "云南",
    "54": "西藏",
    "61": "陕西",
    "62": "甘肃",
    "63": "青海",
    "64": "宁夏",
    "65": "新疆",
}


def _normalize_text(value: str) -> str:  # pragma: no cover
    return re.sub(r"\s+", "", str(value or "")).lower()


def _extract_year(value: str) -> int | None:  # pragma: no cover
    match = re.search(r"(19|20)\d{2}", str(value or ""))
    if not match:
        return None
    return int(match.group(0))


def _apply_intent_profile(  # pragma: no cover
    *, hits: list[RetrievalHitV1], payload: AgentSearchRequestV1
) -> list[RetrievalHitV1]:
    if len(hits) <= 1:
        return hits
    intent = str(payload.intent or "similar_case")
    profile = INTENT_PROFILE_WEIGHTS.get(intent, INTENT_PROFILE_WEIGHTS["similar_case"])
    target_court = _normalize_text(str(payload.court_scope.court_name or ""))
    signatures = [
        _build_result_signature(
            court=hit.court,
            judgment_date=hit.judgment_date,
            title=hit.title,
        )
        for hit in hits
    ]
    signature_counts = Counter(signatures)

    scored: list[tuple[float, float, RetrievalHitV1]] = []
    for hit, signature in zip(hits, signatures, strict=False):
        same_court = bool(target_court and _normalize_text(hit.court) == target_court)
        has_reasoning = bool(str(hit.snippets.reasoning or "").strip())
        has_holdings = bool(str(hit.snippets.holdings or "").strip())
        hard_conflict = any(any(needle in conflict for needle in HARD_CONFLICT_NEEDLES) for conflict in hit.conflicts)

        intent_score = (
            profile["base"] * float(hit.score)
            + profile["facts"] * float(hit.subscores.facts_match)
            + profile["legal"] * float(hit.subscores.legal_relation_match)
            + profile["dispute"] * float(hit.subscores.dispute_match)
            + profile["damage"] * float(hit.subscores.damage_match)
        )
        if same_court:
            intent_score += profile.get("same_court_bonus", 0.0)
        if has_reasoning:
            intent_score += profile.get("reasoning_bonus", 0.0)
        if has_holdings:
            intent_score += profile.get("holdings_bonus", 0.0)
        if hard_conflict:
            intent_score = min(intent_score, 0.62)

        diversity_penalty = min(0.12, 0.04 * max(0, signature_counts[signature] - 1))
        ranked_score = max(0.0, min(1.0, intent_score - diversity_penalty))
        scored.append((ranked_score, float(hit.score), hit))

    scored.sort(key=lambda item: (item[0], item[1]), reverse=True)
    return [item[2] for item in scored]


def _build_result_signature(*, court: str, judgment_date: str, title: str) -> str:  # pragma: no cover
    year = _extract_year(judgment_date or "")
    normalized_court = _normalize_text(court)
    normalized_title = _normalize_text(title)[:24]
    return f"{normalized_court}:{year or 0}:{normalized_title}"


def _apply_hard_filters(*, results: list[Any], payload: AgentSearchRequestV1) -> list[Any]:  # pragma: no cover
    if not results:
        return []
    filtered = results
    filtered = [item for item in filtered if _match_cause_type(item=item, cause_type=payload.cause_type)]
    filtered = [item for item in filtered if _match_court_scope(item=item, payload=payload)]
    filtered = [item for item in filtered if _match_year_range(item=item, payload=payload)]
    return filtered


def _match_cause_type(*, item: Any, cause_type: str) -> bool:  # pragma: no cover
    normalized_cause = _normalize_text(cause_type)
    if not normalized_cause:
        return True
    haystack = _normalize_text(f"{getattr(item, 'title', '')} {getattr(item, 'case_digest', '')}")
    return normalized_cause in haystack


def _match_court_scope(*, item: Any, payload: AgentSearchRequestV1) -> bool:  # pragma: no cover
    mode = str(payload.court_scope.mode or "same_court").strip().lower()
    court_text = str(getattr(item, "court_text", "") or "")
    normalized_item_court = _normalize_text(court_text)
    if not normalized_item_court:
        return False

    target_court = str(payload.court_scope.court_name or "").strip()
    normalized_target_court = _normalize_text(target_court)
    if mode == "same_court":
        if not normalized_target_court:
            return True
        return normalized_item_court == normalized_target_court

    if mode == "same_level":
        if not normalized_target_court:
            return True
        return _extract_court_level(court_text) == _extract_court_level(target_court)

    if mode == "region":
        region_keywords = _build_region_keywords(
            court_name=target_court,
            region_code=str(payload.court_scope.region_code or ""),
        )
        if not region_keywords:
            return True
        return any(
            _normalize_text(keyword) in normalized_item_court for keyword in region_keywords if str(keyword).strip()
        )

    return True


def _match_year_range(*, item: Any, payload: AgentSearchRequestV1) -> bool:  # pragma: no cover
    from_year = payload.year_range.from_year
    to_year = payload.year_range.to
    if from_year is None and to_year is None:
        return True
    year = _extract_year(str(getattr(item, "judgment_date", "") or ""))
    if year is None:
        return False
    if from_year is not None and year < int(from_year):
        return False
    if to_year is not None and year > int(to_year):
        return False
    return True


def _extract_court_level(text: str) -> str:  # pragma: no cover
    normalized = _normalize_text(text)
    for keyword, level in COURT_LEVEL_KEYWORDS:
        if _normalize_text(keyword) in normalized:
            return level
    return "unknown"


def _build_region_keywords(*, court_name: str, region_code: str) -> list[str]:  # pragma: no cover
    keywords: list[str] = []
    cleaned_name = str(court_name or "").strip()
    if cleaned_name:
        keywords.append(cleaned_name)
    code = re.sub(r"\D+", "", str(region_code or ""))
    if len(code) >= 2:
        province = REGION_CODE_PREFIX.get(code[:2])
        if province:
            keywords.append(province)
    seen: set[str] = set()
    deduped: list[str] = []
    for keyword in keywords:
        marker = _normalize_text(keyword)
        if not marker or marker in seen:
            continue
        seen.add(marker)
        deduped.append(keyword)
    return deduped
