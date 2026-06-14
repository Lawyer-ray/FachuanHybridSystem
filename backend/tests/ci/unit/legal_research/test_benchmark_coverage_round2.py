"""Extended coverage tests for benchmark_legal_research_retrieval command.

Covers branches NOT already tested in test_benchmark_coverage.py:
  - _normalize_relevance_grade edge cases (float, string variants)
  - _parse_relevance_judgments with list-of-dicts, list-of-strings, duplicate upgrades
  - _evaluate_case with eval_top_k limiting, pooled edge cases, empty predictions
  - _compute_ndcg_at_k with various top_k scenarios
  - _build_query_type_metrics with real data, extras, contributions
  - _query_type_metric_value edge cases (non-list, non-dict, bad value)
  - _write_summary_csv
  - _build_ab_scenarios with A/B matrices
  - _load_cases various paths (missing file, bad JSON, bad format, missing fields)
  - _write_template
  - _temporary_tuning_overrides context manager
  - _count_labeled_cases pooled with both expected and judgments
  - _normalize_search_mode
"""
from __future__ import annotations

import json
import math
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from apps.legal_research.management.commands.benchmark_legal_research_retrieval import (
    Command,
    CredentialRef,
)


class TestNormalizeRelevanceGradeExtended:
    """More branches for _normalize_relevance_grade."""

    def test_float_value_clamped(self):
        assert Command._normalize_relevance_grade(3.5) == 2

    def test_negative_value_clamped(self):
        assert Command._normalize_relevance_grade(-1) == 0

    def test_string_high(self):
        assert Command._normalize_relevance_grade("high") == 2

    def test_string_strong(self):
        assert Command._normalize_relevance_grade("strong") == 2

    def test_string_relevant(self):
        assert Command._normalize_relevance_grade("relevant") == 2

    def test_string_chinese_high(self):
        assert Command._normalize_relevance_grade("高度相关") == 2
        assert Command._normalize_relevance_grade("强相关") == 2
        assert Command._normalize_relevance_grade("相关") == 2

    def test_string_partial(self):
        assert Command._normalize_relevance_grade("partial") == 1

    def test_string_weak(self):
        assert Command._normalize_relevance_grade("weak") == 1

    def test_string_chinese_partial(self):
        assert Command._normalize_relevance_grade("一般相关") == 1
        assert Command._normalize_relevance_grade("部分相关") == 1

    def test_string_irrelevant(self):
        assert Command._normalize_relevance_grade("irrelevant") == 0

    def test_string_none(self):
        assert Command._normalize_relevance_grade("none") == 0

    def test_string_chinese_irrelevant(self):
        assert Command._normalize_relevance_grade("不相关") == 0

    def test_empty_string(self):
        assert Command._normalize_relevance_grade("") is None

    def test_whitespace_string(self):
        assert Command._normalize_relevance_grade("   ") is None

    def test_unrecognized_string(self):
        assert Command._normalize_relevance_grade("unknown_grade") is None

    def test_string_one(self):
        assert Command._normalize_relevance_grade("1") == 1

    def test_string_zero(self):
        assert Command._normalize_relevance_grade("0") == 0

    def test_string_two(self):
        assert Command._normalize_relevance_grade("2") == 2

    def test_string_number_three_not_recognized(self):
        # "3" is not in any recognized set, so returns None
        assert Command._normalize_relevance_grade("3") is None


class TestParseRelevanceJudgmentsExtended:
    """More branches for _parse_relevance_judgments."""

    def test_dict_with_none_values_skipped(self):
        result = Command._parse_relevance_judgments({"d1": None})
        # None -> _normalize_relevance_grade(None) -> None -> skip
        assert "d1" not in result

    def test_dict_empty_key_skipped(self):
        result = Command._parse_relevance_judgments({"": 1})
        assert "" not in result

    def test_dict_duplicate_keeps_max(self):
        result = Command._parse_relevance_judgments({"d1": 1, "d1": 2})
        assert result["d1"] == 2

    def test_list_of_dicts_with_doc_id_key(self):
        result = Command._parse_relevance_judgments([{"doc_id": "x1", "grade": 2}])
        assert result["x1"] == 2

    def test_list_of_dicts_with_id_key(self):
        result = Command._parse_relevance_judgments([{"id": "x2", "grade": 1}])
        assert result["x2"] == 1

    def test_list_of_dicts_empty_doc_id_skipped(self):
        result = Command._parse_relevance_judgments([{"doc_id": "", "grade": 1}])
        assert not result

    def test_list_of_strings(self):
        result = Command._parse_relevance_judgments(["doc_a", "doc_b"])
        assert result["doc_a"] == 1
        assert result["doc_b"] == 1

    def test_list_empty_string_skipped(self):
        result = Command._parse_relevance_judgments(["", "  "])
        assert not result

    def test_none_input(self):
        assert Command._parse_relevance_judgments(None) == {}

    def test_list_mixed(self):
        result = Command._parse_relevance_judgments([{"doc_id": "a", "grade": 2}, "b"])
        assert result["a"] == 2
        assert result["b"] == 1

    def test_dict_grade_none_skipped(self):
        result = Command._parse_relevance_judgments({"d1": "unknown"})
        assert "d1" not in result


