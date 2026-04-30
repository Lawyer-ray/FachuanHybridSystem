"""评分排序：粗筛、LLM 评分、边界重评、双重审查。"""

from __future__ import annotations

import logging
import re
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Any

from apps.legal_research.models import LegalResearchTask
from apps.legal_research.services.executor_components.policy_mixin import DualReviewPolicy
from apps.legal_research.services.sources import CaseDetail

logger = logging.getLogger(__name__)


class ExecutorScoringMixin:
    SCORE_RETRY_ATTEMPTS = 3
    BORDERLINE_RECHECK_GAP = 0.08
    COARSE_RECALL_KEEP_MIN = 20
    COARSE_RECALL_MULTIPLIER = 6
    COARSE_RECALL_THRESHOLD_RATIO = 0.6
    COARSE_RECALL_THRESHOLD_CEIL = 0.52
    DEFERRED_RERANK_KEEP_MIN = 15
    DEFERRED_RERANK_MULTIPLIER = 6
    LLM_SCORING_CONCURRENCY = 5
    LLM_SCORING_BATCH_SIZE = 8

    # ── 粗筛与阈值 ───────────────────────────────────────────

    @classmethod
    def _coarse_recall(
        cls,
        *,
        similarity: Any,
        keyword: str,
        case_summary: str,
        detail: CaseDetail,
    ) -> tuple[float, str]:
        scorer = getattr(similarity, "coarse_recall_score", None)
        if callable(scorer):
            try:
                coarse = scorer(
                    keyword=keyword,
                    case_summary=case_summary,
                    title=detail.title,
                    case_digest=detail.case_digest,
                    content_text=detail.content_text,
                )
                score = cls._normalize_score(getattr(coarse, "score", 0.0))
                reason = str(getattr(coarse, "reason", "") or "")
                return score, reason
            except Exception:
                logger.exception(
                    "宽召回评分失败，回退关键词匹配",
                    extra={"doc_id": detail.doc_id_unquoted or detail.doc_id_raw},
                )

        overlap = cls._keyword_overlap(keyword=keyword, detail=detail)
        return overlap, f"宽召回fallback:关键词重合={overlap:.2f}"

    @classmethod
    def _coarse_rerank_budget(
        cls,
        *,
        task: LegalResearchTask,
        matched: int,
        batch_size: int,
    ) -> int:
        target_count = int(task.target_count)
        remaining_target = max(1, target_count - matched)
        return min(batch_size, max(cls.COARSE_RECALL_KEEP_MIN, remaining_target * cls.COARSE_RECALL_MULTIPLIER))

    @classmethod
    def _effective_fetch_limit(cls, *, max_candidates: int, skipped: int) -> int:
        baseline = max(1, int(max_candidates))
        extra = max(0, int(skipped))
        hard_cap = max(baseline, baseline * cls.DETAIL_FAILURE_BACKFILL_MULTIPLIER)
        return min(hard_cap, baseline + extra)

    @classmethod
    def _coarse_threshold(cls, min_similarity: float) -> float:
        base = max(0.1, min_similarity * cls.COARSE_RECALL_THRESHOLD_RATIO)
        return min(cls.COARSE_RECALL_THRESHOLD_CEIL, base)

    @classmethod
    def _deferred_rerank_budget(cls, *, task: LegalResearchTask, matched: int, deferred_count: int) -> int:
        target_count = int(task.target_count)
        remaining_target = max(1, target_count - matched)
        budget = max(cls.DEFERRED_RERANK_KEEP_MIN, remaining_target * cls.DEFERRED_RERANK_MULTIPLIER)
        return min(deferred_count, budget)

    @staticmethod
    def _should_rerank(*, coarse_score: float, threshold: float, rerank_used: int, rerank_budget: int) -> bool:
        if coarse_score < 0.20:
            return False
        return coarse_score >= threshold or rerank_used < rerank_budget

    # ── 单候选重排流水线 ─────────────────────────────────────

    @classmethod
    def _rerank_single_candidate(
        cls,
        *,
        similarity: Any,
        source_client: Any,
        session: Any,
        task: LegalResearchTask,
        detail: CaseDetail,
        coarse_score: float,
        coarse_reason: str,
        task_id: str,
        matched: int,
        skipped: int,
        feedback_term_weights: dict[str, int],
        feedback_min_score_floor: float,
        feedback_score_margin: float,
        min_similarity_threshold: float,
        dual_review_policy: DualReviewPolicy,
    ) -> tuple[int, int, bool]:
        sim = cls._score_case_with_retry(
            similarity=similarity,
            task=task,
            detail=detail,
            task_id=task_id,
        )
        if sim is None:
            return matched, skipped + 1, False

        if not task.llm_model and sim.model:
            task.llm_model = sim.model

        if sim.score < min_similarity_threshold and sim.score >= max(
            0.0, min_similarity_threshold - cls.BORDERLINE_RECHECK_GAP
        ):
            rescored = cls._rescore_borderline_with_retry(
                similarity=similarity,
                task=task,
                detail=detail,
                first_score=sim.score,
                first_reason=sim.reason,
                task_id=task_id,
            )
            if rescored is not None and rescored.score > sim.score:
                sim = rescored
                if not task.llm_model and sim.model:
                    task.llm_model = sim.model

        dual_review_metadata: dict[str, Any] | None = None
        similarity_metadata = cls._extract_similarity_metadata(similarity=sim)
        if (
            dual_review_policy.enabled
            and sim.score >= dual_review_policy.trigger_floor
            and str(getattr(sim, "model", "") or "").strip() != dual_review_policy.review_model
        ):
            reviewed = cls._review_case_with_retry(
                similarity=similarity,
                task=task,
                detail=detail,
                task_id=task_id,
                review_model=dual_review_policy.review_model,
                primary_score=sim.score,
                primary_reason=sim.reason,
            )
            if reviewed is not None:
                merged_score, merged_reason, merged_model, dual_review_metadata = cls._merge_dual_review_scores(
                    primary=sim,
                    reviewed=reviewed,
                    dual_review_policy=dual_review_policy,
                )
                sim.score = merged_score
                sim.reason = merged_reason
                sim.model = merged_model

        feedback_updated = cls._update_feedback_terms(
            feedback_term_weights=feedback_term_weights,
            detail=detail,
            reason=sim.reason,
            similarity_score=sim.score,
            min_similarity=min_similarity_threshold,
            feedback_min_score_floor=feedback_min_score_floor,
            feedback_score_margin=feedback_score_margin,
        )

        if sim.score < min_similarity_threshold:
            return matched, skipped, feedback_updated

        pdf = cls._download_pdf_with_retry(
            source_client=source_client,
            session=session,
            detail=detail,
            task_id=task_id,
        )
        if pdf is None:
            skipped += 1
            logger.info(
                "案例命中但PDF下载失败，跳过",
                extra={"task_id": task_id, "doc_id": detail.doc_id_raw},
            )
            return matched, skipped, feedback_updated

        matched += 1
        merged_metadata: dict[str, Any] | None = None
        if similarity_metadata or dual_review_metadata:
            merged_metadata = {}
            if similarity_metadata:
                merged_metadata.update(similarity_metadata)
            if dual_review_metadata:
                merged_metadata.update(dual_review_metadata)
        cls._save_result(
            task=task,
            detail=detail,
            similarity=sim,
            rank=matched,
            pdf=pdf,
            coarse_score=coarse_score,
            coarse_reason=coarse_reason,
            extra_metadata=merged_metadata,
        )
        return matched, skipped, feedback_updated

    # ── 评分与重试 ───────────────────────────────────────────

    @classmethod
    def _score_case_with_retry(
        cls,
        *,
        similarity: Any,
        task: LegalResearchTask,
        detail: CaseDetail,
        task_id: str,
    ) -> Any | None:
        keyword = cls._build_scoring_keyword(task.keyword, task.case_summary)
        for attempt in range(1, cls.SCORE_RETRY_ATTEMPTS + 1):
            try:
                return similarity.score_case(
                    keyword=keyword,
                    case_summary=task.case_summary,
                    title=detail.title,
                    case_digest=detail.case_digest,
                    content_text=detail.content_text,
                    model=task.llm_model or None,
                )
            except Exception as exc:
                if attempt >= cls.SCORE_RETRY_ATTEMPTS:
                    logger.warning(
                        "案例相似度评分失败，已跳过该案例",
                        extra={
                            "task_id": task_id,
                            "doc_id": detail.doc_id_unquoted or detail.doc_id_raw,
                            "attempt": attempt,
                            "max_attempts": cls.SCORE_RETRY_ATTEMPTS,
                            "error": str(exc),
                        },
                    )
                    return None
                logger.warning(
                    "案例相似度评分失败，准备重试",
                    extra={
                        "task_id": task_id,
                        "doc_id": detail.doc_id_unquoted or detail.doc_id_raw,
                        "attempt": attempt,
                        "max_attempts": cls.SCORE_RETRY_ATTEMPTS,
                        "error": str(exc),
                    },
                )
                cls._sleep_for_retry(attempt=attempt)
        return None

    @classmethod
    def _rescore_borderline_with_retry(
        cls,
        *,
        similarity: Any,
        task: LegalResearchTask,
        detail: CaseDetail,
        first_score: float,
        first_reason: str,
        task_id: str,
    ) -> Any | None:
        rescoring = getattr(similarity, "rescore_borderline_case", None)
        if not callable(rescoring):
            return None

        keyword = cls._build_scoring_keyword(task.keyword, task.case_summary)
        for attempt in range(1, cls.SCORE_RETRY_ATTEMPTS + 1):
            try:
                return rescoring(
                    keyword=keyword,
                    case_summary=task.case_summary,
                    title=detail.title,
                    case_digest=detail.case_digest,
                    content_text=detail.content_text,
                    first_score=first_score,
                    first_reason=first_reason,
                    model=task.llm_model or None,
                )
            except Exception as exc:
                if attempt >= cls.SCORE_RETRY_ATTEMPTS:
                    logger.info(
                        "近阈值复判失败，保留首轮评分",
                        extra={
                            "task_id": task_id,
                            "doc_id": detail.doc_id_unquoted or detail.doc_id_raw,
                            "attempt": attempt,
                            "max_attempts": cls.SCORE_RETRY_ATTEMPTS,
                            "error": str(exc),
                        },
                    )
                    return None
                cls._sleep_for_retry(attempt=attempt)
        return None

    @classmethod
    def _review_case_with_retry(
        cls,
        *,
        similarity: Any,
        task: LegalResearchTask,
        detail: CaseDetail,
        task_id: str,
        review_model: str,
        primary_score: float,
        primary_reason: str,
    ) -> Any | None:
        rescoring = getattr(similarity, "rescore_borderline_case", None)
        keyword = cls._build_scoring_keyword(task.keyword, task.case_summary)
        for attempt in range(1, cls.SCORE_RETRY_ATTEMPTS + 1):
            try:
                if callable(rescoring):
                    return rescoring(
                        keyword=keyword,
                        case_summary=task.case_summary,
                        title=detail.title,
                        case_digest=detail.case_digest,
                        content_text=detail.content_text,
                        first_score=primary_score,
                        first_reason=primary_reason,
                        model=review_model,
                    )
                return similarity.score_case(
                    keyword=keyword,
                    case_summary=task.case_summary,
                    title=detail.title,
                    case_digest=detail.case_digest,
                    content_text=detail.content_text,
                    model=review_model,
                )
            except Exception as exc:
                if attempt >= cls.SCORE_RETRY_ATTEMPTS:
                    logger.info(
                        "双模型复核失败，回退主模型评分",
                        extra={
                            "task_id": task_id,
                            "doc_id": detail.doc_id_unquoted or detail.doc_id_raw,
                            "attempt": attempt,
                            "max_attempts": cls.SCORE_RETRY_ATTEMPTS,
                            "review_model": review_model,
                            "error": str(exc),
                        },
                    )
                    return None
                cls._sleep_for_retry(attempt=attempt)
        return None

    @classmethod
    def _merge_dual_review_scores(
        cls,
        *,
        primary: Any,
        reviewed: Any,
        dual_review_policy: DualReviewPolicy,
    ) -> tuple[float, str, str, dict[str, Any]]:
        primary_score = cls._normalize_score(getattr(primary, "score", 0.0))
        review_score = cls._normalize_score(getattr(reviewed, "score", 0.0))

        primary_weight = max(0.0, dual_review_policy.primary_weight)
        secondary_weight = max(0.0, dual_review_policy.secondary_weight)
        total_weight = max(1e-6, primary_weight + secondary_weight)
        primary_weight = primary_weight / total_weight
        secondary_weight = secondary_weight / total_weight

        blended_score = primary_score * primary_weight + review_score * secondary_weight
        disagreement = primary_score - review_score
        if disagreement > dual_review_policy.gap_tolerance:
            blended_score = min(blended_score, review_score + 0.04)
        if review_score < dual_review_policy.required_min:
            blended_score = min(blended_score, review_score)
        blended_score = max(0.0, min(1.0, blended_score))

        primary_reason = str(getattr(primary, "reason", "") or "")
        reviewed_reason = str(getattr(reviewed, "reason", "") or "")
        merged_reason = (
            f"主判:{primary_reason[:90]} | 复核:{reviewed_reason[:90]}"
            if primary_reason or reviewed_reason
            else "双模型复核完成"
        )
        primary_model = str(getattr(primary, "model", "") or "")
        reviewed_model = str(getattr(reviewed, "model", "") or "")
        merged_model = f"{primary_model}|review:{reviewed_model}" if primary_model or reviewed_model else "dual-review"
        metadata = {
            "dual_review": {
                "primary_score": round(primary_score, 4),
                "review_score": round(review_score, 4),
                "blended_score": round(blended_score, 4),
                "primary_model": primary_model,
                "review_model": reviewed_model,
                "primary_weight": round(primary_weight, 4),
                "secondary_weight": round(secondary_weight, 4),
                "gap_tolerance": round(dual_review_policy.gap_tolerance, 4),
                "required_min": round(dual_review_policy.required_min, 4),
            }
        }
        return blended_score, merged_reason[:220], merged_model, metadata

    # ── 工具方法 ─────────────────────────────────────────────

    @staticmethod
    def _normalize_score(score: Any) -> float:
        try:
            value = float(score)
        except (TypeError, ValueError):
            return 0.0
        return max(0.0, min(1.0, value))

    @staticmethod
    def _keyword_overlap(*, keyword: str, detail: CaseDetail) -> float:
        tokens = [x for x in re.split(r"[\s,，;；、]+", (keyword or "").lower()) if x and len(x) >= 2]
        if not tokens:
            return 0.0
        haystack = f"{detail.title} {detail.case_digest} {(detail.content_text or '')[:1200]}".lower()
        matched = sum(1 for token in tokens if token in haystack)
        return matched / len(tokens)

    # ── 并发评分 ─────────────────────────────────────────────

    def _batch_rerank_candidates(
        self,
        *,
        candidates: list[tuple[Any, float, str]],
        similarity: Any,
        task: LegalResearchTask,
        task_id: str,
        concurrency: int,
    ) -> list[tuple[Any, Any, float, str]]:
        if not candidates:
            return []

        results: list[tuple[Any, Any, float, str]] = []

        def _score_one(detail: Any) -> Any | None:
            return self._score_case_with_retry(similarity=similarity, task=task, detail=detail, task_id=task_id)

        effective_concurrency = max(1, min(concurrency, len(candidates)))
        with ThreadPoolExecutor(max_workers=effective_concurrency) as pool:
            future_map = {
                pool.submit(_score_one, detail): (detail, coarse_score, coarse_reason)
                for detail, coarse_score, coarse_reason in candidates
            }
            for future in as_completed(future_map):
                detail, coarse_score, coarse_reason = future_map[future]
                try:
                    sim = future.result()
                    if sim is not None:
                        results.append((detail, sim, coarse_score, coarse_reason))
                except Exception:
                    logger.warning("并发LLM评分异常", extra={"task_id": task_id})

        results.sort(key=lambda x: getattr(x[1], "score", 0.0), reverse=True)
        return results
