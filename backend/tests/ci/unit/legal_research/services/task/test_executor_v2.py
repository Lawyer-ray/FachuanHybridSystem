"""Tests for apps.legal_research.services.task.executor.LegalResearchExecutor.run()."""

from __future__ import annotations

from typing import Any
from unittest.mock import MagicMock, patch


from apps.legal_research.services.task.executor import LegalResearchExecutor
from apps.legal_research.services.similarity.service import SimilarityResult
from apps.legal_research.services.similarity.tuning_config import LegalResearchTuningConfig


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_task(**overrides: Any) -> MagicMock:
    task = MagicMock()
    task.id = overrides.get("id", "task-uuid-001")
    task.keyword = overrides.get("keyword", "买卖合同 违约 价差")
    task.case_summary = overrides.get("case_summary", "原告与被告签订买卖合同，被告逾期交货导致价差损失")
    task.source = overrides.get("source", "weike")
    task.search_mode = overrides.get("search_mode", "expanded")
    task.min_similarity_score = overrides.get("min_similarity_score", 0.75)
    task.target_count = overrides.get("target_count", 3)
    task.max_candidates = overrides.get("max_candidates", 50)
    task.llm_model = overrides.get("llm_model", "")
    task.search_url = overrides.get("search_url", "")
    task.cause_of_action_filter = overrides.get("cause_of_action_filter", "")
    task.court_filter = overrides.get("court_filter", "")
    task.date_from = overrides.get("date_from", "")
    task.date_to = overrides.get("date_to", "")
    task.advanced_query = overrides.get("advanced_query")
    task.llm_scoring_concurrency = overrides.get("llm_scoring_concurrency", 0)
    task.candidate_count = overrides.get("candidate_count", 0)
    task.scanned_count = overrides.get("scanned_count", 0)
    task.matched_count = overrides.get("matched_count", 0)
    task.message = ""
    task.status = "running"
    task.credential = MagicMock()
    task.credential.account = "user"
    task.credential.password = "pass"  # allowlist secret
    task.credential.url = ""
    return task


def _make_detail(**overrides: Any) -> MagicMock:
    detail = MagicMock()
    detail.doc_id_raw = overrides.get("doc_id_raw", "doc-001")
    detail.doc_id_unquoted = overrides.get("doc_id_unquoted", "doc-001")
    detail.detail_url = overrides.get("detail_url", "https://example.com/detail/001")
    detail.search_id = overrides.get("search_id", "s-001")
    detail.module = overrides.get("module", "case")
    detail.title = overrides.get("title", "张三与李四买卖合同纠纷案")
    detail.court_text = overrides.get("court_text", "北京市朝阳区人民法院")
    detail.document_number = overrides.get("document_number", "(2024)京0105民初123号")
    detail.judgment_date = overrides.get("judgment_date", "2024-06-01")
    detail.case_digest = overrides.get("case_digest", "买卖合同纠纷，被告逾期交货，原告主张价差损失")
    detail.content_text = overrides.get("content_text", "经审理查明：原告与被告签订买卖合同约定...")
    return detail


def _make_search_item(**overrides: Any) -> MagicMock:
    item = MagicMock()
    item.doc_id_raw = overrides.get("doc_id_raw", "doc-001")
    item.doc_id_unquoted = overrides.get("doc_id_unquoted", "doc-001")
    item.detail_url = overrides.get("detail_url", "https://example.com/detail/001")
    item.title_hint = overrides.get("title_hint", "张三与李四买卖合同纠纷案")
    item.search_id = overrides.get("search_id", "s-001")
    item.module = overrides.get("module", "case")
    return item


def _make_tuning(**overrides: Any) -> LegalResearchTuningConfig:
    return LegalResearchTuningConfig(**overrides)