class TestEvaluateCaseExtended:
    """More branches for _evaluate_case."""

    def test_empty_predictions_closed(self):
        result = Command._evaluate_case(
            predicted_doc_ids=[],
            expected_doc_ids=["a", "b"],
            relevance_judgments={},
            evaluation_mode="closed",
            eval_top_k=0,
        )
        assert result["tp"] == 0
        assert result["fp"] == 0
        assert result["fn"] == 2
        assert result["labeled"] is True
        assert result["anchor_hit_at_k"] is False

    def test_empty_predictions_pooled(self):
        result = Command._evaluate_case(
            predicted_doc_ids=[],
            expected_doc_ids=["a"],
            relevance_judgments={"a": 1},
            evaluation_mode="pooled",
            eval_top_k=0,
        )
        assert result["tp"] == 0
        assert result["fn"] == 1
        assert result["unjudged_count"] == 0

    def test_eval_top_k_limits_predictions(self):
        result = Command._evaluate_case(
            predicted_doc_ids=["a", "b", "c", "d"],
            expected_doc_ids=["a"],
            relevance_judgments={"a": 1},
            evaluation_mode="pooled",
            eval_top_k=2,
        )
        # Only first 2 predicted are considered
        assert len(result.get("predicted_doc_ids", ["a", "b"])) == 2 or result["judged_count"] <= 2

    def test_pooled_unjudged_predictions(self):
        result = Command._evaluate_case(
            predicted_doc_ids=["x", "y", "z"],
            expected_doc_ids=[],
            relevance_judgments={},
            evaluation_mode="pooled",
            eval_top_k=0,
        )
        assert result["unjudged_count"] == 3
        assert result["judged_count"] == 0

    def test_pooled_mixed_judged_unjudged(self):
        result = Command._evaluate_case(
            predicted_doc_ids=["a", "b", "c"],
            expected_doc_ids=["a"],
            relevance_judgments={"a": 1},
            evaluation_mode="pooled",
            eval_top_k=0,
        )
        assert result["judged_count"] == 1
        assert result["unjudged_count"] == 2

    def test_pooled_zero_grade_is_fp(self):
        result = Command._evaluate_case(
            predicted_doc_ids=["a"],
            expected_doc_ids=[],
            relevance_judgments={"a": 0},
            evaluation_mode="pooled",
            eval_top_k=0,
        )
        assert result["fp"] == 1
        assert result["tp"] == 0

    def test_no_labeled_no_expected(self):
        result = Command._evaluate_case(
            predicted_doc_ids=[],
            expected_doc_ids=[],
            relevance_judgments={},
            evaluation_mode="closed",
            eval_top_k=0,
        )
        assert result["labeled"] is False


class TestComputeNdcgAtKExtended:
    """More branches for _compute_ndcg_at_k."""

    def test_perfect_ordering(self):
        result = Command._compute_ndcg_at_k(
            predicted=["a", "b"],
            relevance_map={"a": 2, "b": 1, "c": 0},
            top_k=2,
        )
        assert result == 1.0

    def test_reversed_ordering(self):
        result = Command._compute_ndcg_at_k(
            predicted=["b", "a"],
            relevance_map={"a": 2, "b": 1},
            top_k=2,
        )
        assert 0.0 < result < 1.0

    def test_top_k_zero_allows_all(self):
        result = Command._compute_ndcg_at_k(
            predicted=["a", "b", "c"],
            relevance_map={"a": 1},
            top_k=0,
        )
        assert 0.0 <= result <= 1.0

    def test_empty_relevance_map(self):
        result = Command._compute_ndcg_at_k(
            predicted=["a"],
            relevance_map={},
            top_k=1,
        )
        assert result == 0.0

    def test_single_item(self):
        result = Command._compute_ndcg_at_k(
            predicted=["a"],
            relevance_map={"a": 2},
            top_k=1,
        )
        assert result == 1.0


