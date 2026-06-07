"""Coverage tests for legal_research benchmark command and related services."""
from __future__ import annotations

import json
import math
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest


# --- benchmark_legal_research_retrieval ---

class TestBenchmarkCommandHelpers:
    """Test static/classmethods of benchmark command."""

    def test_init_query_type_metric(self):
        from apps.legal_research.management.commands.benchmark_legal_research_retrieval import Command

        result = Command._init_query_type_metric()
        assert isinstance(result, dict)
        assert "total_cases" in result
        assert result["total_cases"] == 0

    def test_normalize_query_type_primary(self):
        from apps.legal_research.management.commands.benchmark_legal_research_retrieval import Command

        assert Command._normalize_query_type("primary") == Command.QUERY_TYPE_PRIMARY
        assert Command._normalize_query_type("main") == Command.QUERY_TYPE_PRIMARY

    def test_normalize_query_type_expansion(self):
        from apps.legal_research.management.commands.benchmark_legal_research_retrieval import Command

        assert Command._normalize_query_type("expansion") == Command.QUERY_TYPE_EXPANSION

    def test_normalize_query_type_feedback(self):
        from apps.legal_research.management.commands.benchmark_legal_research_retrieval import Command

        assert Command._normalize_query_type("feedback") == Command.QUERY_TYPE_FEEDBACK

    def test_normalize_query_type_other(self):
        from apps.legal_research.management.commands.benchmark_legal_research_retrieval import Command

        assert Command._normalize_query_type("unknown") == Command.QUERY_TYPE_OTHER
        assert Command._normalize_query_type(None) == Command.QUERY_TYPE_OTHER
        assert Command._normalize_query_type("") == Command.QUERY_TYPE_OTHER

    def test_normalize_evaluation_mode(self):
        from apps.legal_research.management.commands.benchmark_legal_research_retrieval import Command

        assert Command._normalize_evaluation_mode("closed") == Command.EVAL_MODE_CLOSED
        assert Command._normalize_evaluation_mode("pooled") == Command.EVAL_MODE_POOLED
        assert Command._normalize_evaluation_mode("invalid") == Command.EVAL_MODE_POOLED
        assert Command._normalize_evaluation_mode(None) == Command.EVAL_MODE_POOLED

    def test_normalize_eval_top_k(self):
        from apps.legal_research.management.commands.benchmark_legal_research_retrieval import Command

        assert Command._normalize_eval_top_k(20) == 20
        assert Command._normalize_eval_top_k(0) == 0
        assert Command._normalize_eval_top_k(-5) == 0
        assert Command._normalize_eval_top_k(None) == 0
        assert Command._normalize_eval_top_k("abc") == 0

    def test_to_str_list(self):
        from apps.legal_research.management.commands.benchmark_legal_research_retrieval import Command

        assert Command._to_str_list(["a", "b"]) == ["a", "b"]
        assert Command._to_str_list(None) == []
        assert Command._to_str_list("not a list") == []
        assert Command._to_str_list(["  ", "a"]) == ["a"]

    def test_compute_prf(self):
        from apps.legal_research.management.commands.benchmark_legal_research_retrieval import Command

        p, r, f1 = Command._compute_prf(tp=5, fp=5, fn=5)
        assert abs(p - 0.5) < 0.001
        assert abs(r - 0.5) < 0.001
        assert abs(f1 - 0.5) < 0.001

    def test_compute_prf_zero(self):
        from apps.legal_research.management.commands.benchmark_legal_research_retrieval import Command

        p, r, f1 = Command._compute_prf(tp=0, fp=0, fn=0)
        assert p == 0.0
        assert r == 0.0
        assert f1 == 0.0

    def test_count_confusion(self):
        from apps.legal_research.management.commands.benchmark_legal_research_retrieval import Command

        tp, fp, fn = Command._count_confusion(
            predicted_doc_ids=["a", "b", "c"],
            expected_doc_ids=["b", "c", "d"],
        )
        assert tp == 2
        assert fp == 1
        assert fn == 1

    def test_parse_relevance_judgments_dict(self):
        from apps.legal_research.management.commands.benchmark_legal_research_retrieval import Command

        result = Command._parse_relevance_judgments({"doc1": 2, "doc2": 0})
        assert result["doc1"] == 2
        assert result["doc2"] == 0

    def test_parse_relevance_judgments_list(self):
        from apps.legal_research.management.commands.benchmark_legal_research_retrieval import Command

        result = Command._parse_relevance_judgments([{"doc_id": "d1", "grade": 1}, "d2"])
        assert result["d1"] == 1
        assert result["d2"] == 1

    def test_normalize_relevance_grade(self):
        from apps.legal_research.management.commands.benchmark_legal_research_retrieval import Command

        assert Command._normalize_relevance_grade(2) == 2
        assert Command._normalize_relevance_grade("high") == 2
        assert Command._normalize_relevance_grade("partial") == 1
        assert Command._normalize_relevance_grade("irrelevant") == 0
        assert Command._normalize_relevance_grade(None) is None
        assert Command._normalize_relevance_grade(True) == 1
        assert Command._normalize_relevance_grade(False) == 0

    def test_compute_ndcg_at_k(self):
        from apps.legal_research.management.commands.benchmark_legal_research_retrieval import Command

        result = Command._compute_ndcg_at_k(
            predicted=["a", "b", "c"],
            relevance_map={"a": 2, "b": 1, "c": 0},
            top_k=3,
        )
        assert 0.0 <= result <= 1.0

    def test_compute_ndcg_at_k_empty(self):
        from apps.legal_research.management.commands.benchmark_legal_research_retrieval import Command

        assert Command._compute_ndcg_at_k(predicted=[], relevance_map={}, top_k=0) == 0.0

    def test_query_type_label(self):
        from apps.legal_research.management.commands.benchmark_legal_research_retrieval import Command

        assert Command._query_type_label("primary") == "主查询"
        assert Command._query_type_label("unknown") == "unknown"

    def test_build_query_type_metrics_empty(self):
        from apps.legal_research.management.commands.benchmark_legal_research_retrieval import Command

        assert Command._build_query_type_metrics(
            query_type_stats={}, total_tp=0, total_cases=0, labeled_cases=0
        ) == []

    def test_query_type_metric_value(self):
        from apps.legal_research.management.commands.benchmark_legal_research_retrieval import Command

        summary = {"query_type_metrics": [{"query_type": "primary", "contribution_rate": 0.5}]}
        assert Command._query_type_metric_value(summary=summary, query_type="primary", key="contribution_rate") == 0.5
        assert Command._query_type_metric_value(summary=summary, query_type="other", key="contribution_rate") == 0.0

    def test_parse_int_list(self):
        from apps.legal_research.management.commands.benchmark_legal_research_retrieval import Command

        assert Command._parse_int_list("1,2,3") == [1, 2, 3]
        assert Command._parse_int_list("") == []
        assert Command._parse_int_list("1,1,2") == [1, 2]
        assert Command._parse_int_list("-1,0,1") == [1]

    def test_build_scenario_id(self):
        from apps.legal_research.management.commands.benchmark_legal_research_retrieval import Command

        assert Command._build_scenario_id(overrides={}) == "default"
        result = Command._build_scenario_id(overrides={"similarity_local_cache_max_size": 512})
        assert "sim512" in result

    def test_count_labeled_cases_closed(self):
        from apps.legal_research.management.commands.benchmark_legal_research_retrieval import Command

        cases = [{"expected_relevant_doc_ids": ["a"]}, {"expected_relevant_doc_ids": []}]
        assert Command._count_labeled_cases(cases=cases, evaluation_mode="closed") == 1

    def test_count_labeled_cases_pooled(self):
        from apps.legal_research.management.commands.benchmark_legal_research_retrieval import Command

        cases = [{"relevance_judgments": {"a": 1}}, {"expected_relevant_doc_ids": []}]
        assert Command._count_labeled_cases(cases=cases, evaluation_mode="pooled") == 1

    def test_evaluate_case_closed(self):
        from apps.legal_research.management.commands.benchmark_legal_research_retrieval import Command

        result = Command._evaluate_case(
            predicted_doc_ids=["a", "b"],
            expected_doc_ids=["b", "c"],
            relevance_judgments={},
            evaluation_mode="closed",
            eval_top_k=0,
        )
        assert result["tp"] == 1
        assert result["fp"] == 1
        assert result["fn"] == 1
        assert result["labeled"] is True

    def test_evaluate_case_pooled(self):
        from apps.legal_research.management.commands.benchmark_legal_research_retrieval import Command

        result = Command._evaluate_case(
            predicted_doc_ids=["a", "b"],
            expected_doc_ids=["a"],
            relevance_judgments={"a": 2, "b": 0},
            evaluation_mode="pooled",
            eval_top_k=10,
        )
        assert result["tp"] == 1
        assert result["labeled"] is True

    def test_build_ab_scenarios_single(self):
        from apps.legal_research.management.commands.benchmark_legal_research_retrieval import Command

        options = {
            "similarity_local_cache_max_size": 0,
            "semantic_local_cache_max_size": 0,
            "weike_session_restrict_cooldown_seconds": 0,
            "ab_similarity_local_cache_sizes": "",
            "ab_semantic_local_cache_sizes": "",
            "ab_weike_cooldown_seconds": "",
        }
        result = Command._build_ab_scenarios(options=options)
        assert len(result) == 1
        assert result[0]["scenario_id"] == "default"

    def test_write_json_report(self, tmp_path):
        from apps.legal_research.management.commands.benchmark_legal_research_retrieval import Command

        path = tmp_path / "report.json"
        Command._write_json_report(path=path, payload={"test": True})
        assert path.exists()
        data = json.loads(path.read_text())
        assert data["test"] is True