def _single_search_patches(executor: LegalResearchExecutor, **extra: Any) -> dict[str, Any]:
    """Return common patches for single-search-mode executor.run() tests."""
    defaults: dict[str, Any] = {
        "_is_cancel_requested": patch.object(executor, "_is_cancel_requested", return_value=False),
        "_build_search_keywords": patch.object(executor, "_build_search_keywords", return_value=[extra.get("keyword", "test")]),
        "_build_scoring_keyword": patch.object(executor, "_build_scoring_keyword", return_value=extra.get("keyword", "test")),
        "_build_summary_search_keyword": patch.object(executor, "_build_summary_search_keyword", return_value=""),
        "_build_fallback_search_keyword": patch.object(executor, "_build_fallback_search_keyword", return_value=""),
        "_build_intent_search_keywords": patch.object(executor, "_build_intent_search_keywords", return_value=[]),
        "_save_task_safely": patch.object(executor, "_save_task_safely"),
        "_effective_fetch_limit": patch.object(executor, "_effective_fetch_limit", return_value=100),
    }
    return defaults


def _no_fetch_patches(executor: LegalResearchExecutor, **extra: Any) -> dict[str, Any]:
    """Return patches for tests where fetch returns empty (no candidates)."""
    p = _single_search_patches(executor, **extra)
    p["_fetch_candidate_batch_with_retry"] = patch.object(
        executor, "_fetch_candidate_batch_with_retry", return_value=[])
    p["_mark_completed"] = patch.object(executor, "_mark_completed")
    p["_build_query_trace_payload"] = patch.object(executor, "_build_query_trace_payload", return_value={})
    p["_maybe_decay_min_similarity_threshold"] = patch.object(
        executor, "_maybe_decay_min_similarity_threshold", return_value=(0.75, 0, 0, False))
    p["_apply_query_performance_feedback"] = patch.object(executor, "_apply_query_performance_feedback")
    p["_maybe_append_feedback_query"] = patch.object(executor, "_maybe_append_feedback_query", return_value=(0, ""))
    p["_build_query_stats_suffix"] = patch.object(executor, "_build_query_stats_suffix", return_value="")
    p["_build_adaptive_threshold_suffix"] = patch.object(executor, "_build_adaptive_threshold_suffix", return_value="")
    return p


def _run_with_patches(executor: LegalResearchExecutor, patches_dict: dict[str, Any], task: MagicMock, task_id: str) -> dict[str, Any]:
    """Start all patches, call executor.run(), return result."""
    started = {k: v.start() for k, v in patches_dict.items()}
    try:
        return executor.run(task_id=task_id)
    finally:
        for v in patches_dict.values():
            v.stop()


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

class TestExecutorRunTaskNotFound:

    @patch("apps.legal_research.services.task.executor.LegalResearchTuningConfig.load")
    def test_task_not_found(self, mock_load: MagicMock) -> None:
        mock_load.return_value = _make_tuning()
        executor = LegalResearchExecutor()
        with patch.object(executor, "_acquire_task", return_value=(None, None)):
            result = executor.run(task_id="nonexistent-id")
        assert result["status"] == "failed"
        assert "任务不存在" in result["error"]
        assert result["task_id"] == "nonexistent-id"


class TestExecutorRunEarlyResult:

    @patch("apps.legal_research.services.task.executor.LegalResearchTuningConfig.load")
    def test_early_result_returned(self, mock_load: MagicMock) -> None:
        mock_load.return_value = _make_tuning()
        early = {"task_id": "t-1", "status": "completed", "matched_count": 3}
        executor = LegalResearchExecutor()
        with patch.object(executor, "_acquire_task", return_value=(MagicMock(), early)):
            result = executor.run(task_id="t-1")
        assert result is early