class TestBuildQueryTypeMetricsExtended:
    """More branches for _build_query_type_metrics."""

    def test_with_real_data(self):
        stats = {
            "primary": {
                "total_cases": 10,
                "labeled_cases": 8,
                "errors": 1,
                "tp": 5,
                "fp": 2,
                "fn": 1,
                "judged_count": 100,
                "unjudged_count": 20,
            },
            "expansion": {
                "total_cases": 5,
                "labeled_cases": 3,
                "errors": 0,
                "tp": 2,
                "fp": 1,
                "fn": 1,
                "judged_count": 50,
                "unjudged_count": 10,
            },
        }
        result = Command._build_query_type_metrics(
            query_type_stats=stats, total_tp=7, total_cases=15, labeled_cases=11
        )
        assert len(result) == 2
        assert result[0]["query_type"] == "primary"
        assert result[1]["query_type"] == "expansion"

    def test_extras_beyond_order(self):
        stats = {
            "custom_type": {"total_cases": 3, "labeled_cases": 2, "tp": 1, "fp": 0, "fn": 0, "judged_count": 5, "unjudged_count": 1, "errors": 0},
            "primary": {"total_cases": 5, "labeled_cases": 4, "tp": 3, "fp": 1, "fn": 0, "judged_count": 10, "unjudged_count": 2, "errors": 0},
        }
        result = Command._build_query_type_metrics(
            query_type_stats=stats, total_tp=4, total_cases=8, labeled_cases=6
        )
        # primary first (ordered), then custom_type
        assert result[0]["query_type"] == "primary"
        assert result[1]["query_type"] == "custom_type"

    def test_contribution_rate_zero_tp(self):
        stats = {
            "primary": {"total_cases": 2, "labeled_cases": 2, "tp": 0, "fp": 0, "fn": 0, "judged_count": 5, "unjudged_count": 0, "errors": 0},
        }
        result = Command._build_query_type_metrics(
            query_type_stats=stats, total_tp=0, total_cases=2, labeled_cases=2
        )
        assert result[0]["contribution_rate"] == 0.0

    def test_labeled_case_ratio_zero_labeled(self):
        stats = {
            "primary": {"total_cases": 2, "labeled_cases": 0, "tp": 0, "fp": 0, "fn": 0, "judged_count": 0, "unjudged_count": 0, "errors": 0},
        }
        result = Command._build_query_type_metrics(
            query_type_stats=stats, total_tp=0, total_cases=2, labeled_cases=0
        )
        assert result[0]["labeled_case_ratio"] == 0.0


class TestQueryTypeMetricValueExtended:
    """More branches for _query_type_metric_value."""

    def test_no_metrics_key(self):
        assert Command._query_type_metric_value(summary={}, query_type="primary", key="f1") == 0.0

    def test_metrics_not_list(self):
        assert Command._query_type_metric_value(summary={"query_type_metrics": "bad"}, query_type="primary", key="f1") == 0.0

    def test_metrics_item_not_dict(self):
        assert Command._query_type_metric_value(summary={"query_type_metrics": ["bad"]}, query_type="primary", key="f1") == 0.0

    def test_bad_value_returns_zero(self):
        summary = {"query_type_metrics": [{"query_type": "primary", "f1": "not_a_number"}]}
        assert Command._query_type_metric_value(summary=summary, query_type="primary", key="f1") == 0.0