# --- query_mixin ---

class TestQueryMixin:
    def test_import(self):
        from apps.legal_research.services.executor_components.query_mixin import ExecutorQueryMixin

        assert ExecutorQueryMixin is not None


# --- similarity service ---

class TestSimilarityService:
    def test_import(self):
        from apps.legal_research.services.similarity.service import CaseSimilarityService

        assert CaseSimilarityService is not None


# --- scoring_mixin ---

class TestScoringMixin:
    def test_import(self):
        from apps.legal_research.services.executor_components.scoring_mixin import ExecutorScoringMixin

        assert ExecutorScoringMixin is not None


# --- intent_mixin ---

class TestIntentMixin:
    def test_import(self):
        from apps.legal_research.services.executor_components.intent_mixin import ExecutorIntentMixin

        assert ExecutorIntentMixin is not None


# --- weike document ---

class TestWeikeDocument:
    def test_import(self):
        from apps.legal_research.services.sources.weike.document import WeikeDocumentMixin

        assert WeikeDocumentMixin is not None


# --- weike search ---

class TestWeikeSearch:
    def test_import(self):
        from apps.legal_research.services.sources.weike.search import WeikeSearchMixin

        assert WeikeSearchMixin is not None


# --- task executor ---

class TestTaskExecutor:
    def test_import(self):
        from apps.legal_research.services.task.executor import LegalResearchExecutor

        assert LegalResearchExecutor is not None


# --- case download service ---

class TestCaseDownloadService:
    def test_import(self):
        from apps.legal_research.services.task.case_download_service import CaseDownloadService

        assert CaseDownloadService is not None


# --- case_download_admin ---

class TestCaseDownloadAdmin:
    def test_import(self):
        from apps.legal_research.admin.case_download_admin import CaseDownloadTaskAdmin

        assert CaseDownloadTaskAdmin is not None


# --- legal_solution task_admin ---

class TestLegalSolutionTaskAdmin:
    def test_import(self):
        from apps.legal_solution.admin.task_admin import SolutionTaskAdmin

        assert SolutionTaskAdmin is not None