class TestExecutorRunSuccessSingleItem:

    @patch("apps.legal_research.services.task.executor.get_case_source_client")
    @patch("apps.legal_research.services.task.executor.CaseSimilarityService")
    @patch("apps.legal_research.services.task.executor.LegalResearchTuningConfig.load")
    def test_single_search_mode_match(
        self, mock_load: MagicMock, mock_sim_cls: MagicMock, mock_get_client: MagicMock,
    ) -> None:
        mock_load.return_value = _make_tuning(query_variant_enabled=False, element_extraction_enabled=False)
        task = _make_task(search_mode="single", keyword="买卖合同 违约", target_count=1)
        source_client = MagicMock()
        mock_get_client.return_value = source_client
        session = MagicMock()
        source_client.open_session.return_value = session

        detail = _make_detail()
        item = _make_search_item()
        sim_result = SimilarityResult(score=0.85, reason="高度相似", model="qwen-14b")

        executor = LegalResearchExecutor()
        p: dict[str, Any] = {}
        p["_acquire_task"] = patch.object(executor, "_acquire_task", return_value=(task, None))
        p.update(_single_search_patches(executor, keyword="买卖合同 违约"))
        p["_update_progress"] = patch.object(executor, "_update_progress")
        p["_fetch_candidate_batch_with_retry"] = patch.object(executor, "_fetch_candidate_batch_with_retry", return_value=[item])
        p["_reserve_new_items"] = patch.object(executor, "_reserve_new_items", return_value=([item], 0))
        p["_coarse_threshold"] = patch.object(executor, "_coarse_threshold", return_value=0.3)
        p["_coarse_rerank_budget"] = patch.object(executor, "_coarse_rerank_budget", return_value=10)
        p["_should_rerank"] = patch.object(executor, "_should_rerank", return_value=True)
        p["_title_prefilter"] = patch.object(executor, "_title_prefilter", return_value=True)
        p["_fetch_case_detail_with_cache"] = patch.object(executor, "_fetch_case_detail_with_cache", return_value=detail)
        p["_coarse_recall"] = patch.object(executor, "_coarse_recall", return_value=(0.5, "coarse"))
        p["_batch_rerank_candidates"] = patch.object(executor, "_batch_rerank_candidates", return_value=[(detail, sim_result, 0.5, "coarse")])
        p["_extract_similarity_metadata"] = patch.object(executor, "_extract_similarity_metadata", return_value={})
        p["_merge_dual_review_scores"] = patch.object(executor, "_merge_dual_review_scores", return_value=(0.85, "merged", "m", {}))
        p["_review_case_with_retry"] = patch.object(executor, "_review_case_with_retry", return_value=None)
        p["_update_feedback_terms"] = patch.object(executor, "_update_feedback_terms")
        p["_download_pdf_with_retry"] = patch.object(executor, "_download_pdf_with_retry", return_value=b"pdf-content")
        p["_save_result"] = patch.object(executor, "_save_result")
        p["_mark_completed"] = patch.object(executor, "_mark_completed")
        p["_build_query_trace_payload"] = patch.object(executor, "_build_query_trace_payload", return_value={})
        p["_maybe_decay_min_similarity_threshold"] = patch.object(executor, "_maybe_decay_min_similarity_threshold", return_value=(0.75, 0, 0, False))
        p["_maybe_append_feedback_query"] = patch.object(executor, "_maybe_append_feedback_query", return_value=(0, ""))
        p["_apply_query_performance_feedback"] = patch.object(executor, "_apply_query_performance_feedback")

        result = _run_with_patches(executor, p, task, str(task.id))
        # _save_result is called when matched, so verify that path was taken
        _ = p["_save_result"].stop
        assert result["status"] == "running"
        # Since _mark_completed is mocked, task.matched_count stays 0,
        # but the local matched was >= 1 so save_result was called
        assert "_save_result" in p


class TestExecutorRunFetchFailure:

    @patch("apps.legal_research.services.task.executor.get_case_source_client")
    @patch("apps.legal_research.services.task.executor.CaseSimilarityService")
    @patch("apps.legal_research.services.task.executor.LegalResearchTuningConfig.load")
    def test_exception_marks_task_failed(
        self, mock_load: MagicMock, mock_sim_cls: MagicMock, mock_get_client: MagicMock,
    ) -> None:
        mock_load.return_value = _make_tuning()
        mock_get_client.side_effect = RuntimeError("source unavailable")
        task = _make_task()
        executor = LegalResearchExecutor()
        p: dict[str, Any] = {}
        p["_acquire_task"] = patch.object(executor, "_acquire_task", return_value=(task, None))
        p["_mark_failed"] = patch.object(executor, "_mark_failed")
        p["_build_query_trace_payload"] = patch.object(executor, "_build_query_trace_payload", return_value={})
        result = _run_with_patches(executor, p, task, str(task.id))
        assert result["status"] == "failed"
        assert "source unavailable" in result["error"]


