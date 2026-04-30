"""NLP 意图抽取：从案件摘要提取法律要素（关系/违约/损害/救济）。"""

from __future__ import annotations

import re
from typing import TypedDict

from apps.core.interfaces import ServiceLocator


class _IntentSlots(TypedDict):
    relation_high: list[str]
    relation_low: list[str]
    breach_high: list[str]
    breach_low: list[str]
    damage_high: list[str]
    damage_low: list[str]
    remedy_high: list[str]
    remedy_low: list[str]
    low_conf_limit: int


class _IntentRuleOverrides(TypedDict):
    relation_regex_extra: list[str]
    relation_term_extra: list[str]
    breach_hint_extra: list[str]
    damage_hint_extra: list[str]
    remedy_hint_extra: list[str]
    low_conf_limit: int


class ExecutorIntentMixin:
    INTENT_RELATION_REGEX: tuple[str, ...] = (
        r"[一-鿿A-Za-z0-9]{2,20}合同纠纷",
        r"[一-鿿A-Za-z0-9]{2,20}纠纷",
        r"[一-鿿A-Za-z0-9]{2,20}侵权纠纷",
        r"[一-鿿A-Za-z0-9]{2,20}争议",
        r"[一-鿿A-Za-z0-9]{2,20}之诉",
    )
    INTENT_BREACH_HINTS: tuple[str, ...] = (
        "违约",
        "逾期",
        "迟延",
        "拒绝",
        "拒不",
        "未履行",
        "不履行",
        "转卖",
        "解除",
        "终止",
        "瑕疵",
        "不合格",
        "拖欠",
        "拒付",
        "未交货",
        "不交货",
        "未付款",
        "不付款",
    )
    INTENT_DAMAGE_HINTS: tuple[str, ...] = (
        "损失",
        "价差",
        "赔偿",
        "违约金",
        "利息",
        "货款",
        "停工",
        "停机",
        "停产",
        "损害",
        "费用",
    )
    INTENT_REMEDY_HINTS: tuple[str, ...] = (
        "请求",
        "主张",
        "要求",
        "承担",
        "赔偿",
        "支付",
        "返还",
        "退还",
        "继续履行",
        "解除合同",
        "代位清偿",
        "恢复原状",
    )
    INTENT_RULE_RELATION_REGEX_EXTRA_KEY = "LEGAL_RESEARCH_INTENT_RELATION_REGEX_EXTRA"
    INTENT_RULE_RELATION_TERM_EXTRA_KEY = "LEGAL_RESEARCH_INTENT_RELATION_TERM_EXTRA"
    INTENT_RULE_BREACH_HINT_EXTRA_KEY = "LEGAL_RESEARCH_INTENT_BREACH_HINT_EXTRA"
    INTENT_RULE_DAMAGE_HINT_EXTRA_KEY = "LEGAL_RESEARCH_INTENT_DAMAGE_HINT_EXTRA"
    INTENT_RULE_REMEDY_HINT_EXTRA_KEY = "LEGAL_RESEARCH_INTENT_REMEDY_HINT_EXTRA"
    INTENT_LOW_CONF_MAX_TERMS_KEY = "LEGAL_RESEARCH_INTENT_LOW_CONF_MAX_TERMS"

    # ── 意图抽取 ──────────────────────────────────────────────

    @classmethod
    def _extract_intent_slots(cls, text: str) -> tuple[list[str], list[str], list[str], list[str]]:
        slots = cls._extract_intent_slots_with_confidence(text)
        return (
            cls._dedupe_tokens([*slots["relation_high"], *slots["relation_low"]], max_tokens=8),
            cls._dedupe_tokens([*slots["breach_high"], *slots["breach_low"]], max_tokens=8),
            cls._dedupe_tokens([*slots["damage_high"], *slots["damage_low"]], max_tokens=8),
            cls._dedupe_tokens([*slots["remedy_high"], *slots["remedy_low"]], max_tokens=8),
        )

    @classmethod
    def _extract_intent_slots_with_confidence(cls, text: str) -> _IntentSlots:
        normalized = re.sub(r"\s+", " ", (text or "")).strip()
        if not normalized:
            return {
                "relation_high": [],
                "relation_low": [],
                "breach_high": [],
                "breach_low": [],
                "damage_high": [],
                "damage_low": [],
                "remedy_high": [],
                "remedy_low": [],
                "low_conf_limit": 2,
            }

        rule_overrides = cls._load_intent_rule_overrides()
        relation_mapping: tuple[tuple[tuple[str, ...], str], ...] = (
            (("买卖合同", "买卖"), "买卖合同纠纷"),
            (("借款", "借贷", "民间借贷"), "借款合同纠纷"),
            (("租赁", "房屋租赁"), "租赁合同纠纷"),
            (("承揽", "加工"), "承揽合同纠纷"),
            (("运输",), "运输合同纠纷"),
            (("服务合同", "委托"), "服务合同纠纷"),
            (("建设工程", "施工"), "建设工程合同纠纷"),
            (("劳动", "工伤"), "劳动争议"),
            (("股权转让", "股权"), "股权转让纠纷"),
        )
        breach_mapping: tuple[tuple[tuple[str, ...], str], ...] = (
            (("违约",), "违约责任"),
            (("未交货", "不交货", "拒绝交货", "延迟交货", "逾期交货"), "交货违约"),
            (("转卖", "另行出售", "卖给他人"), "转卖违约"),
            (("拒绝履行", "不履行", "未履行", "拒不履行"), "拒不履行"),
            (("解除合同", "单方解除"), "解除合同"),
            (("迟延付款", "逾期付款"), "付款违约"),
            (("质量问题", "质量不合格", "瑕疵"), "质量瑕疵"),
        )
        damage_mapping: tuple[tuple[tuple[str, ...], str], ...] = (
            (("价差",), "价差损失"),
            (("损失",), "损失赔偿"),
            (("违约金",), "违约金"),
            (("利息",), "利息损失"),
            (("停工",), "停工损失"),
            (("货款",), "货款损失"),
        )
        remedy_mapping: tuple[tuple[tuple[str, ...], str], ...] = (
            (("承担违约责任", "违约责任"), "承担违约责任"),
            (("赔偿",), "赔偿损失"),
            (("继续履行",), "继续履行"),
            (("返还", "退还"), "返还款项"),
            (("解除合同",), "解除合同"),
            (("代位清偿",), "代位清偿"),
        )

        semantic_tokens = cls._extract_summary_terms(normalized)

        relation_high = cls._collect_intent_terms(normalized, relation_mapping)
        relation_high.extend(
            cls._extract_relation_terms_dynamic(normalized, extra_regexes=rule_overrides["relation_regex_extra"])
        )
        relation_high.extend([cls._normalize_relation_term(term) for term in rule_overrides["relation_term_extra"]])
        relation_low = [token for token in semantic_tokens if cls._looks_like_relation_term(token)]

        breach_hints = cls._merge_hint_overrides(cls.INTENT_BREACH_HINTS, rule_overrides["breach_hint_extra"])
        damage_hints = cls._merge_hint_overrides(cls.INTENT_DAMAGE_HINTS, rule_overrides["damage_hint_extra"])
        remedy_hints = cls._merge_hint_overrides(cls.INTENT_REMEDY_HINTS, rule_overrides["remedy_hint_extra"])

        breach_high = cls._collect_intent_terms(normalized, breach_mapping)
        dyn_breach_high, dyn_breach_low = cls._extract_slot_terms_by_hints_with_confidence(
            normalized, hints=breach_hints
        )
        breach_high.extend(dyn_breach_high)
        breach_low = [
            *dyn_breach_low,
            *[token for token in semantic_tokens if cls._contains_any_hint(token, breach_hints)],
        ]

        damage_high = cls._collect_intent_terms(normalized, damage_mapping)
        dyn_damage_high, dyn_damage_low = cls._extract_slot_terms_by_hints_with_confidence(
            normalized, hints=damage_hints
        )
        damage_high.extend(dyn_damage_high)
        damage_low = [
            *dyn_damage_low,
            *[token for token in semantic_tokens if cls._contains_any_hint(token, damage_hints)],
        ]

        remedy_high = cls._collect_intent_terms(normalized, remedy_mapping)
        dyn_remedy_high, dyn_remedy_low = cls._extract_slot_terms_by_hints_with_confidence(
            normalized, hints=remedy_hints
        )
        remedy_high.extend(dyn_remedy_high)
        remedy_low = [
            *dyn_remedy_low,
            *[token for token in semantic_tokens if cls._contains_any_hint(token, remedy_hints)],
        ]

        relation_high_deduped = cls._dedupe_tokens(
            [cls._normalize_relation_term(term) for term in relation_high if term],
            max_tokens=8,
        )
        return {
            "relation_high": relation_high_deduped,
            "relation_low": cls._dedupe_tokens(
                [
                    cls._normalize_relation_term(term)
                    for term in relation_low
                    if term and cls._normalize_relation_term(term) not in relation_high_deduped
                ],
                max_tokens=8,
            ),
            "breach_high": cls._dedupe_tokens(breach_high, max_tokens=8),
            "breach_low": cls._dedupe_tokens(
                [term for term in breach_low if term and term not in breach_high], max_tokens=8
            ),
            "damage_high": cls._dedupe_tokens(damage_high, max_tokens=8),
            "damage_low": cls._dedupe_tokens(
                [term for term in damage_low if term and term not in damage_high], max_tokens=8
            ),
            "remedy_high": cls._dedupe_tokens(remedy_high, max_tokens=8),
            "remedy_low": cls._dedupe_tokens(
                [term for term in remedy_low if term and term not in remedy_high], max_tokens=8
            ),
            "low_conf_limit": rule_overrides["low_conf_limit"],
        }

    @classmethod
    def _collect_intent_terms(
        cls,
        text: str,
        mapping: tuple[tuple[tuple[str, ...], str], ...],
    ) -> list[str]:
        terms: list[str] = []
        for needles, canonical_term in mapping:
            if any(needle in text for needle in needles):
                terms.append(canonical_term)
        return cls._dedupe_tokens(terms, max_tokens=8)

    @classmethod
    def _extract_relation_terms_dynamic(
        cls,
        text: str,
        *,
        extra_regexes: list[str] | None = None,
    ) -> list[str]:
        compact = re.sub(r"\s+", "", text)
        if not compact:
            return []

        terms: list[str] = []
        patterns = [*cls.INTENT_RELATION_REGEX, *(extra_regexes or [])]
        for pattern in patterns:
            try:
                matched_items = re.findall(pattern, compact)
            except re.error:
                continue
            for matched in matched_items:
                if not matched:
                    continue
                terms.append(cls._normalize_relation_term(str(matched)))

        for matched in re.findall(r"[一-鿿A-Za-z0-9]{2,16}合同", compact):
            if not matched:
                continue
            terms.append(cls._normalize_relation_term(matched))

        return cls._dedupe_tokens([term for term in terms if term], max_tokens=8)

    @classmethod
    def _extract_slot_terms_by_hints_with_confidence(
        cls,
        text: str,
        *,
        hints: tuple[str, ...],
    ) -> tuple[list[str], list[str]]:
        if not hints:
            return [], []
        high_terms: list[str] = []
        low_terms: list[str] = []
        for clause in cls._split_intent_clauses(text):
            hint_hits = [hint for hint in hints if hint in clause]
            if not hint_hits:
                continue
            compact = cls._compact_clause_by_hints(clause, hints=hints, max_chars=16)
            if not compact:
                continue

            strong = (len(hint_hits) >= 2) or (len(compact) >= 7)
            if strong:
                high_terms.append(compact)
            else:
                low_terms.append(compact)
        return cls._dedupe_tokens(high_terms, max_tokens=8), cls._dedupe_tokens(low_terms, max_tokens=8)

    @staticmethod
    def _split_intent_clauses(text: str) -> list[str]:
        raw = re.split(r"[\n\r，,。；;：:！!？?]+", text or "")
        clauses: list[str] = []
        for part in raw:
            normalized = re.sub(r"\s+", "", part).strip()
            if len(normalized) < 2:
                continue
            clauses.append(normalized)
        return clauses

    @classmethod
    def _compact_clause_by_hints(cls, clause: str, *, hints: tuple[str, ...], max_chars: int) -> str:
        if not clause:
            return ""

        chosen_hint = ""
        chosen_index = len(clause) + 1
        for hint in hints:
            idx = clause.find(hint)
            if idx < 0:
                continue
            if idx < chosen_index:
                chosen_index = idx
                chosen_hint = hint

        if not chosen_hint:
            compact = clause
        else:
            left = max(0, chosen_index - 6)
            right = min(len(clause), chosen_index + len(chosen_hint) + 8)
            compact = clause[left:right]

        compact = re.sub(r"^(原告|被告|双方|当事人|买方|卖方|请求|主张|要求|因|由于|致使|导致)+", "", compact)
        compact = re.sub(r"(请求|主张|要求)$", "", compact)
        compact = compact.strip("，。；：、,.;: ")
        if len(compact) > max_chars:
            compact = compact[:max_chars]
        return compact

    @classmethod
    def _normalize_relation_term(cls, term: str) -> str:
        normalized = re.sub(r"\s+", "", term or "").strip("，。；：、,.;: ")
        if not normalized:
            return ""
        normalized = re.sub(r"(纠纷案|争议案|之诉案)$", lambda m: m.group(1)[:-1], normalized)
        if normalized in {"劳动", "劳动纠纷"}:
            return "劳动争议"
        if normalized.endswith("合同") and not normalized.endswith("合同纠纷"):
            return f"{normalized}纠纷"
        return normalized

    @staticmethod
    def _looks_like_relation_term(term: str) -> bool:
        value = (term or "").strip()
        if not value:
            return False
        if value.endswith("纠纷") or value.endswith("争议") or value.endswith("之诉"):
            return True
        return "合同" in value

    @staticmethod
    def _contains_any_hint(text: str, hints: tuple[str, ...]) -> bool:
        normalized = (text or "").strip()
        if not normalized:
            return False
        return any(hint in normalized for hint in hints)

    # ── 规则覆盖加载 ──────────────────────────────────────────

    @classmethod
    def _load_intent_rule_overrides(cls) -> _IntentRuleOverrides:
        try:
            config_service = ServiceLocator.get_system_config_service()
        except Exception:
            return {
                "relation_regex_extra": [],
                "relation_term_extra": [],
                "breach_hint_extra": [],
                "damage_hint_extra": [],
                "remedy_hint_extra": [],
                "low_conf_limit": 2,
            }

        return {
            "relation_regex_extra": cls._parse_rule_items(
                str(config_service.get_value(cls.INTENT_RULE_RELATION_REGEX_EXTRA_KEY, "") or ""),
                max_items=16,
                max_len=120,
            ),
            "relation_term_extra": cls._parse_rule_items(
                str(config_service.get_value(cls.INTENT_RULE_RELATION_TERM_EXTRA_KEY, "") or ""),
                max_items=16,
                max_len=40,
            ),
            "breach_hint_extra": cls._parse_rule_items(
                str(config_service.get_value(cls.INTENT_RULE_BREACH_HINT_EXTRA_KEY, "") or ""),
                max_items=24,
                max_len=20,
            ),
            "damage_hint_extra": cls._parse_rule_items(
                str(config_service.get_value(cls.INTENT_RULE_DAMAGE_HINT_EXTRA_KEY, "") or ""),
                max_items=24,
                max_len=20,
            ),
            "remedy_hint_extra": cls._parse_rule_items(
                str(config_service.get_value(cls.INTENT_RULE_REMEDY_HINT_EXTRA_KEY, "") or ""),
                max_items=24,
                max_len=20,
            ),
            "low_conf_limit": cls._parse_int_with_bounds(
                str(config_service.get_value(cls.INTENT_LOW_CONF_MAX_TERMS_KEY, "2") or ""),
                default=2,
                min_value=1,
                max_value=6,
            ),
        }

    @staticmethod
    def _parse_rule_items(raw: str, *, max_items: int, max_len: int) -> list[str]:
        if not raw:
            return []
        parts = re.split(r"[\n\r,，;；|]+", raw)
        out: list[str] = []
        seen: set[str] = set()
        for part in parts:
            token = re.sub(r"\s+", "", part or "").strip()
            if not token:
                continue
            token = token[:max_len]
            key = token.lower()
            if key in seen:
                continue
            seen.add(key)
            out.append(token)
            if len(out) >= max_items:
                break
        return out

    @staticmethod
    def _parse_int_with_bounds(raw: str, *, default: int, min_value: int, max_value: int) -> int:
        try:
            value = int((raw or "").strip())
        except (TypeError, ValueError):
            return default
        return max(min_value, min(max_value, value))

    @classmethod
    def _merge_hint_overrides(cls, defaults: tuple[str, ...], extras: list[str]) -> tuple[str, ...]:
        merged = cls._dedupe_tokens([*defaults, *extras], max_tokens=64)
        return tuple(merged)

    # ── 通用工具方法 ──────────────────────────────────────────

    @staticmethod
    def _split_tokens(text: str) -> list[str]:
        parts = re.split(r"[\s,，;；、]+", (text or "").strip())
        return [p for p in parts if p and len(p) >= 2]

    @staticmethod
    def _is_location_or_court_token(token: str) -> bool:
        value = (token or "").strip()
        if not value:
            return False
        if "法院" in value:
            return True
        if re.fullmatch(r"[一-鿿]{2,12}(省|市|区|县|镇|乡)", value):
            return True
        return False

    @classmethod
    def _extract_summary_terms(cls, case_summary: str) -> list[str]:
        text = (case_summary or "").strip()
        if not text:
            return []

        terms: list[str] = []
        relation_terms = cls._extract_relation_terms_dynamic(text)
        terms.extend(relation_terms[:4])

        for hints in (cls.INTENT_BREACH_HINTS, cls.INTENT_DAMAGE_HINTS, cls.INTENT_REMEDY_HINTS):
            high_terms, low_terms = cls._extract_slot_terms_by_hints_with_confidence(text, hints=hints)
            terms.extend(high_terms[:3])
            terms.extend(low_terms[:2])

        phrase_mapping = (
            ("买卖合同", "买卖合同纠纷"),
            ("违约", "违约责任"),
            ("价差", "价差损失"),
            ("损失", "损失赔偿"),
            ("转卖", "转卖"),
            ("市场价格", "市场价格"),
            ("固定价格", "固定价格"),
            ("继续履行", "继续履行"),
            ("代位清偿", "代位清偿"),
            ("解除合同", "解除合同"),
            ("不当得利", "不当得利纠纷"),
        )
        for needle, term in phrase_mapping:
            if needle in text:
                terms.append(term)

        extra_tokens = re.findall(r"[一-鿿A-Za-z0-9]{2,16}", text)
        stopwords = {
            "一个月后",
            "并且",
            "约定",
            "买方",
            "卖方",
            "货物",
            "按照",
            "如何",
            "此时",
            "要求",
            "承担",
            "相关",
            "以及",
            "责任",
            "应当",
            "法院",
            "本院",
            "原告",
            "被告",
            "案件",
            "争议焦点",
        }
        for token in extra_tokens:
            if token in stopwords:
                continue
            if token.isdigit():
                continue
            if re.fullmatch(r"[一二三四五六七八九十百千万第]+", token):
                continue
            if token.endswith("人民法院") or token.endswith("法院"):
                continue
            terms.append(token)

        return cls._dedupe_tokens(terms, max_tokens=12)

    @staticmethod
    def _dedupe_tokens(tokens: list[str], *, max_tokens: int) -> list[str]:
        out: list[str] = []
        seen: set[str] = set()
        for token in tokens:
            key = token.strip().lower()
            if not key or key in seen:
                continue
            seen.add(key)
            out.append(token.strip())
            if len(out) >= max_tokens:
                break
        return out