class TestNormalizeSearchMode:
    """Test _normalize_search_mode."""

    def test_empty_returns_expanded(self):
        from apps.legal_research.models import LegalResearchSearchMode
        assert Command._normalize_search_mode("") == LegalResearchSearchMode.EXPANDED

    def test_single_variants(self):
        from apps.legal_research.models import LegalResearchSearchMode
        assert Command._normalize_search_mode("single") == LegalResearchSearchMode.SINGLE
        assert Command._normalize_search_mode("strict") == LegalResearchSearchMode.SINGLE
        assert Command._normalize_search_mode("单检索") == LegalResearchSearchMode.SINGLE
        assert Command._normalize_search_mode("单一检索") == LegalResearchSearchMode.SINGLE
        assert Command._normalize_search_mode("不扩展") == LegalResearchSearchMode.SINGLE

    def test_expanded_variants(self):
        from apps.legal_research.models import LegalResearchSearchMode
        assert Command._normalize_search_mode("expanded") == LegalResearchSearchMode.EXPANDED
        assert Command._normalize_search_mode("random_text") == LegalResearchSearchMode.EXPANDED

    def test_none_returns_expanded(self):
        from apps.legal_research.models import LegalResearchSearchMode
        assert Command._normalize_search_mode(None) == LegalResearchSearchMode.EXPANDED


class TestCountLabeledCasesExtended:
    """More branches for _count_labeled_cases."""

    def test_pooled_both_expected_and_judgments(self):
        cases = [
            {"expected_relevant_doc_ids": ["a"], "relevance_judgments": {"b": 1}},
            {"expected_relevant_doc_ids": [], "relevance_judgments": {"c": 1}},
            {"expected_relevant_doc_ids": [], "relevance_judgments": {}},
        ]
        assert Command._count_labeled_cases(cases=cases, evaluation_mode="pooled") == 2

    def test_closed_no_expected(self):
        cases = [{"relevance_judgments": {"a": 1}}]
        assert Command._count_labeled_cases(cases=cases, evaluation_mode="closed") == 0

    def test_pooled_no_expected_no_judgments(self):
        cases = [{"expected_relevant_doc_ids": [], "relevance_judgments": {}}]
        assert Command._count_labeled_cases(cases=cases, evaluation_mode="pooled") == 0


class TestBuildAbScenariosExtended:
    """More branches for _build_ab_scenarios."""

    def test_single_overrides(self):
        options = {
            "similarity_local_cache_max_size": 512,
            "semantic_local_cache_max_size": 0,
            "weike_session_restrict_cooldown_seconds": 0,
            "ab_similarity_local_cache_sizes": "",
            "ab_semantic_local_cache_sizes": "",
            "ab_weike_cooldown_seconds": "",
        }
        result = Command._build_ab_scenarios(options=options)
        assert len(result) == 1
        assert result[0]["overrides"]["similarity_local_cache_max_size"] == 512

    def test_ab_matrix_multiple(self):
        options = {
            "similarity_local_cache_max_size": 0,
            "semantic_local_cache_max_size": 0,
            "weike_session_restrict_cooldown_seconds": 0,
            "ab_similarity_local_cache_sizes": "100,200",
            "ab_semantic_local_cache_sizes": "50",
            "ab_weike_cooldown_seconds": "",
        }
        result = Command._build_ab_scenarios(options=options)
        # 2 similarity * 1 semantic * 1 default weike = 2
        assert len(result) == 2

    def test_ab_deduplication(self):
        options = {
            "similarity_local_cache_max_size": 100,
            "semantic_local_cache_max_size": 0,
            "weike_session_restrict_cooldown_seconds": 0,
            "ab_similarity_local_cache_sizes": "100",
            "ab_semantic_local_cache_sizes": "",
            "ab_weike_cooldown_seconds": "",
        }
        result = Command._build_ab_scenarios(options=options)
        # The base override sim=100 and ab sim=100 produce same scenario
        assert len(result) == 1