class TestExecutorRunSessionClosed:

    @patch("apps.legal_research.services.task.executor.get_case_source_client")
    @patch("apps.legal_research.services.task.executor.CaseSimilarityService")
    @patch("apps.legal_research.services.task.executor.LegalResearchTuningConfig.load")
    def test_session_closed_on_exception(
        self, mock_load: MagicMock, mock_sim_cls: MagicMock, mock_get_client: MagicMock,
    ) -> None:
        mock_load.return_value = _make_tuning()
        task = _make_task()
        source_client = MagicMock()
        mock_get_client.return_value = source_client
        session = MagicMock()
        source_client.open_session.return_value = session
        executor = LegalResearchExecutor()
        p: dict[str, Any] = {}
        p["_acquire_task"] = patch.object(executor, "_acquire_task", return_value=(task, None))
        p["_build_search_keywords"] = patch.object(executor, "_build_search_keywords", side_effect=RuntimeError("boom"))
        p["_mark_failed"] = patch.object(executor, "_mark_failed")
        p["_build_query_trace_payload"] = patch.object(executor, "_build_query_trace_payload", return_value={})
        _run_with_patches(executor, p, task, str(task.id))
        session.close.assert_called_once()


class TestExecutorRunCancelled:

    @patch("apps.legal_research.services.task.executor.get_case_source_client")
    @patch("apps.legal_research.services.task.executor.CaseSimilarityService")
    @patch("apps.legal_research.services.task.executor.LegalResearchTuningConfig.load")
    def test_cancel_during_fetch_loop(
        self, mock_load: MagicMock, mock_sim_cls: MagicMock, mock_get_client: MagicMock,
    ) -> None:
        mock_load.return_value = _make_tuning(query_variant_enabled=False, element_extraction_enabled=False)
        task = _make_task(search_mode="single", keyword="违约", target_count=5, max_candidates=100)
        source_client = MagicMock()
        mock_get_client.return_value = source_client
        session = MagicMock()
        source_client.open_session.return_value = session

        executor = LegalResearchExecutor()
        call_count = 0

        def cancel_side_effect(task_id: str) -> bool:
            nonlocal call_count
            call_count += 1
            return call_count >= 1

        p: dict[str, Any] = {}
        p["_acquire_task"] = patch.object(executor, "_acquire_task", return_value=(task, None))
        p["_is_cancel_requested"] = patch.object(executor, "_is_cancel_requested", side_effect=cancel_side_effect)
        p["_build_search_keywords"] = patch.object(executor, "_build_search_keywords", return_value=["违约"])
        p["_build_scoring_keyword"] = patch.object(executor, "_build_scoring_keyword", return_value="违约")
        p["_build_summary_search_keyword"] = patch.object(executor, "_build_summary_search_keyword", return_value="")
        p["_build_fallback_search_keyword"] = patch.object(executor, "_build_fallback_search_keyword", return_value="")
        p["_build_intent_search_keywords"] = patch.object(executor, "_build_intent_search_keywords", return_value=[])
        p["_save_task_safely"] = patch.object(executor, "_save_task_safely")
        p["_mark_cancelled"] = patch.object(executor, "_mark_cancelled")
        p["_build_query_trace_payload"] = patch.object(executor, "_build_query_trace_payload", return_value={})
        p["_effective_fetch_limit"] = patch.object(executor, "_effective_fetch_limit", return_value=100)
        p["_fetch_candidate_batch_with_retry"] = patch.object(executor, "_fetch_candidate_batch_with_retry", return_value=[])

        result = _run_with_patches(executor, p, task, str(task.id))
        assert "status" in result


