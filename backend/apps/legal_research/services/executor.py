from __future__ import annotations

import json
import logging
import re
from dataclasses import dataclass
from types import SimpleNamespace
from typing import Any

from apps.core.interfaces import ServiceLocator
from apps.legal_research.models import LegalResearchSearchMode, LegalResearchTask, LegalResearchTaskStatus
from apps.legal_research.services.executor_components import (
    ExecutorResultPersistenceMixin,
    ExecutorSourceGatewayMixin,
    ExecutorTaskLifecycleMixin,
)
from apps.legal_research.services.similarity_service import CaseSimilarityService
from apps.legal_research.services.sources import CaseDetail, get_case_source_client
from apps.legal_research.services.tuning_config import LegalResearchTuningConfig

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class _DualReviewPolicy:
    enabled: bool
    review_model: str
    primary_weight: float
    secondary_weight: float
    trigger_floor: float
    gap_tolerance: float
    required_min: float


@dataclass(frozen=True)
class _AdaptiveThresholdPolicy:
    enabled: bool
    floor: float
    step: float
    scan_interval: int


class LegalResearchExecutor(
    ExecutorTaskLifecycleMixin,
    ExecutorSourceGatewayMixin,
    ExecutorResultPersistenceMixin,
):
    CANDIDATE_BATCH_SIZE = 100
    PAGE_SIZE_HINT = 20
    MAX_PAGE_WINDOW = 2000
    SEARCH_RETRY_ATTEMPTS = 3
    DETAIL_RETRY_ATTEMPTS = 3
    DOWNLOAD_RETRY_ATTEMPTS = 3
    SCORE_RETRY_ATTEMPTS = 3
    BORDERLINE_RECHECK_GAP = 0.08
    RETRY_BACKOFF_SECONDS = 0.8
    RETRY_BACKOFF_MAX_SECONDS = 6.0
    COARSE_RECALL_KEEP_MIN = 20
    COARSE_RECALL_MULTIPLIER = 6
    COARSE_RECALL_THRESHOLD_RATIO = 0.5
    COARSE_RECALL_THRESHOLD_CEIL = 0.45
    DEFERRED_RERANK_KEEP_MIN = 25
    DEFERRED_RERANK_MULTIPLIER = 10
    DETAIL_FAILURE_BACKFILL_MULTIPLIER = 2
    QUERY_EXPANSION_TRIGGER_CANDIDATES = 80
    INTENT_QUERY_MAX = 5
    FEEDBACK_QUERY_LIMIT = 2
    FEEDBACK_MIN_TERMS = 3
    FEEDBACK_MIN_SCORE_FLOOR = 0.68
    QUERY_VARIANT_MAX = 2
    QUERY_VARIANT_MAX_TOKENS = 220
    QUERY_VARIANT_TIMEOUT_SECONDS = 25
    DETAIL_CACHE_TTL_SECONDS = 21600
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
    INTENT_RELATION_REGEX: tuple[str, ...] = (
        r"[\u4e00-\u9fffA-Za-z0-9]{2,20}合同纠纷",
        r"[\u4e00-\u9fffA-Za-z0-9]{2,20}纠纷",
        r"[\u4e00-\u9fffA-Za-z0-9]{2,20}侵权纠纷",
        r"[\u4e00-\u9fffA-Za-z0-9]{2,20}争议",
        r"[\u4e00-\u9fffA-Za-z0-9]{2,20}之诉",
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

    def run(self, *, task_id: str) -> dict[str, Any]:
        task, early_result = self._acquire_task(task_id=task_id)
        if early_result is not None:
            return early_result
        if task is None:
            logger.error("案例检索任务获取失败", extra={"task_id": task_id})
            return {"task_id": task_id, "status": "failed", "error": "任务不存在"}

        tuning = LegalResearchTuningConfig.load()
        try:
            similarity = CaseSimilarityService(tuning=tuning)
        except TypeError:
            similarity = CaseSimilarityService()
        search_mode = str(
            getattr(task, "search_mode", LegalResearchSearchMode.EXPANDED) or LegalResearchSearchMode.EXPANDED
        )
        single_search_mode = search_mode.strip().lower() == LegalResearchSearchMode.SINGLE
        query_variant_enabled = bool(getattr(tuning, "query_variant_enabled", True))
        query_variant_max_count = max(0, int(getattr(tuning, "query_variant_max_count", self.QUERY_VARIANT_MAX)))
        query_variant_model = str(getattr(tuning, "query_variant_model", "") or "").strip()
        detail_cache_ttl_seconds = max(
            60, int(getattr(tuning, "detail_cache_ttl_seconds", self.DETAIL_CACHE_TTL_SECONDS))
        )
        feedback_query_limit = max(0, int(tuning.feedback_query_limit))
        feedback_min_terms = max(1, int(tuning.feedback_min_terms))
        feedback_min_score_floor = max(0.0, min(1.0, float(tuning.feedback_min_score_floor)))
        feedback_score_margin = max(0.01, min(0.6, float(tuning.feedback_score_margin)))
        dual_review_policy = self._build_dual_review_policy(tuning=tuning)
        min_similarity_threshold = self._resolve_effective_min_similarity(
            requested_min_similarity=task.min_similarity_score,
            tuning=tuning,
        )
        adaptive_threshold_policy = self._build_adaptive_threshold_policy(
            baseline_min_similarity=min_similarity_threshold,
            tuning=tuning,
        )
        effective_min_similarity_threshold = min_similarity_threshold
        adaptive_checkpoint_scanned = 0
        adaptive_checkpoint_matched = 0
        lowest_min_similarity_threshold = min_similarity_threshold
        primary_queries: list[str] = []
        initial_expansion_queries: list[str] = []
        feedback_queries: list[str] = []
        query_stats: dict[str, dict[str, int]] = {}

        session = None
        try:
            source_client = get_case_source_client(task.source)
            session = source_client.open_session(
                username=task.credential.account,
                password=task.credential.password,
                login_url=task.credential.url or None,
            )
            if hasattr(session, "task_id"):
                session.task_id = str(task.id)
            if single_search_mode:
                primary_query = re.sub(r"\s+", " ", str(task.keyword or "")).strip()
                keyword_candidates = [primary_query] if primary_query else []
            else:
                keyword_candidates = self._build_search_keywords(task.keyword, task.case_summary)
            if (not single_search_mode) and query_variant_enabled and query_variant_max_count > 0:
                llm_variants = self._generate_llm_query_variants(
                    keyword=task.keyword,
                    case_summary=task.case_summary,
                    model=(query_variant_model or task.llm_model or None),
                    max_variants=query_variant_max_count,
                )
                if llm_variants:
                    keyword_candidates = self._merge_query_candidates(keyword_candidates, llm_variants)
            search_keywords = keyword_candidates[:1]
            expansion_keywords = [] if single_search_mode else keyword_candidates[1:]
            primary_queries = [query for query in search_keywords if str(query).strip()]
            initial_expansion_queries = [query for query in expansion_keywords if str(query).strip()]
            search_query_set = {q.strip().lower() for q in search_keywords if q.strip()}
            scoring_keyword = self._build_scoring_keyword(task.keyword, task.case_summary)
            feedback_term_weights: dict[str, int] = {}
            feedback_queries_added = 0
            detail_cache_local: dict[str, CaseDetail] = {}

            scanned = 0
            matched = 0
            fetched = 0
            skipped = 0
            seen_doc_ids: set[str] = set()
            query_index = 0
            while query_index < len(search_keywords) and scanned < task.max_candidates and matched < task.target_count:
                search_keyword = search_keywords[query_index]
                query_offset = 0
                query_new_candidates = 0
                query_metric = query_stats.setdefault(search_keyword, self._init_query_metric())

                while (
                    fetched < self._effective_fetch_limit(max_candidates=task.max_candidates, skipped=skipped)
                    and scanned < task.max_candidates
                    and matched < task.target_count
                ):
                    if self._is_cancel_requested(task.id):
                        self._mark_cancelled(task=task, scanned=scanned, matched=matched, skipped=skipped)
                        return {
                            "task_id": str(task.id),
                            "status": task.status,
                            "scanned_count": scanned,
                            "matched_count": matched,
                            "skipped_count": skipped,
                            "query_trace": self._build_query_trace_payload(
                                primary_queries=primary_queries,
                                expansion_queries=initial_expansion_queries,
                                feedback_queries=feedback_queries,
                                query_stats=query_stats,
                            ),
                        }

                    fetch_limit = self._effective_fetch_limit(max_candidates=task.max_candidates, skipped=skipped)
                    batch_size = min(self.CANDIDATE_BATCH_SIZE, max(1, fetch_limit - fetched))
                    items = self._fetch_candidate_batch_with_retry(
                        source_client=source_client,
                        session=session,
                        keyword=search_keyword,
                        offset=query_offset,
                        batch_size=batch_size,
                        task_id=str(task.id),
                    )

                    if not items:
                        break
                    query_offset += len(items)

                    unique_items, duplicate_in_batch = self._reserve_new_items(items=items, seen_doc_ids=seen_doc_ids)
                    if not unique_items:
                        continue

                    fetched += len(unique_items)
                    query_new_candidates += len(unique_items)
                    query_metric["candidates"] += len(unique_items)
                    task.candidate_count = fetched
                    duplicate_suffix = f"，重复 {duplicate_in_batch} 篇" if duplicate_in_batch else ""
                    task.message = (
                        f"已获取候选案例 {fetched}/{task.max_candidates} 篇"
                        f"（检索式 {query_index + 1}/{len(search_keywords)}"
                        f"，本批新增 {len(unique_items)} 篇{duplicate_suffix}）"
                    )
                    self._save_task_safely(task, update_fields=["candidate_count", "message", "updated_at"])

                    rerank_threshold = self._coarse_threshold(effective_min_similarity_threshold)
                    rerank_budget = self._coarse_rerank_budget(task=task, matched=matched, batch_size=len(unique_items))
                    rerank_used = 0
                    deferred_candidates: list[tuple[CaseDetail, float, str]] = []
                    for item in unique_items:
                        if self._is_cancel_requested(task.id):
                            self._mark_cancelled(task=task, scanned=scanned, matched=matched, skipped=skipped)
                            return {
                                "task_id": str(task.id),
                                "status": task.status,
                                "scanned_count": scanned,
                                "matched_count": matched,
                                "skipped_count": skipped,
                            }

                        if matched >= task.target_count:
                            break

                        detail = self._fetch_case_detail_with_cache(
                            source_client=source_client,
                            session=session,
                            source=task.source,
                            item=item,
                            task_id=str(task.id),
                            local_cache=detail_cache_local,
                            ttl_seconds=detail_cache_ttl_seconds,
                        )
                        if detail is None:
                            skipped += 1
                            query_metric["skipped"] += 1
                            self._update_progress(task=task, scanned=scanned, matched=matched, skipped=skipped)
                            (
                                effective_min_similarity_threshold,
                                adaptive_checkpoint_scanned,
                                adaptive_checkpoint_matched,
                                threshold_lowered,
                            ) = self._maybe_decay_min_similarity_threshold(
                                current_threshold=effective_min_similarity_threshold,
                                scanned=scanned,
                                matched=matched,
                                checkpoint_scanned=adaptive_checkpoint_scanned,
                                checkpoint_matched=adaptive_checkpoint_matched,
                                policy=adaptive_threshold_policy,
                            )
                            if threshold_lowered:
                                lowest_min_similarity_threshold = min(
                                    lowest_min_similarity_threshold,
                                    effective_min_similarity_threshold,
                                )
                            continue

                        scanned += 1
                        query_metric["scanned"] += 1

                        coarse_score, coarse_reason = self._coarse_recall(
                            similarity=similarity,
                            keyword=scoring_keyword,
                            case_summary=task.case_summary,
                            detail=detail,
                        )
                        should_rerank = self._should_rerank(
                            coarse_score=coarse_score,
                            threshold=rerank_threshold,
                            rerank_used=rerank_used,
                            rerank_budget=rerank_budget,
                        )
                        if not should_rerank:
                            deferred_candidates.append((detail, coarse_score, coarse_reason))
                            self._update_progress(task=task, scanned=scanned, matched=matched, skipped=skipped)
                            (
                                effective_min_similarity_threshold,
                                adaptive_checkpoint_scanned,
                                adaptive_checkpoint_matched,
                                threshold_lowered,
                            ) = self._maybe_decay_min_similarity_threshold(
                                current_threshold=effective_min_similarity_threshold,
                                scanned=scanned,
                                matched=matched,
                                checkpoint_scanned=adaptive_checkpoint_scanned,
                                checkpoint_matched=adaptive_checkpoint_matched,
                                policy=adaptive_threshold_policy,
                            )
                            if threshold_lowered:
                                lowest_min_similarity_threshold = min(
                                    lowest_min_similarity_threshold,
                                    effective_min_similarity_threshold,
                                )
                            continue
                        rerank_used += 1

                        previous_matched = matched
                        matched, skipped, feedback_updated = self._rerank_single_candidate(
                            similarity=similarity,
                            source_client=source_client,
                            session=session,
                            task=task,
                            detail=detail,
                            coarse_score=coarse_score,
                            coarse_reason=coarse_reason,
                            task_id=str(task.id),
                            matched=matched,
                            skipped=skipped,
                            feedback_term_weights=feedback_term_weights,
                            feedback_min_score_floor=feedback_min_score_floor,
                            feedback_score_margin=feedback_score_margin,
                            min_similarity_threshold=effective_min_similarity_threshold,
                            dual_review_policy=dual_review_policy,
                        )
                        query_metric["matched"] += max(0, matched - previous_matched)
                        if (not single_search_mode) and feedback_updated:
                            feedback_queries_added, feedback_query = self._maybe_append_feedback_query(
                                search_keywords=search_keywords,
                                search_query_set=search_query_set,
                                feedback_term_weights=feedback_term_weights,
                                keyword=task.keyword,
                                case_summary=task.case_summary,
                                feedback_queries_added=feedback_queries_added,
                                feedback_query_limit=feedback_query_limit,
                                feedback_min_terms=feedback_min_terms,
                            )
                            if feedback_query:
                                if feedback_query not in feedback_queries:
                                    feedback_queries.append(feedback_query)
                                task.message = f"已触发伪相关反馈扩展检索：{feedback_query}"
                                self._save_task_safely(task, update_fields=["message", "updated_at"])
                        self._update_progress(task=task, scanned=scanned, matched=matched, skipped=skipped)
                        (
                            effective_min_similarity_threshold,
                            adaptive_checkpoint_scanned,
                            adaptive_checkpoint_matched,
                            threshold_lowered,
                        ) = self._maybe_decay_min_similarity_threshold(
                            current_threshold=effective_min_similarity_threshold,
                            scanned=scanned,
                            matched=matched,
                            checkpoint_scanned=adaptive_checkpoint_scanned,
                            checkpoint_matched=adaptive_checkpoint_matched,
                            policy=adaptive_threshold_policy,
                        )
                        if threshold_lowered:
                            lowest_min_similarity_threshold = min(
                                lowest_min_similarity_threshold,
                                effective_min_similarity_threshold,
                            )

                    if matched < task.target_count and deferred_candidates:
                        deferred_limit = self._deferred_rerank_budget(
                            task=task,
                            matched=matched,
                            deferred_count=len(deferred_candidates),
                        )
                        for detail, coarse_score, coarse_reason in sorted(
                            deferred_candidates,
                            key=lambda x: x[1],
                            reverse=True,
                        )[:deferred_limit]:
                            if self._is_cancel_requested(task.id):
                                self._mark_cancelled(task=task, scanned=scanned, matched=matched, skipped=skipped)
                                return {
                                    "task_id": str(task.id),
                                    "status": task.status,
                                    "scanned_count": scanned,
                                    "matched_count": matched,
                                    "skipped_count": skipped,
                                    "query_trace": self._build_query_trace_payload(
                                        primary_queries=primary_queries,
                                        expansion_queries=initial_expansion_queries,
                                        feedback_queries=feedback_queries,
                                        query_stats=query_stats,
                                    ),
                                }
                            if matched >= task.target_count:
                                break

                            previous_matched = matched
                            matched, skipped, feedback_updated = self._rerank_single_candidate(
                                similarity=similarity,
                                source_client=source_client,
                                session=session,
                                task=task,
                                detail=detail,
                                coarse_score=coarse_score,
                                coarse_reason=coarse_reason,
                                task_id=str(task.id),
                                matched=matched,
                                skipped=skipped,
                                feedback_term_weights=feedback_term_weights,
                                feedback_min_score_floor=feedback_min_score_floor,
                                feedback_score_margin=feedback_score_margin,
                                min_similarity_threshold=effective_min_similarity_threshold,
                                dual_review_policy=dual_review_policy,
                            )
                            query_metric["matched"] += max(0, matched - previous_matched)
                            if (not single_search_mode) and feedback_updated:
                                feedback_queries_added, feedback_query = self._maybe_append_feedback_query(
                                    search_keywords=search_keywords,
                                    search_query_set=search_query_set,
                                    feedback_term_weights=feedback_term_weights,
                                    keyword=task.keyword,
                                    case_summary=task.case_summary,
                                    feedback_queries_added=feedback_queries_added,
                                    feedback_query_limit=feedback_query_limit,
                                    feedback_min_terms=feedback_min_terms,
                                )
                                if feedback_query:
                                    if feedback_query not in feedback_queries:
                                        feedback_queries.append(feedback_query)
                                    task.message = f"已触发伪相关反馈扩展检索：{feedback_query}"
                                    self._save_task_safely(task, update_fields=["message", "updated_at"])
                            self._update_progress(task=task, scanned=scanned, matched=matched, skipped=skipped)
                            (
                                effective_min_similarity_threshold,
                                adaptive_checkpoint_scanned,
                                adaptive_checkpoint_matched,
                                threshold_lowered,
                            ) = self._maybe_decay_min_similarity_threshold(
                                current_threshold=effective_min_similarity_threshold,
                                scanned=scanned,
                                matched=matched,
                                checkpoint_scanned=adaptive_checkpoint_scanned,
                                checkpoint_matched=adaptive_checkpoint_matched,
                                policy=adaptive_threshold_policy,
                            )
                            if threshold_lowered:
                                lowest_min_similarity_threshold = min(
                                    lowest_min_similarity_threshold,
                                    effective_min_similarity_threshold,
                                )

                if (
                    not single_search_mode
                    and expansion_keywords
                    and matched < task.target_count
                    and query_index == 0
                    and fetched < min(task.max_candidates, self.QUERY_EXPANSION_TRIGGER_CANDIDATES)
                ):
                    for query in expansion_keywords:
                        normalized = query.strip().lower()
                        if not normalized or normalized in search_query_set:
                            continue
                        search_query_set.add(normalized)
                        search_keywords.append(query)
                    expansion_keywords = []
                    task.message = (
                        f"主检索式候选仅 {fetched} 篇，切换扩展检索式继续召回"
                        if query_new_candidates > 0
                        else "主检索式未召回候选，切换扩展检索式重试"
                    )
                    self._save_task_safely(task, update_fields=["message", "updated_at"])

                self._apply_query_performance_feedback(
                    search_keyword=search_keyword,
                    metric=query_metric,
                    feedback_term_weights=feedback_term_weights,
                )
                if not single_search_mode:
                    feedback_queries_added, feedback_query = self._maybe_append_feedback_query(
                        search_keywords=search_keywords,
                        search_query_set=search_query_set,
                        feedback_term_weights=feedback_term_weights,
                        keyword=task.keyword,
                        case_summary=task.case_summary,
                        feedback_queries_added=feedback_queries_added,
                        feedback_query_limit=feedback_query_limit,
                        feedback_min_terms=feedback_min_terms,
                    )
                    if feedback_query:
                        if feedback_query not in feedback_queries:
                            feedback_queries.append(feedback_query)
                        task.message = f"已触发检索式反馈扩展：{feedback_query}"
                        self._save_task_safely(task, update_fields=["message", "updated_at"])

                query_index += 1

            if self._is_cancel_requested(task.id):
                self._mark_cancelled(task=task, scanned=scanned, matched=matched, skipped=skipped)
                return {
                    "task_id": str(task.id),
                    "status": task.status,
                    "scanned_count": scanned,
                    "matched_count": matched,
                    "skipped_count": skipped,
                    "query_trace": self._build_query_trace_payload(
                        primary_queries=primary_queries,
                        expansion_queries=initial_expansion_queries,
                        feedback_queries=feedback_queries,
                        query_stats=query_stats,
                    ),
                }

            skip_suffix = f"（跳过异常案例 {skipped} 篇）" if skipped else ""
            adaptive_suffix = self._build_adaptive_threshold_suffix(
                baseline=min_similarity_threshold,
                lowered_to=lowest_min_similarity_threshold,
            )
            query_suffix = self._build_query_stats_suffix(query_stats=query_stats)
            if query_stats:
                logger.info(
                    "案例检索式统计",
                    extra={
                        "task_id": str(task.id),
                        "query_stats": query_stats,
                    },
                )

            if fetched == 0:
                self._mark_completed(task, message="未检索到候选案例")
            elif matched >= task.target_count:
                self._mark_completed(
                    task,
                    message=f"达到目标，命中 {matched}/{task.target_count} 篇相似案例{skip_suffix}{adaptive_suffix}{query_suffix}",
                )
            elif scanned >= task.max_candidates:
                self._mark_completed(
                    task,
                    message=(
                        f"达到最大扫描上限 {task.max_candidates}，"
                        f"命中 {matched}/{task.target_count}，未达到目标{skip_suffix}{adaptive_suffix}{query_suffix}"
                    ),
                )
            else:
                self._mark_completed(
                    task,
                    message=(
                        f"候选案例已扫描完毕（共 {task.candidate_count} 篇），"
                        f"命中 {matched}/{task.target_count}，未达到目标{skip_suffix}{adaptive_suffix}{query_suffix}"
                    ),
                )

            return {
                "task_id": str(task.id),
                "status": task.status,
                "scanned_count": task.scanned_count,
                "matched_count": task.matched_count,
                "skipped_count": skipped,
                "query_trace": self._build_query_trace_payload(
                    primary_queries=primary_queries,
                    expansion_queries=initial_expansion_queries,
                    feedback_queries=feedback_queries,
                    query_stats=query_stats,
                ),
            }
        except Exception as e:
            logger.exception("案例检索任务失败", extra={"task_id": str(task.id)})
            self._mark_failed(task, str(e))
            return {
                "task_id": str(task.id),
                "status": "failed",
                "error": str(e),
                "query_trace": self._build_query_trace_payload(
                    primary_queries=primary_queries,
                    expansion_queries=initial_expansion_queries,
                    feedback_queries=feedback_queries,
                    query_stats=query_stats,
                ),
            }
        finally:
            if session is not None:
                session.close()

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
        remaining_target = max(1, task.target_count - matched)
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

    @staticmethod
    def _resolve_effective_min_similarity(
        *,
        requested_min_similarity: float,
        tuning: LegalResearchTuningConfig,
    ) -> float:
        baseline = max(0.0, min(1.0, float(requested_min_similarity)))
        if not tuning.online_tuning_enabled:
            return baseline
        adjusted = baseline + float(tuning.online_min_similarity_delta)
        return max(0.4, min(0.99, adjusted))

    @staticmethod
    def _build_dual_review_policy(*, tuning: LegalResearchTuningConfig) -> _DualReviewPolicy:
        review_model = str(tuning.dual_review_model or "").strip()
        enabled = bool(tuning.dual_review_enabled and review_model)
        primary_weight = max(0.0, min(1.0, float(tuning.dual_review_primary_weight)))
        secondary_weight = max(0.0, min(1.0, float(tuning.dual_review_secondary_weight)))
        if primary_weight + secondary_weight <= 0:
            primary_weight = 0.62
            secondary_weight = 0.38
        return _DualReviewPolicy(
            enabled=enabled,
            review_model=review_model,
            primary_weight=primary_weight,
            secondary_weight=secondary_weight,
            trigger_floor=max(0.0, min(1.0, float(tuning.dual_review_trigger_floor))),
            gap_tolerance=max(0.01, min(0.6, float(tuning.dual_review_gap_tolerance))),
            required_min=max(0.0, min(1.0, float(tuning.dual_review_required_min))),
        )

    @staticmethod
    def _build_adaptive_threshold_policy(
        *,
        baseline_min_similarity: float,
        tuning: LegalResearchTuningConfig,
    ) -> _AdaptiveThresholdPolicy:
        baseline = max(0.4, min(0.99, float(baseline_min_similarity)))
        configured_floor = max(0.4, min(0.99, float(tuning.adaptive_threshold_floor)))
        floor = min(baseline, configured_floor)
        step = max(0.005, min(0.2, float(tuning.adaptive_threshold_step)))
        scan_interval = max(10, int(tuning.adaptive_threshold_scan_interval))
        enabled = bool(tuning.adaptive_threshold_enabled and floor < baseline)
        return _AdaptiveThresholdPolicy(enabled=enabled, floor=floor, step=step, scan_interval=scan_interval)

    @staticmethod
    def _maybe_decay_min_similarity_threshold(
        *,
        current_threshold: float,
        scanned: int,
        matched: int,
        checkpoint_scanned: int,
        checkpoint_matched: int,
        policy: _AdaptiveThresholdPolicy,
    ) -> tuple[float, int, int, bool]:
        if not policy.enabled:
            return current_threshold, checkpoint_scanned, checkpoint_matched, False
        if current_threshold <= policy.floor + 1e-6:
            return current_threshold, scanned, matched, False
        if matched > checkpoint_matched:
            return current_threshold, scanned, matched, False
        if scanned - checkpoint_scanned < policy.scan_interval:
            return current_threshold, checkpoint_scanned, checkpoint_matched, False

        lowered = max(policy.floor, current_threshold - policy.step)
        if lowered >= current_threshold:
            return current_threshold, scanned, matched, False
        return lowered, scanned, matched, True

    @staticmethod
    def _build_adaptive_threshold_suffix(*, baseline: float, lowered_to: float) -> str:
        baseline_value = max(0.0, min(1.0, float(baseline)))
        lowered_value = max(0.0, min(1.0, float(lowered_to)))
        if lowered_value >= baseline_value - 1e-6:
            return ""
        return f"（自适应阈值 {baseline_value:.2f}→{lowered_value:.2f}）"

    @classmethod
    def _deferred_rerank_budget(cls, *, task: LegalResearchTask, matched: int, deferred_count: int) -> int:
        remaining_target = max(1, task.target_count - matched)
        budget = max(cls.DEFERRED_RERANK_KEEP_MIN, remaining_target * cls.DEFERRED_RERANK_MULTIPLIER)
        return min(deferred_count, budget)

    @staticmethod
    def _should_rerank(*, coarse_score: float, threshold: float, rerank_used: int, rerank_budget: int) -> bool:
        return coarse_score >= threshold or rerank_used < rerank_budget

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
        dual_review_policy: _DualReviewPolicy,
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
        dual_review_policy: _DualReviewPolicy,
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

    @classmethod
    def _build_search_keyword(cls, keyword: str, case_summary: str) -> str:
        base_tokens = cls._split_tokens(keyword)
        if not base_tokens:
            base_tokens = cls._split_tokens(case_summary)
        merged = cls._expand_terms_with_synonyms(base_tokens, max_tokens=12)
        return " ".join(merged).strip()

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

        fallback_tokens = cls._split_tokens(keyword) or cls._split_tokens(case_summary)
        return [" ".join(cls._expand_terms_with_synonyms(fallback_tokens, max_tokens=8)).strip()]

    @classmethod
    def _build_fallback_search_keyword(cls, keyword: str, case_summary: str) -> str:
        fallback_tokens = cls._split_tokens(keyword)
        filtered = [token for token in fallback_tokens if not cls._is_location_or_court_token(token)]
        summary_terms = cls._extract_summary_terms(case_summary)
        merged = cls._expand_terms_with_synonyms([*filtered, *summary_terms], max_tokens=12)
        return " ".join(merged).strip()

    @classmethod
    def _build_scoring_keyword(cls, keyword: str, case_summary: str) -> str:
        base_tokens = cls._split_tokens(keyword)
        filtered = [token for token in base_tokens if not cls._is_location_or_court_token(token)]
        summary_terms = cls._extract_summary_terms(case_summary)
        merged = cls._expand_terms_with_synonyms([*filtered, *summary_terms], max_tokens=10)
        if not merged:
            merged = cls._expand_terms_with_synonyms([*base_tokens, *summary_terms], max_tokens=10)
        return " ".join(merged).strip()

    @classmethod
    def _build_summary_search_keyword(cls, case_summary: str) -> str:
        summary_terms = cls._expand_terms_with_synonyms(cls._extract_summary_terms(case_summary), max_tokens=8)
        return " ".join(summary_terms[:6]).strip()

    @classmethod
    def _build_feedback_search_keyword(cls, keyword: str, case_summary: str, feedback_terms: list[str]) -> str:
        keyword_tokens = cls._split_tokens(keyword)
        keyword_tokens = [token for token in keyword_tokens if not cls._is_location_or_court_token(token)]
        summary_terms = cls._extract_summary_terms(case_summary)
        merged = cls._expand_terms_with_synonyms([*keyword_tokens, *summary_terms, *feedback_terms], max_tokens=12)
        return " ".join(merged).strip()

    @classmethod
    def _build_intent_search_keywords(cls, keyword: str, case_summary: str) -> list[str]:
        context = f"{keyword} {case_summary}".strip()
        if not context:
            return []

        intent_slots = cls._extract_intent_slots_with_confidence(context)
        relation_terms = intent_slots["relation_high"]
        breach_terms = intent_slots["breach_high"]
        damage_terms = intent_slots["damage_high"]
        remedy_terms = intent_slots["remedy_high"]
        relation_low_terms = intent_slots["relation_low"]
        breach_low_terms = intent_slots["breach_low"]
        damage_low_terms = intent_slots["damage_low"]
        remedy_low_terms = intent_slots["remedy_low"]
        low_conf_limit = max(1, int(intent_slots.get("low_conf_limit", 2)))

        keyword_terms = [token for token in cls._split_tokens(keyword) if not cls._is_location_or_court_token(token)]
        summary_terms = cls._extract_summary_terms(case_summary)
        summary_relation_terms = [term for term in summary_terms if cls._looks_like_relation_term(term)]

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
        low_conf_pool = cls._dedupe_tokens(
            [*relation_low_terms, *breach_low_terms, *damage_low_terms, *remedy_low_terms],
            max_tokens=max(2, low_conf_limit * 2),
        )
        if low_conf_pool:
            query_parts.append([*keyword_terms[:2], *low_conf_pool[:low_conf_limit], *summary_terms[:2]])
        elif keyword_terms and summary_terms:
            query_parts.append([*keyword_terms[:3], *summary_terms[:3]])
        intent_pool = cls._dedupe_tokens(
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
                backend="siliconflow",
                model=(model or None),
                fallback=False,
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
            tokens = [token for token in cls._split_tokens(candidate) if not cls._is_location_or_court_token(token)]
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
    def _extract_intent_slots_with_confidence(cls, text: str) -> dict[str, list[str] | int]:
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

        for matched in re.findall(r"[\u4e00-\u9fffA-Za-z0-9]{2,16}合同", compact):
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

            # 高置信度: 同句命中多个提示词，或提示词+上下文长度足够。
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

    @classmethod
    def _load_intent_rule_overrides(cls) -> dict[str, list[str] | int]:
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

        # 命中极差时对当前检索式词项轻微降权，避免后续反馈扩展被噪声主导。
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
        tokens = re.findall(r"[\u4e00-\u9fffA-Za-z0-9]{2,12}", text)
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

    @classmethod
    def _reserve_new_items(cls, *, items: list[Any], seen_doc_ids: set[str]) -> tuple[list[Any], int]:
        unique_items: list[Any] = []
        duplicate_in_batch = 0
        for item in items:
            doc_id = cls._extract_item_doc_id(item)
            if doc_id and doc_id in seen_doc_ids:
                duplicate_in_batch += 1
                continue
            if doc_id:
                seen_doc_ids.add(doc_id)
            unique_items.append(item)
        return unique_items, duplicate_in_batch

    @classmethod
    def _fetch_case_detail_with_cache(
        cls,
        *,
        source_client: Any,
        session: Any,
        source: str,
        item: Any,
        task_id: str,
        local_cache: dict[str, CaseDetail],
        ttl_seconds: int,
    ) -> CaseDetail | None:
        doc_id = cls._extract_item_doc_id(item)
        cache_key = cls._build_case_detail_cache_key(source=source, doc_id=doc_id)
        if cache_key:
            cached = local_cache.get(cache_key)
            if cached is not None:
                return cached
            persistent = cls._load_case_detail_cache(cache_key)
            if persistent is not None:
                local_cache[cache_key] = persistent
                return persistent

        detail = cls._fetch_case_detail_with_retry(
            source_client=source_client,
            session=session,
            item=item,
            task_id=task_id,
        )
        if detail is None:
            return None
        if cache_key:
            local_cache[cache_key] = detail
            cls._save_case_detail_cache(cache_key=cache_key, detail=detail, ttl_seconds=ttl_seconds)
        return detail

    @classmethod
    def _build_case_detail_cache_key(cls, *, source: str, doc_id: str) -> str:
        source_name = str(source or "").strip().lower()
        doc_id_norm = str(doc_id or "").strip()
        if not source_name or not doc_id_norm:
            return ""
        return f"legal_research:detail:{source_name}:{doc_id_norm}"

    @classmethod
    def _load_case_detail_cache(cls, cache_key: str) -> CaseDetail | None:
        try:
            from django.core.cache import cache

            payload = cache.get(cache_key)
        except Exception:
            return None
        if not isinstance(payload, dict):
            return None
        return cls._deserialize_case_detail_payload(payload)

    @classmethod
    def _save_case_detail_cache(cls, *, cache_key: str, detail: CaseDetail, ttl_seconds: int) -> None:
        payload = cls._serialize_case_detail(detail)
        if not payload:
            return
        try:
            from django.core.cache import cache

            cache.set(cache_key, payload, timeout=max(60, int(ttl_seconds)))
        except Exception:
            return

    @staticmethod
    def _serialize_case_detail(detail: CaseDetail) -> dict[str, Any]:
        payload = {
            "doc_id_raw": str(getattr(detail, "doc_id_raw", "") or ""),
            "doc_id_unquoted": str(getattr(detail, "doc_id_unquoted", "") or ""),
            "detail_url": str(getattr(detail, "detail_url", "") or ""),
            "search_id": str(getattr(detail, "search_id", "") or ""),
            "module": str(getattr(detail, "module", "") or ""),
            "title": str(getattr(detail, "title", "") or ""),
            "court_text": str(getattr(detail, "court_text", "") or ""),
            "document_number": str(getattr(detail, "document_number", "") or ""),
            "judgment_date": str(getattr(detail, "judgment_date", "") or ""),
            "case_digest": str(getattr(detail, "case_digest", "") or ""),
            "content_text": str(getattr(detail, "content_text", "") or ""),
        }
        raw_meta = getattr(detail, "raw_meta", None)
        if isinstance(raw_meta, dict):
            payload["raw_meta"] = raw_meta
        return payload

    @staticmethod
    def _deserialize_case_detail_payload(payload: dict[str, Any]) -> CaseDetail | None:
        doc_id_raw = str(payload.get("doc_id_raw", "") or "")
        doc_id_unquoted = str(payload.get("doc_id_unquoted", "") or "")
        if not doc_id_raw and not doc_id_unquoted:
            return None
        return SimpleNamespace(
            doc_id_raw=doc_id_raw,
            doc_id_unquoted=doc_id_unquoted,
            detail_url=str(payload.get("detail_url", "") or ""),
            search_id=str(payload.get("search_id", "") or ""),
            module=str(payload.get("module", "") or ""),
            title=str(payload.get("title", "") or ""),
            court_text=str(payload.get("court_text", "") or ""),
            document_number=str(payload.get("document_number", "") or ""),
            judgment_date=str(payload.get("judgment_date", "") or ""),
            case_digest=str(payload.get("case_digest", "") or ""),
            content_text=str(payload.get("content_text", "") or ""),
            raw_meta=payload.get("raw_meta", {}),
        )

    @staticmethod
    def _extract_item_doc_id(item: Any) -> str:
        return str(getattr(item, "doc_id_unquoted", "") or getattr(item, "doc_id_raw", "")).strip()

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
        if re.fullmatch(r"[\u4e00-\u9fff]{2,12}(省|市|区|县|镇|乡)", value):
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

        extra_tokens = re.findall(r"[\u4e00-\u9fffA-Za-z0-9]{2,16}", text)
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
