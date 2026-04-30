from __future__ import annotations

import logging
import re
from typing import Any

from apps.legal_research.models import LegalResearchSearchMode, LegalResearchTask
from apps.legal_research.services.executor_components import (
    ExecutorCacheMixin,
    ExecutorFeedbackMixin,
    ExecutorIntentMixin,
    ExecutorPolicyMixin,
    ExecutorQueryMixin,
    ExecutorResultPersistenceMixin,
    ExecutorScoringMixin,
    ExecutorSourceGatewayMixin,
    ExecutorTaskLifecycleMixin,
)
from apps.legal_research.services.executor_components.policy_mixin import (
    AdaptiveThresholdPolicy,
    DualReviewPolicy,
)
from apps.legal_research.services.similarity_service import CaseSimilarityService
from apps.legal_research.services.sources import get_case_source_client
from apps.legal_research.services.tuning_config import LegalResearchTuningConfig

logger = logging.getLogger(__name__)

# 向后兼容别名 — run() 中的类型注解使用下划线前缀名称
_DualReviewPolicy = DualReviewPolicy
_AdaptiveThresholdPolicy = AdaptiveThresholdPolicy


class LegalResearchExecutor(
    ExecutorTaskLifecycleMixin,
    ExecutorSourceGatewayMixin,
    ExecutorResultPersistenceMixin,
    ExecutorPolicyMixin,
    ExecutorCacheMixin,
    ExecutorFeedbackMixin,
    ExecutorScoringMixin,
    ExecutorQueryMixin,
    ExecutorIntentMixin,
):
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
            # ── [3] AI 自动提取关键检索要素 ──
            element_extraction_enabled = bool(getattr(tuning, "element_extraction_enabled", True))
            if (not single_search_mode) and element_extraction_enabled:
                element_model = str(getattr(tuning, "element_extraction_model", "") or "").strip()
                element_timeout = max(5, int(getattr(tuning, "element_extraction_timeout_seconds", 20)))
                elements = self._extract_legal_elements(
                    case_summary=task.case_summary,
                    model=(element_model or task.llm_model or None),
                    timeout_seconds=element_timeout,
                )
                if elements:
                    element_queries = self._build_element_based_queries(elements)
                    if element_queries:
                        keyword_candidates = self._merge_query_candidates(element_queries, keyword_candidates)
                        logger.info("法律要素检索式: %s", element_queries, extra={"task_id": str(task.id)})
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
            # ── 新配置项 ──
            title_prefilter_enabled = bool(getattr(tuning, "title_prefilter_enabled", True))
            title_prefilter_min_overlap = max(
                0.0, float(getattr(tuning, "title_prefilter_min_overlap", self.TITLE_PREFILTER_MIN_OVERLAP))
            )
            coarse_recall_hard_floor = max(0.0, float(getattr(tuning, "coarse_recall_hard_floor", 0.20)))
            llm_scoring_concurrency = max(
                1, int(getattr(tuning, "llm_scoring_concurrency", self.LLM_SCORING_CONCURRENCY))
            )
            feedback_term_weights: dict[str, int] = {}
            feedback_queries_added = 0
            detail_cache_local: dict[str, Any] = {}

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
                        advanced_query=getattr(task, "advanced_query", None) or None,
                        court_filter=str(getattr(task, "court_filter", "") or ""),
                        cause_of_action_filter=str(getattr(task, "cause_of_action_filter", "") or ""),
                        date_from=str(getattr(task, "date_from", "") or ""),
                        date_to=str(getattr(task, "date_to", "") or ""),
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
                    deferred_candidates: list[tuple[Any, float, str]] = []
                    # ── [4] 候选预筛 + 宽召回 → 收集待评分批次 ──
                    pending_rerank: list[tuple[Any, float, str]] = []
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

                        # ── [4] 标题预筛 ──
                        if title_prefilter_enabled:
                            title_hint = getattr(item, "title_hint", "") or ""
                            if not self._title_prefilter(
                                keyword=task.keyword,
                                case_summary=task.case_summary,
                                title_hint=title_hint,
                                min_overlap=title_prefilter_min_overlap,
                            ):
                                skipped += 1
                                query_metric["skipped"] = query_metric.get("skipped", 0) + 1
                                continue

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
                            query_metric["skipped"] = query_metric.get("skipped", 0) + 1
                            self._update_progress(task=task, scanned=scanned, matched=matched, skipped=skipped)
                            continue

                        scanned += 1
                        query_metric["scanned"] += 1

                        # ── [2] 宽召回（更激进过滤）──
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
                            continue
                        rerank_used += 1
                        pending_rerank.append((detail, coarse_score, coarse_reason))

                    # ── [1] 并发 LLM 评分 ──
                    if pending_rerank and matched < task.target_count:
                        if self._is_cancel_requested(task.id):
                            self._mark_cancelled(task=task, scanned=scanned, matched=matched, skipped=skipped)
                            return {
                                "task_id": str(task.id),
                                "status": task.status,
                                "scanned_count": scanned,
                                "matched_count": matched,
                                "skipped_count": skipped,
                            }
                        task.message = f"正在并发评分 {len(pending_rerank)} 篇候选（{llm_scoring_concurrency} 并发）"
                        self._save_task_safely(task, update_fields=["message", "updated_at"])

                        scored_results = self._batch_rerank_candidates(
                            candidates=pending_rerank,
                            similarity=similarity,
                            task=task,
                            task_id=str(task.id),
                            concurrency=llm_scoring_concurrency,
                        )
                        for detail, sim, coarse_score, coarse_reason in scored_results:
                            if matched >= task.target_count:
                                break
                            if not task.llm_model and sim.model:
                                task.llm_model = sim.model

                            # 近阈值复判
                            if sim.score < effective_min_similarity_threshold and sim.score >= max(
                                0.0, effective_min_similarity_threshold - self.BORDERLINE_RECHECK_GAP
                            ):
                                rescored = self._rescore_borderline_with_retry(
                                    similarity=similarity,
                                    task=task,
                                    detail=detail,
                                    first_score=sim.score,
                                    first_reason=sim.reason,
                                    task_id=str(task.id),
                                )
                                if rescored is not None and rescored.score > sim.score:
                                    sim = rescored

                            # 双模型复核
                            dual_review_metadata: dict[str, Any] | None = None
                            similarity_metadata = self._extract_similarity_metadata(similarity=sim)
                            if (
                                dual_review_policy.enabled
                                and sim.score >= dual_review_policy.trigger_floor
                                and str(getattr(sim, "model", "") or "").strip() != dual_review_policy.review_model
                            ):
                                reviewed = self._review_case_with_retry(
                                    similarity=similarity,
                                    task=task,
                                    detail=detail,
                                    task_id=str(task.id),
                                    review_model=dual_review_policy.review_model,
                                    primary_score=sim.score,
                                    primary_reason=sim.reason,
                                )
                                if reviewed is not None:
                                    merged_score, merged_reason, merged_model, dual_review_metadata = (
                                        self._merge_dual_review_scores(
                                            primary=sim,
                                            reviewed=reviewed,
                                            dual_review_policy=dual_review_policy,
                                        )
                                    )
                                    sim.score = merged_score
                                    sim.reason = merged_reason
                                    sim.model = merged_model

                            # 反馈更新
                            self._update_feedback_terms(
                                feedback_term_weights=feedback_term_weights,
                                detail=detail,
                                reason=sim.reason,
                                similarity_score=sim.score,
                                min_similarity=effective_min_similarity_threshold,
                                feedback_min_score_floor=feedback_min_score_floor,
                                feedback_score_margin=feedback_score_margin,
                            )

                            if sim.score < effective_min_similarity_threshold:
                                continue

                            # 命中 → 下载 PDF
                            pdf = self._download_pdf_with_retry(
                                source_client=source_client,
                                session=session,
                                detail=detail,
                                task_id=str(task.id),
                            )
                            if pdf is None:
                                skipped += 1
                                continue

                            matched += 1
                            query_metric["matched"] += 1
                            merged_metadata: dict[str, Any] | None = None
                            if similarity_metadata or dual_review_metadata:
                                merged_metadata = {}
                                if similarity_metadata:
                                    merged_metadata.update(similarity_metadata)
                                if dual_review_metadata:
                                    merged_metadata.update(dual_review_metadata)
                            self._save_result(
                                task=task,
                                detail=detail,
                                similarity=sim,
                                rank=matched,
                                pdf=pdf,
                                coarse_score=coarse_score,
                                coarse_reason=coarse_reason,
                                extra_metadata=merged_metadata,
                            )

                        # 批量评分后更新反馈检索式
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
                            if feedback_query and feedback_query not in feedback_queries:
                                feedback_queries.append(feedback_query)

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
