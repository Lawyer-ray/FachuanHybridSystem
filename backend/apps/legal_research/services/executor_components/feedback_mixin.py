"""反馈学习：根据命中结果调整查询词权重，生成反馈查询。"""

from __future__ import annotations

import re
from typing import Any

from apps.legal_research.services.sources import CaseDetail


class ExecutorFeedbackMixin:
    FEEDBACK_QUERY_LIMIT = 2
    FEEDBACK_MIN_TERMS = 3
    FEEDBACK_MIN_SCORE_FLOOR = 0.68

    @staticmethod
    def _init_query_metric() -> dict[str, int]:
        return {"candidates": 0, "scanned": 0, "matched": 0, "skipped": 0}

    @classmethod
    def _apply_query_performance_feedback(
        cls,
        *,
        search_keyword: str,
        metric: dict[str, int],
        feedback_term_weights: dict[str, int],
    ) -> None:
        scanned = max(0, int(metric.get("scanned", 0)))
        matched = max(0, int(metric.get("matched", 0)))
        if scanned <= 0:
            return

        hit_rate = matched / max(1, scanned)
        keyword_tokens = [
            token for token in cls._split_tokens(search_keyword) if not cls._is_location_or_court_token(token)
        ]
        if not keyword_tokens:
            return

        if matched >= 1 and hit_rate >= 0.08:
            boost = 2 if hit_rate >= 0.25 else 1
            for token in keyword_tokens[:6]:
                feedback_term_weights[token] = feedback_term_weights.get(token, 0) + boost
            return

        if scanned >= 20 and matched == 0:
            for token in keyword_tokens[:6]:
                old = feedback_term_weights.get(token, 0)
                if old <= 0:
                    continue
                new_weight = max(0, old - 1)
                if new_weight <= 0:
                    feedback_term_weights.pop(token, None)
                else:
                    feedback_term_weights[token] = new_weight

    @classmethod
    def _build_query_stats_suffix(cls, *, query_stats: dict[str, dict[str, int]]) -> str:
        if not query_stats:
            return ""

        best_query = ""
        best_scanned = 0
        best_matched = 0
        best_rate = -1.0
        for query, stats in query_stats.items():
            scanned = max(0, int(stats.get("scanned", 0)))
            matched = max(0, int(stats.get("matched", 0)))
            if scanned <= 0:
                continue
            rate = matched / scanned
            better = (matched > best_matched) or (matched == best_matched and rate > best_rate)
            if better:
                best_query = query
                best_scanned = scanned
                best_matched = matched
                best_rate = rate

        if not best_query:
            return ""
        preview = re.sub(r"\s+", " ", best_query).strip()[:18]
        return f"（最佳检索式 {best_matched}/{best_scanned}: {preview}）"

    @staticmethod
    def _build_query_trace_payload(
        *,
        primary_queries: list[str],
        expansion_queries: list[str],
        feedback_queries: list[str],
        query_stats: dict[str, dict[str, int]],
    ) -> dict[str, Any]:
        return {
            "primary_queries": [str(query).strip() for query in primary_queries if str(query).strip()],
            "expansion_queries": [str(query).strip() for query in expansion_queries if str(query).strip()],
            "feedback_queries": [str(query).strip() for query in feedback_queries if str(query).strip()],
            "query_stats": query_stats,
        }

    @classmethod
    def _maybe_append_feedback_query(
        cls,
        *,
        search_keywords: list[str],
        search_query_set: set[str],
        feedback_term_weights: dict[str, int],
        keyword: str,
        case_summary: str,
        feedback_queries_added: int,
        feedback_query_limit: int,
        feedback_min_terms: int,
    ) -> tuple[int, str]:
        if feedback_queries_added >= max(0, feedback_query_limit):
            return feedback_queries_added, ""
        feedback_terms = cls._pick_feedback_terms(feedback_term_weights)
        if len(feedback_terms) < max(1, feedback_min_terms):
            return feedback_queries_added, ""

        query = cls._build_feedback_search_keyword(
            keyword=keyword, case_summary=case_summary, feedback_terms=feedback_terms
        )
        normalized = query.strip().lower()
        if not normalized or normalized in search_query_set:
            return feedback_queries_added, ""

        search_query_set.add(normalized)
        search_keywords.append(query)
        return feedback_queries_added + 1, query

    @classmethod
    def _pick_feedback_terms(cls, feedback_term_weights: dict[str, int]) -> list[str]:
        if not feedback_term_weights:
            return []
        sorted_terms = sorted(
            feedback_term_weights.items(),
            key=lambda item: (item[1], len(item[0])),
            reverse=True,
        )
        out: list[str] = []
        for term, _weight in sorted_terms:
            out.append(term)
            if len(out) >= 6:
                break
        return out

    @classmethod
    def _update_feedback_terms(
        cls,
        *,
        feedback_term_weights: dict[str, int],
        detail: CaseDetail,
        reason: str,
        similarity_score: float,
        min_similarity: float,
        feedback_min_score_floor: float,
        feedback_score_margin: float,
    ) -> bool:
        threshold = max(feedback_min_score_floor, min_similarity - feedback_score_margin)
        if similarity_score < threshold:
            return False

        text = f"{detail.title} {detail.case_digest} {reason}"
        tokens = re.findall(r"[一-鿿A-Za-z0-9]{2,12}", text)
        if not tokens:
            return False

        stopwords = {
            "法院",
            "本院",
            "认为",
            "原告",
            "被告",
            "一审",
            "二审",
            "民事",
            "裁定书",
            "判决书",
            "案件",
            "纠纷",
            "责任",
            "相关",
            "本案",
            "请求",
            "争议",
        }
        boosted_needles = {
            "合同",
            "买卖",
            "违约",
            "赔偿",
            "损失",
            "价差",
            "交货",
            "转卖",
            "履行",
            "代位清偿",
            "解除合同",
        }

        updated = False
        for token in tokens:
            normalized = token.strip()
            if len(normalized) < 2:
                continue
            if normalized in stopwords:
                continue
            if re.fullmatch(r"[0-9]+", normalized):
                continue

            weight = 1
            if any(needle in normalized for needle in boosted_needles):
                weight = 2
            old = feedback_term_weights.get(normalized, 0)
            feedback_term_weights[normalized] = old + weight
            if feedback_term_weights[normalized] != old:
                updated = True

        return updated