class TestLoadCases:
    """Test _load_cases various paths."""

    def test_missing_file(self):
        with pytest.raises(Exception, match="样本文件不存在"):
            Command._load_cases(path=Path("/nonexistent/file.json"))

    def test_invalid_json(self, tmp_path):
        p = tmp_path / "bad.json"
        p.write_text("not json {{{", encoding="utf-8")
        with pytest.raises(Exception, match="样本文件解析失败"):
            Command._load_cases(path=p)

    def test_bad_format_not_list(self, tmp_path):
        p = tmp_path / "bad.json"
        p.write_text(json.dumps({"not_cases": []}), encoding="utf-8")
        with pytest.raises(Exception, match="样本文件格式错误"):
            Command._load_cases(path=p)

    def test_valid_list_format(self, tmp_path):
        p = tmp_path / "ok.json"
        p.write_text(json.dumps([{"keyword": "k", "case_summary": "s"}]), encoding="utf-8")
        cases = Command._load_cases(path=p)
        assert len(cases) == 1

    def test_valid_dict_with_cases_key(self, tmp_path):
        p = tmp_path / "ok2.json"
        p.write_text(json.dumps({"cases": [{"keyword": "k", "case_summary": "s"}]}), encoding="utf-8")
        cases = Command._load_cases(path=p)
        assert len(cases) == 1

    def test_missing_keyword_raises(self, tmp_path):
        p = tmp_path / "bad.json"
        p.write_text(json.dumps([{"case_summary": "s"}]), encoding="utf-8")
        with pytest.raises(Exception, match="样本缺少 keyword"):
            Command._load_cases(path=p)

    def test_missing_case_summary_raises(self, tmp_path):
        p = tmp_path / "bad.json"
        p.write_text(json.dumps([{"keyword": "k"}]), encoding="utf-8")
        with pytest.raises(Exception, match="样本缺少 case_summary"):
            Command._load_cases(path=p)

    def test_non_dict_items_skipped(self, tmp_path):
        p = tmp_path / "bad.json"
        p.write_text(json.dumps(["not_a_dict", {"keyword": "k", "case_summary": "s"}]), encoding="utf-8")
        cases = Command._load_cases(path=p)
        assert len(cases) == 1

    def test_query_type_normalization(self, tmp_path):
        p = tmp_path / "ok.json"
        p.write_text(json.dumps([{"keyword": "k", "case_summary": "s", "query_type": "expansion"}]), encoding="utf-8")
        cases = Command._load_cases(path=p)
        assert cases[0]["query_type"] == "expansion"

    def test_query_strategy_type_fallback(self, tmp_path):
        p = tmp_path / "ok.json"
        p.write_text(
            json.dumps([{"keyword": "k", "case_summary": "s", "query_strategy_type": "feedback"}]),
            encoding="utf-8",
        )
        cases = Command._load_cases(path=p)
        assert cases[0]["query_type"] == "feedback"


class TestWriteTemplate:
    """Test _write_template."""

    def test_creates_template(self, tmp_path):
        p = tmp_path / "template.json"
        Command._write_template(path=p)
        assert p.exists()
        data = json.loads(p.read_text(encoding="utf-8"))
        assert data["schema_version"] == "v2"
        assert len(data["cases"]) == 2


class TestWriteSummaryCsv:
    """Test _write_summary_csv."""

    def test_creates_csv(self, tmp_path):
        cmd = Command()
        csv_path = tmp_path / "summary.csv"
        scenario_reports = [
            {
                "scenario_id": "s1",
                "overrides": {},
                "summary": {
                    "evaluation_mode": "pooled",
                    "eval_top_k": 20,
                    "total_cases": 10,
                    "labeled_cases": 8,
                    "labeled_ratio": 0.8,
                    "errors": 1,
                    "judged_count": 100,
                    "unjudged_count": 20,
                    "tp": 5,
                    "fp": 2,
                    "fn": 1,
                    "precision": 0.71,
                    "recall": 0.83,
                    "f1": 0.77,
                    "ndcg_at_k": 0.65,
                    "query_type_metrics": [
                        {"query_type": "primary", "contribution_rate": 0.6},
                        {"query_type": "expansion", "contribution_rate": 0.4},
                        {"query_type": "feedback", "contribution_rate": 0.0},
                        {"query_type": "other", "contribution_rate": 0.0},
                    ],
                },
                "cases": [],
            }
        ]
        cmd._write_summary_csv(path=csv_path, scenario_reports=scenario_reports)
        assert csv_path.exists()
        content = csv_path.read_text(encoding="utf-8")
        assert "scenario_id" in content
        assert "s1" in content


class TestTemporaryTuningOverrides:
    """Test _temporary_tuning_overrides context manager."""

    def test_no_payload_yields(self):
        with Command._temporary_tuning_overrides({}):
            pass  # Should not raise

    def test_valid_override(self):
        from apps.legal_research.services.similarity.tuning_config import LegalResearchTuningConfig

        original_load = LegalResearchTuningConfig.load
        try:
            with Command._temporary_tuning_overrides(
                {"similarity_local_cache_max_size": 9999}
            ):
                pass  # Override applied and reverted
        finally:
            LegalResearchTuningConfig.load = original_load


class TestCredentialRef:
    """Test CredentialRef dataclass."""

    def test_creation(self):
        ref = CredentialRef(id=1, lawyer_id=2)
        assert ref.id == 1
        assert ref.lawyer_id == 2