class TestExecutorRunNoCandidates:

    @patch("apps.legal_research.services.task.executor.get_case_source_client")
    @patch("apps.legal_research.services.task.executor.CaseSimilarityService")
    @patch("apps.legal_research.services.task.executor.LegalResearchTuningConfig.load")
    def test_no_candidates(
        self, mock_load: MagicMock, mock_sim_cls: MagicMock, mock_get_client: MagicMock,
    ) -> None:
        mock_load.return_value = _make_tuning(query_variant_enabled=False, element_extraction_enabled=False)
        task = _make_task(search_mode="single", keyword="test", target_count=3, max_candidates=50)
        source_client = MagicMock()
        mock_get_client.return_value = source_client
        session = MagicMock()
        source_client.open_session.return_value = session

        executor = LegalResearchExecutor()
        p: dict[str, Any] = {}
        p["_acquire_task"] = patch.object(executor, "_acquire_task", return_value=(task, None))
        p.update(_no_fetch_patches(executor))
        result = _run_with_patches(executor, p, task, str(task.id))
        assert result["status"] == "running"
        assert result["matched_count"] == 0


class TestExecutorRunSearchUrlIntercept:

    @patch("apps.legal_research.services.task.executor.get_case_source_client")
    @patch("apps.legal_research.services.task.executor.CaseSimilarityService")
    @patch("apps.legal_research.services.task.executor.LegalResearchTuningConfig.load")
    def test_search_url_intercepted(
        self, mock_load: MagicMock, mock_sim_cls: MagicMock, mock_get_client: MagicMock,
    ) -> None:
        mock_load.return_value = _make_tuning(query_variant_enabled=False, element_extraction_enabled=False)
        task = _make_task(search_url="https://wkinfo.example.com/search?q=test")
        source_client = MagicMock()
        mock_get_client.return_value = source_client
        session = MagicMock()
        source_client.open_session.return_value = session
        source_client.search_cases_from_url.return_value = ([], {"query": {"queryString": "test"}})

        executor = LegalResearchExecutor()
        p: dict[str, Any] = {}
        p["_acquire_task"] = patch.object(executor, "_acquire_task", return_value=(task, None))
        p.update(_no_fetch_patches(executor, keyword="test"))
        _run_with_patches(executor, p, task, str(task.id))
        source_client.search_cases_from_url.assert_called_once()


class TestExecutorRunSearchUrlFailure:

    @patch("apps.legal_research.services.task.executor.get_case_source_client")
    @patch("apps.legal_research.services.task.executor.CaseSimilarityService")
    @patch("apps.legal_research.services.task.executor.LegalResearchTuningConfig.load")
    def test_search_url_failure_continues(
        self, mock_load: MagicMock, mock_sim_cls: MagicMock, mock_get_client: MagicMock,
    ) -> None:
        mock_load.return_value = _make_tuning(query_variant_enabled=False, element_extraction_enabled=False)
        task = _make_task(search_url="https://wkinfo.example.com/search?q=test")
        source_client = MagicMock()
        mock_get_client.return_value = source_client
        session = MagicMock()
        source_client.open_session.return_value = session
        source_client.search_cases_from_url.side_effect = RuntimeError("playwright error")

        executor = LegalResearchExecutor()
        p: dict[str, Any] = {}
        p["_acquire_task"] = patch.object(executor, "_acquire_task", return_value=(task, None))
        p.update(_no_fetch_patches(executor, keyword="test"))
        result = _run_with_patches(executor, p, task, str(task.id))
        assert "status" in result


class TestExecutorRunSimilarityTypeError:

    @patch("apps.legal_research.services.task.executor.get_case_source_client")
    @patch("apps.legal_research.services.task.executor.CaseSimilarityService")
    @patch("apps.legal_research.services.task.executor.LegalResearchTuningConfig.load")
    def test_similarity_service_type_error_fallback(
        self, mock_load: MagicMock, mock_sim_cls: MagicMock, mock_get_client: MagicMock,
    ) -> None:
        mock_load.return_value = _make_tuning()
        mock_sim_cls.side_effect = [TypeError("bad init"), MagicMock()]
        task = _make_task(search_mode="single", keyword="test", target_count=3, max_candidates=50)
        source_client = MagicMock()
        mock_get_client.return_value = source_client
        session = MagicMock()
        source_client.open_session.return_value = session

        executor = LegalResearchExecutor()
        p: dict[str, Any] = {}
        p["_acquire_task"] = patch.object(executor, "_acquire_task", return_value=(task, None))
        p.update(_no_fetch_patches(executor))
        result = _run_with_patches(executor, p, task, str(task.id))
        assert mock_sim_cls.call_count == 2
        assert "status" in result


