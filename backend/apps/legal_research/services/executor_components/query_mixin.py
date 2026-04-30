"""查询构建：关键词提取、同义词扩展、LLM 变体生成。"""

from __future__ import annotations

import json
import logging
import re
from typing import Any

from apps.core.interfaces import ServiceLocator

logger = logging.getLogger(__name__)


class ExecutorQueryMixin:
    LEGAL_SYNONYM_GROUPS: tuple[tuple[str, ...], ...] = (
        ("买卖合同纠纷", "买卖合同", "货物买卖纠纷"),
        ("借款合同纠纷", "借贷纠纷", "民间借贷纠纷"),
        ("违约责任", "违约", "不履行", "未履行", "拒绝履行"),
        ("违约金", "滞纳金", "罚金"),
        ("赔偿损失", "损失赔偿", "损害赔偿"),
        ("价差损失", "差价损失", "价差"),
        ("逾期交货", "迟延交货", "延迟交货", "未按时交货"),
        ("继续履行", "实际履行"),
        ("解除合同", "合同解除"),
    )
    ELEMENT_EXTRACTION_MAX_TOKENS = 300
    ELEMENT_EXTRACTION_TIMEOUT_SECONDS = 20
    QUERY_EXPANSION_TRIGGER_CANDIDATES = 80
    INTENT_QUERY_MAX = 5
    TITLE_PREFILTER_MIN_OVERLAP = 0.15
    QUERY_VARIANT_MAX = 2
    QUERY_VARIANT_MAX_TOKENS = 220
    QUERY_VARIANT_TIMEOUT_SECONDS = 25

    # ── 主构建器 ──────────────────────────────────────────────

    @classmethod
    def _build_search_keywords(cls, keyword: str, case_summary: str) -> list[str]:
        primary = cls._build_search_keyword(keyword, case_summary)
        intent_queries = cls._build_intent_search_keywords(keyword, case_summary)[: cls.INTENT_QUERY_MAX]
        fallback = cls._build_fallback_search_keyword(keyword, case_summary)
        scoring = cls._build_scoring_keyword(keyword, case_summary)
        summary = cls._build_summary_search_keyword(case_summary)

        candidates = [primary, *intent_queries, fallback, scoring, summary]
        deduped: list[str] = []
        seen: set[str] = set()
        for query in candidates:
            normalized = (query or "").strip()
            if not normalized:
                continue
            key = normalized.lower()
            if key in seen:
                continue
            seen.add(key)
            deduped.append(normalized)

        if deduped:
            return deduped

        fallback_tokens = cls._split_tokens(keyword) or cls._split_tokens(case_summary)  # type: ignore[attr-defined]
        return [" ".join(cls._expand_terms_with_synonyms(fallback_tokens, max_tokens=8)).strip()]

    @classmethod
    def _build_search_keyword(cls, keyword: str, case_summary: str) -> str:
        base_tokens = cls._split_tokens(keyword)  # type: ignore[attr-defined]
        if not base_tokens:
            base_tokens = cls._split_tokens(case_summary)  # type: ignore[attr-defined]
        merged = cls._expand_terms_with_synonyms(base_tokens, max_tokens=12)
        return " ".join(merged).strip()

    @classmethod
    def _build_fallback_search_keyword(cls, keyword: str, case_summary: str) -> str:
        fallback_tokens = cls._split_tokens(keyword)  # type: ignore[attr-defined]
        filtered = [token for token in fallback_tokens if not cls._is_location_or_court_token(token)]  # type: ignore[attr-defined]
        summary_terms = cls._extract_summary_terms(case_summary)  # type: ignore[attr-defined]
        merged = cls._expand_terms_with_synonyms([*filtered, *summary_terms], max_tokens=12)
        return " ".join(merged).strip()

    @classmethod
    def _build_scoring_keyword(cls, keyword: str, case_summary: str) -> str:
        base_tokens = cls._split_tokens(keyword)  # type: ignore[attr-defined]
        filtered = [token for token in base_tokens if not cls._is_location_or_court_token(token)]  # type: ignore[attr-defined]
        summary_terms = cls._extract_summary_terms(case_summary)  # type: ignore[attr-defined]
        merged = cls._expand_terms_with_synonyms([*filtered, *summary_terms], max_tokens=10)
        if not merged:
            merged = cls._expand_terms_with_synonyms([*base_tokens, *summary_terms], max_tokens=10)
        return " ".join(merged).strip()

    @classmethod
    def _build_summary_search_keyword(cls, case_summary: str) -> str:
        summary_terms = cls._expand_terms_with_synonyms(cls._extract_summary_terms(case_summary), max_tokens=8)  # type: ignore[attr-defined]
        return " ".join(summary_terms[:6]).strip()

    @classmethod
    def _build_feedback_search_keyword(cls, keyword: str, case_summary: str, feedback_terms: list[str]) -> str:
        keyword_tokens = cls._split_tokens(keyword)  # type: ignore[attr-defined]
        keyword_tokens = [token for token in keyword_tokens if not cls._is_location_or_court_token(token)]  # type: ignore[attr-defined]
        summary_terms = cls._extract_summary_terms(case_summary)  # type: ignore[attr-defined]
        merged = cls._expand_terms_with_synonyms([*keyword_tokens, *summary_terms, *feedback_terms], max_tokens=12)
        return " ".join(merged).strip()

    @classmethod
    def _build_intent_search_keywords(cls, keyword: str, case_summary: str) -> list[str]:
        context = f"{keyword} {case_summary}".strip()
        if not context:
            return []

        intent_slots = cls._extract_intent_slots_with_confidence(context)  # type: ignore[attr-defined]
        relation_terms = intent_slots["relation_high"]
        breach_terms = intent_slots["breach_high"]
        damage_terms = intent_slots["damage_high"]
        remedy_terms = intent_slots["remedy_high"]
        relation_low_terms = intent_slots["relation_low"]
        breach_low_terms = intent_slots["breach_low"]
        damage_low_terms = intent_slots["damage_low"]
        remedy_low_terms = intent_slots["remedy_low"]
        low_conf_limit = max(1, int(intent_slots["low_conf_limit"]))

        keyword_terms = [token for token in cls._split_tokens(keyword) if not cls._is_location_or_court_token(token)]  # type: ignore[attr-defined]
        summary_terms = cls._extract_summary_terms(case_summary)  # type: ignore[attr-defined]
        summary_relation_terms = [term for term in summary_terms if cls._looks_like_relation_term(term)]  # type: ignore[attr-defined]

        relation_seed = relation_terms or summary_relation_terms[:2] or keyword_terms[:2]
        query_parts: list[list[str]] = []
        if relation_seed and breach_terms and damage_terms:
            query_parts.append([*relation_seed[:2], *breach_terms[:2], *damage_terms[:2]])
        if relation_seed and damage_terms:
            query_parts.append([*relation_seed[:2], *damage_terms[:2], *remedy_terms[:1], *summary_terms[:2]])
        if breach_terms and damage_terms:
            query_parts.append([*breach_terms[:2], *damage_terms[:2], *summary_terms[:2]])
        if relation_seed and remedy_terms:
            query_parts.append([*relation_seed[:2], *remedy_terms[:2], *summary_terms[:2]])
        low_conf_pool = cls._dedupe_tokens(  # type: ignore[attr-defined]
            [*relation_low_terms, *breach_low_terms, *damage_low_terms, *remedy_low_terms],
            max_tokens=max(2, low_conf_limit * 2),
        )
        if low_conf_pool:
            query_parts.append([*keyword_terms[:2], *low_conf_pool[:low_conf_limit], *summary_terms[:2]])
        elif keyword_terms and summary_terms:
            query_parts.append([*keyword_terms[:3], *summary_terms[:3]])
        intent_pool = cls._dedupe_tokens(  # type: ignore[attr-defined]
            [*relation_terms, *breach_terms, *damage_terms, *remedy_terms, *summary_terms], max_tokens=8
        )
        if intent_pool:
            query_parts.append(intent_pool[:6])

        queries: list[str] = []
        seen: set[str] = set()
        for parts in query_parts:
            merged = cls._expand_terms_with_synonyms([part for part in parts if part], max_tokens=12)
            query = " ".join(merged).strip()
            if not query:
                continue
            key = query.lower()
            if key in seen:
                continue
            seen.add(key)
            queries.append(query)
            if len(queries) >= cls.INTENT_QUERY_MAX:
                break
        return queries

    @classmethod
    def _merge_query_candidates(
        cls, base_queries: list[str], extra_queries: list[str], *, max_queries: int = 14
    ) -> list[str]:
        merged: list[str] = []
        seen: set[str] = set()
        for query in [*base_queries, *extra_queries]:
            normalized = re.sub(r"\s+", " ", (query or "")).strip()
            if not normalized:
                continue
            key = normalized.lower()
            if key in seen:
                continue
            seen.add(key)
            merged.append(normalized)
            if len(merged) >= max(1, max_queries):
                break
        return merged

    # ── LLM 变体生成 ─────────────────────────────────────────

    @classmethod
    def _generate_llm_query_variants(
        cls,
        *,
        keyword: str,
        case_summary: str,
        model: str | None,
        max_variants: int,
    ) -> list[str]:
        limit = max(0, int(max_variants))
        if limit <= 0:
            return []

        context = re.sub(r"\s+", " ", f"{keyword} {case_summary}").strip()
        if len(context) < 6:
            return []

        try:
            llm = ServiceLocator.get_llm_service()
        except Exception:
            return []

        prompt = (
            "你是法律检索式改写器。请只输出JSON对象，不要额外文本。\n"
            "格式:\n"
            "{\n"
            '  "queries": ["改写检索式1", "改写检索式2"]\n'
            "}\n"
            "规则:\n"
            "1) 只改写检索词，不改变法律关系与争议核心。\n"
            "2) 每条检索式保持2-8个词，词之间用空格分隔。\n"
            "3) 避免地名、法院名等强定位词。\n"
            f"4) 最多返回 {limit} 条。\n\n"
            f"原始关键词: {keyword}\n"
            f"案情简述: {case_summary}\n"
        )
        try:
            response = llm.chat(
                messages=[
                    {"role": "system", "content": "你是法律检索式改写器，只输出JSON。"},
                    {"role": "user", "content": prompt},
                ],
                model=(model or None),
                fallback=True,
                temperature=0.1,
                max_tokens=cls.QUERY_VARIANT_MAX_TOKENS,
                timeout_seconds=cls.QUERY_VARIANT_TIMEOUT_SECONDS,
            )
        except Exception as exc:
            logger.info("LLM检索式改写失败，跳过改写阶段", extra={"error": str(exc)})
            return []

        content = str(getattr(response, "content", "") or "").strip()
        if not content:
            return []
        return cls._parse_query_variants(content=content, max_variants=limit)

    @classmethod
    def _parse_query_variants(cls, *, content: str, max_variants: int) -> list[str]:
        payload: Any = None
        raw = (content or "").strip()
        if not raw:
            return []
        try:
            payload = json.loads(raw)
        except Exception:
            match = re.search(r"\{.*\}", raw, flags=re.S)
            if match:
                try:
                    payload = json.loads(match.group(0))
                except Exception:
                    payload = None

        candidates: list[str] = []
        if isinstance(payload, dict):
            values = payload.get("queries", [])
            if isinstance(values, list):
                candidates = [str(item or "") for item in values]
            elif isinstance(values, str):
                candidates = [values]

        if not candidates:
            for part in re.split(r"[\n\r]+|[;；]+", raw):
                value = re.sub(r"^[\-\*\d\.\)\s]+", "", part or "").strip()
                if not value:
                    continue
                candidates.append(value)

        out: list[str] = []
        seen: set[str] = set()
        for candidate in candidates:
            tokens = [token for token in cls._split_tokens(candidate) if not cls._is_location_or_court_token(token)]  # type: ignore[attr-defined]
            if not tokens:
                continue
            query = " ".join(cls._expand_terms_with_synonyms(tokens, max_tokens=12)).strip()
            if not query:
                continue
            key = query.lower()
            if key in seen:
                continue
            seen.add(key)
            out.append(query)
            if len(out) >= max(1, max_variants):
                break
        return out

    # ── 法律要素提取 ─────────────────────────────────────────

    @classmethod
    def _extract_legal_elements(
        cls,
        *,
        case_summary: str,
        model: str | None = None,
        timeout_seconds: int = 20,
    ) -> dict[str, Any]:
        if not case_summary or len(case_summary.strip()) < 10:
            return {}
        try:
            llm = ServiceLocator.get_llm_service()
        except Exception:
            return {}

        prompt = (
            "你是法律检索要素提取器。从案情简述中提取关键法律要素，只输出JSON。\n"
            "{\n"
            '  "cause_of_action": "案由（如：买卖合同纠纷、民间借贷纠纷）",\n'
            '  "legal_relation": "法律关系（如：买卖合同、借款合同）",\n'
            '  "dispute_focus": ["争议焦点1", "争议焦点2"],\n'
            '  "damage_type": ["损失类型1", "损失类型2"],\n'
            '  "key_facts": ["关键事实1", "关键事实2"]\n'
            "}\n"
            "规则：每个字段2-6个字，dispute_focus和damage_type各不超过3项，key_facts不超过3项。\n"
            "若无法判断某字段，留空字符串或空数组。\n\n"
            f"案情简述：{case_summary[:1500]}\n"
        )
        try:
            response = llm.chat(
                messages=[
                    {"role": "system", "content": "你是法律检索要素提取器，只输出JSON。"},
                    {"role": "user", "content": prompt},
                ],
                model=(model or None),
                fallback=True,
                temperature=0.0,
                max_tokens=cls.ELEMENT_EXTRACTION_MAX_TOKENS,
                timeout_seconds=timeout_seconds,
            )
        except Exception as exc:
            logger.info("法律要素提取失败: %s", exc)
            return {}

        content = str(getattr(response, "content", "") or "").strip()
        if not content:
            return {}
        try:
            parsed = json.loads(content)
            if isinstance(parsed, dict):
                return parsed
        except json.JSONDecodeError:
            match = re.search(r"\{.*\}", content, flags=re.S)
            if match:
                try:
                    parsed = json.loads(match.group(0))
                    if isinstance(parsed, dict):
                        return parsed
                except json.JSONDecodeError:
                    pass
        return {}

    @classmethod
    def _build_element_based_queries(cls, elements: dict[str, Any]) -> list[str]:
        if not elements:
            return []
        cause = str(elements.get("cause_of_action", "") or "").strip()
        relation = str(elements.get("legal_relation", "") or "").strip()
        disputes = [str(d).strip() for d in (elements.get("dispute_focus") or []) if str(d).strip()]
        damages = [str(d).strip() for d in (elements.get("damage_type") or []) if str(d).strip()]
        facts = [str(f).strip() for f in (elements.get("key_facts") or []) if str(f).strip()]

        queries: list[str] = []
        if cause and disputes:
            queries.append(f"{cause} {' '.join(disputes[:2])}")
        if relation and damages:
            queries.append(f"{relation} {' '.join(damages[:2])}")
        if cause and facts:
            queries.append(f"{cause} {' '.join(facts[:2])}")
        all_terms = [t for t in [cause, relation, *disputes[:1], *damages[:1]] if t]
        if len(all_terms) >= 2:
            queries.append(" ".join(all_terms[:5]))
        return queries

    # ── 同义词扩展 ───────────────────────────────────────────

    @classmethod
    def _expand_terms_with_synonyms(cls, tokens: list[str], *, max_tokens: int) -> list[str]:
        if not tokens:
            return []

        out: list[str] = []
        seen: set[str] = set()
        for raw in tokens:
            token = (raw or "").strip()
            if not token:
                continue
            key = token.lower()
            if key not in seen:
                seen.add(key)
                out.append(token)
                if len(out) >= max_tokens:
                    break

            group = cls._match_synonym_group(token)
            if not group:
                continue
            canonical = group[0]
            canonical_key = canonical.lower()
            if canonical_key not in seen:
                seen.add(canonical_key)
                out.append(canonical)
                if len(out) >= max_tokens:
                    break
            for alt in group[1:]:
                alt_key = alt.lower()
                if alt_key in seen:
                    continue
                seen.add(alt_key)
                out.append(alt)
                if len(out) >= max_tokens:
                    break
            if len(out) >= max_tokens:
                break
        return out

    @classmethod
    def _match_synonym_group(cls, token: str) -> tuple[str, ...] | None:
        value = (token or "").strip()
        if not value:
            return None
        for group in cls.LEGAL_SYNONYM_GROUPS:
            if any(value == item for item in group):
                return group
        for group in cls.LEGAL_SYNONYM_GROUPS:
            if any(len(item) >= 2 and (item in value or value in item) for item in group):
                return group
        return None

    # ── 标题预筛 ─────────────────────────────────────────────

    @classmethod
    def _title_prefilter(cls, *, keyword: str, case_summary: str, title_hint: str, min_overlap: float) -> bool:
        if not title_hint or not title_hint.strip():
            return True
        query_tokens = cls._split_tokens(f"{keyword} {case_summary}")  # type: ignore[attr-defined]
        if not query_tokens:
            return True
        title_lower = title_hint.lower()
        matched = sum(1 for t in query_tokens if t.lower() in title_lower)
        overlap = matched / len(query_tokens)
        return overlap >= min_overlap
