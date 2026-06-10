"""LegalResearchExecutor tests with mocked external dependencies."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from apps.legal_research.services.task.executor import LegalResearchExecutor


class TestLegalResearchExecutorRun:
    """Test run() with heavily mocked dependencies."""

    @patch("apps.legal_research.services.task.executor.LegalResearchTuningConfig.load")
    @patch("apps.legal_research.services.task.executor.CaseSimilarityService")
    @patch("apps.legal_research.services.task.executor.get_case_source_client")
    def test_run_task_not_found(self, mock_get_client, mock_similarity, mock_tuning):
        executor = LegalResearchExecutor()
        with patch.object(executor, "_acquire_task", return_value=(None, None)):
            result = executor.run(task_id="nonexistent")
        assert result["status"] == "failed"
        assert "不存在" in result.get("error", "")

    @patch("apps.legal_research.services.task.executor.LegalResearchTuningConfig.load")
    @patch("apps.legal_research.services.task.executor.CaseSimilarityService")
    @patch("apps.legal_research.services.task.executor.get_case_source_client")
    def test_run_early_result(self, mock_get_client, mock_similarity, mock_tuning):
        executor = LegalResearchExecutor()
        early = {"task_id": "t1", "status": "completed"}
        with patch.object(executor, "_acquire_task", return_value=(None, early)):
            result = executor.run(task_id="t1")
        assert result["status"] == "completed"

    @patch("apps.legal_research.services.task.executor.LegalResearchTuningConfig.load")
    @patch("apps.legal_research.services.task.executor.CaseSimilarityService")
    @patch("apps.legal_research.services.task.executor.get_case_source_client")
    def test_run_exception_handling(self, mock_get_client, mock_similarity, mock_tuning):
        mock_tuning.return_value = MagicMock()
        mock_tuning.return_value.query_variant_enabled = False
        mock_tuning.return_value.element_extraction_enabled = False
        mock_tuning.return_value.feedback_query_limit = 0
        mock_tuning.return_value.feedback_min_terms = 1
        mock_tuning.return_value.feedback_min_score_floor = 0.3
        mock_tuning.return_value.feedback_score_margin = 0.1
        mock_tuning.return_value.detail_cache_ttl_seconds = 300
        mock_tuning.return_value.title_prefilter_enabled = False
        mock_tuning.return_value.llm_scoring_concurrency = 1

        mock_task = MagicMock()
        mock_task.id = "task-1"
        mock_task.keyword = "买卖合同"
        mock_task.case_summary = "纠纷"
        mock_task.source = "weike"
        mock_task.target_count = 1
        mock_task.max_candidates = 5
        mock_task.min_similarity_score = 0.5
        mock_task.llm_model = ""
        mock_task.llm_scoring_concurrency = 0
        mock_task.search_mode = "single"
        mock_task.search_url = ""
        mock_task.court_filter = ""
        mock_task.cause_of_action_filter = ""
        mock_task.date_from = ""
        mock_task.date_to = ""
        mock_task.advanced_query = None
        mock_task.credential = MagicMock()
        mock_task.credential.account = "test"
        mock_task.credential.password = "pass"
        mock_task.credential.url = None

        mock_client = MagicMock()
        mock_client.open_session.side_effect = RuntimeError("connection failed")
        mock_get_client.return_value = mock_client

        executor = LegalResearchExecutor()
        with patch.object(executor, "_acquire_task", return_value=(mock_task, None)):
            with patch.object(executor, "_is_cancel_requested", return_value=False):
                with patch.object(executor, "_mark_failed"):
                    result = executor.run(task_id="task-1")
        assert result["status"] == "failed"


class TestExecutorHelperMethods:
    """Test helper methods on the executor."""

    def test_init_query_metric(self):
        executor = LegalResearchExecutor()
        metric = executor._init_query_metric()
        assert isinstance(metric, dict)
        assert "candidates" in metric
        assert "scanned" in metric
        assert "matched" in metric