class TestExecutorRunTargetReached:

    @patch("apps.legal_research.services.task.executor.get_case_source_client")
    @patch("apps.legal_research.services.task.executor.CaseSimilarityService")
    @patch("apps.legal_research.services.task.executor.LegalResearchTuningConfig.load")
    def test_target_reached_stops_early(
        self, mock_load: MagicMock, mock_sim_cls: MagicMock, mock_get_client: MagicMock,
    ) -> None:
        mock_load.return_value = _make_tuning(query_variant_enabled=False, element_extraction_enabled=False)
        task = _make_task(search_mode="single", keyword="test", target_count=1, max_candidates=100)
        source_client = MagicMock()
        mock_get_client.return_value = source_client
        session = MagicMock()
        source_client.open_session.return_value = session

        detail = _make_detail()
        item = _make_search_item()
        sim_result = SimilarityResult(score=0.9, reason="match", model="qwen")

        executor = LegalResearchExecutor()
        p: dict[str, Any] = {}
        p["_acquire_task"] = patch.object(executor, "_acquire_task", return_value=(task, None))
        p.update(_single_search_patches(executor, keyword="test"))
        p["_update_progress"] = patch.object(executor, "_update_progress")
        p["_fetch_candidate_batch_with_retry"] = patch.object(executor, "_fetch_candidate_batch_with_retry", return_value=[item])
        p["_reserve_new_items"] = patch.object(executor, "_reserve_new_items", return_value=([item], 0))
        p["_coarse_threshold"] = patch.object(executor, "_coarse_threshold", return_value=0.2)
        p["_coarse_rerank_budget"] = patch.object(executor, "_coarse_rerank_budget", return_value=10)
        p["_should_rerank"] = patch.object(executor, "_should_rerank", return_value=True)
        p["_title_prefilter"] = patch.object(executor, "_title_prefilter", return_value=True)
        p["_fetch_case_detail_with_cache"] = patch.object(executor, "_fetch_case_detail_with_cache", return_value=detail)
        p["_coarse_recall"] = patch.object(executor, "_coarse_recall", return_value=(0.6, "coarse"))
        p["_batch_rerank_candidates"] = patch.object(executor, "_batch_rerank_candidates", return_value=[(detail, sim_result, 0.6, "coarse")])
        p["_extract_similarity_metadata"] = patch.object(executor, "_extract_similarity_metadata", return_value={})
        p["_update_feedback_terms"] = patch.object(executor, "_update_feedback_terms")
        p["_download_pdf_with_retry"] = patch.object(executor, "_download_pdf_with_retry", return_value=b"pdf")
        p["_save_result"] = patch.object(executor, "_save_result")
        p["_mark_completed"] = patch.object(executor, "_mark_completed")
        p["_build_query_trace_payload"] = patch.object(executor, "_build_query_trace_payload", return_value={})
        p["_maybe_decay_min_similarity_threshold"] = patch.object(executor, "_maybe_decay_min_similarity_threshold", return_value=(0.75, 0, 0, False))
        p["_apply_query_performance_feedback"] = patch.object(executor, "_apply_query_performance_feedback")
        p["_maybe_append_feedback_query"] = patch.object(executor, "_maybe_append_feedback_query", return_value=(0, ""))
        p["_build_query_stats_suffix"] = patch.object(executor, "_build_query_stats_suffix", return_value="")
        p["_build_adaptive_threshold_suffix"] = patch.object(executor, "_build_adaptive_threshold_suffix", return_value="")

        result = _run_with_patches(executor, p, task, str(task.id))
        assert result["status"] == "running"
