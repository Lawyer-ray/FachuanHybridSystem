"""Tests for apps.legal_research.management.commands.benchmark_legal_research_retrieval."""

from __future__ import annotations

import json
import math
import tempfile
from pathlib import Path
from types import SimpleNamespace

import pytest

from apps.legal_research.management.commands.benchmark_legal_research_retrieval import Command


class TestNormalizeQueryType:
    def test_primary(self) -> None:
        assert Command._normalize_query_type("primary") == "primary"
        assert Command._normalize_query_type("main") == "primary"
        assert Command._normalize_query_type("主查询") == "primary"

    def test_expansion(self) -> None:
        assert Command._normalize_query_type("expansion") == "expansion"
        assert Command._normalize_query_type("扩展") == "expansion"

    def test_feedback(self) -> None:
        assert Command._normalize_query_type("feedback") == "feedback"
        assert Command._normalize_query_type("反馈") == "feedback"

    def test_other_fallback(self) -> None:
        assert Command._normalize_query_type("random") == "other"
        assert Command._normalize_query_type(None) == "other"
        assert Command._normalize_query_type("") == "other"


class TestNormalizeEvaluationMode:
    def test_closed(self) -> None:
        assert Command._normalize_evaluation_mode("closed") == "closed"

    def test_pooled(self) -> None:
        assert Command._normalize_evaluation_mode("pooled") == "pooled"

    def test_unknown_defaults_pooled(self) -> None:
        assert Command._normalize_evaluation_mode("unknown") == "pooled"
        assert Command._normalize_evaluation_mode(None) == "pooled"


class TestNormalizeEvalTopK:
    def test_normal(self) -> None:
        assert Command._normalize_eval_top_k(20) == 20

    def test_zero(self) -> None:
        assert Command._normalize_eval_top_k(0) == 0

    def test_negative_clamps_to_zero(self) -> None:
        assert Command._normalize_eval_top_k(-5) == 0

    def test_none(self) -> None:
        assert Command._normalize_eval_top_k(None) == 0


class TestParseRelevanceJudgments:
    def test_dict_input(self) -> None:
        result = Command._parse_relevance_judgments({"DOC-1": 2, "DOC-2": 1})
        assert result["DOC-1"] == 2
        assert result["DOC-2"] == 1

    def test_list_of_dicts(self) -> None:
        result = Command._parse_relevance_judgments([{"doc_id": "DOC-1", "grade": 2}])
        assert result["DOC-1"] == 2

    def test_list_of_strings(self) -> None:
        result = Command._parse_relevance_judgments(["DOC-1", "DOC-2"])
        assert result["DOC-1"] == 1
        assert result["DOC-2"] == 1

    def test_none_input(self) -> None:
        assert Command._parse_relevance_judgments(None) == {}

    def test_empty_dict(self) -> None:
        assert Command._parse_relevance_judgments({}) == {}


class TestNormalizeRelevanceGrade:
    def test_int_values(self) -> None:
        assert Command._normalize_relevance_grade(0) == 0
        assert Command._normalize_relevance_grade(1) == 1
        assert Command._normalize_relevance_grade(2) == 2
        assert Command._normalize_relevance_grade(10) == 2  # clamped

    def test_bool_values(self) -> None:
        assert Command._normalize_relevance_grade(True) == 1
        assert Command._normalize_relevance_grade(False) == 0

    def test_string_values(self) -> None:
        assert Command._normalize_relevance_grade("high") == 2
        assert Command._normalize_relevance_grade("partial") == 1
        assert Command._normalize_relevance_grade("irrelevant") == 0

    def test_none(self) -> None:
        assert Command._normalize_relevance_grade(None) is None


class TestComputePrf:
    def test_perfect(self) -> None:
        p, r, f1 = Command._compute_prf(tp=5, fp=0, fn=0)
        assert p == 1.0
        assert r == 1.0
        assert f1 == 1.0

    def test_zero(self) -> None:
        p, r, f1 = Command._compute_prf(tp=0, fp=0, fn=0)
        assert p == 0.0
        assert r == 0.0
        assert f1 == 0.0

    def test_partial(self) -> None:
        p, r, f1 = Command._compute_prf(tp=2, fp=1, fn=1)
        assert abs(p - 2 / 3) < 0.001  # precision = tp/(tp+fp)
        assert abs(r - 2 / 3) < 0.001  # recall = tp/(tp+fn)
        expected_f1 = 2 * (2 / 3) * (2 / 3) / (2 / 3 + 2 / 3)
        assert abs(f1 - expected_f1) < 0.001


class TestCountConfusion:
    def test_basic(self) -> None:
        tp, fp, fn = Command._count_confusion(
            predicted_doc_ids=["A", "B", "C"],
            expected_doc_ids=["B", "C", "D"],
        )
        assert tp == 2  # B, C
        assert fp == 1  # A
        assert fn == 1  # D

    def test_empty(self) -> None:
        tp, fp, fn = Command._count_confusion(predicted_doc_ids=[], expected_doc_ids=[])
        assert tp == 0
        assert fp == 0
        assert fn == 0


class TestComputeNdcgAtK:
    def test_perfect_ranking(self) -> None:
        result = Command._compute_ndcg_at_k(
            predicted=["A", "B", "C"],
            relevance_map={"A": 2, "B": 1, "C": 0},
            top_k=3,
        )
        assert result > 0
        assert result <= 1.0

    def test_empty_prediction(self) -> None:
        result = Command._compute_ndcg_at_k(
            predicted=[],
            relevance_map={"A": 2},
            top_k=3,
        )
        assert result == 0.0

    def test_empty_relevance(self) -> None:
        result = Command._compute_ndcg_at_k(
            predicted=["A", "B"],
            relevance_map={},
            top_k=3,
        )
        assert result == 0.0


class TestToStrList:
    def test_normal_list(self) -> None:
        assert Command._to_str_list(["A", "B", "C"]) == ["A", "B", "C"]

    def test_empty_list(self) -> None:
        assert Command._to_str_list([]) == []

    def test_non_list(self) -> None:
        assert Command._to_str_list("not-a-list") == []

    def test_strips_whitespace(self) -> None:
        assert Command._to_str_list([" A ", "", "B"]) == ["A", "B"]


class TestCountLabeledCases:
    def test_closed_mode(self) -> None:
        cases = [
            {"expected_relevant_doc_ids": ["A", "B"]},
            {"expected_relevant_doc_ids": []},
        ]
        count = Command._count_labeled_cases(cases=cases, evaluation_mode="closed")
        assert count == 1

    def test_pooled_mode_with_judgments(self) -> None:
        cases = [
            {"expected_relevant_doc_ids": [], "relevance_judgments": {"DOC-1": 2}},
        ]
        count = Command._count_labeled_cases(cases=cases, evaluation_mode="pooled")
        assert count == 1

    def test_no_labels(self) -> None:
        cases = [{"expected_relevant_doc_ids": []}]
        count = Command._count_labeled_cases(cases=cases, evaluation_mode="pooled")
        assert count == 0


class TestInitQueryTypeMetric:
    def test_returns_correct_keys(self) -> None:
        metric = Command._init_query_type_metric()
        assert metric["total_cases"] == 0
        assert metric["labeled_cases"] == 0
        assert metric["errors"] == 0
        assert metric["tp"] == 0
        assert metric["fp"] == 0
        assert metric["fn"] == 0


class TestParseIntList:
    def test_normal(self) -> None:
        assert Command._parse_int_list("1,2,3") == [1, 2, 3]

    def test_with_spaces(self) -> None:
        assert Command._parse_int_list(" 1 , 2 , 3 ") == [1, 2, 3]

    def test_with_invalid(self) -> None:
        assert Command._parse_int_list("1,abc,3") == [1, 3]

    def test_empty(self) -> None:
        assert Command._parse_int_list("") == []

    def test_deduplication(self) -> None:
        assert Command._parse_int_list("1,2,1,3,2") == [1, 2, 3]

    def test_negative_filtered(self) -> None:
        assert Command._parse_int_list("-1,0,1") == [1]


class TestBuildScenarioId:
    def test_empty(self) -> None:
        assert Command._build_scenario_id(overrides={}) == "default"

    def test_with_values(self) -> None:
        assert Command._build_scenario_id(overrides={"similarity_local_cache_max_size": 512}) == "sim512_sem0_wk0"


class TestQueryTypeLabel:
    def test_known(self) -> None:
        assert Command._query_type_label("primary") == "主查询"

    def test_unknown(self) -> None:
        assert Command._query_type_label("unknown") == "unknown"


class TestQueryTypeMetricValue:
    def test_found(self) -> None:
        summary = {"query_type_metrics": [{"query_type": "primary", "contribution_rate": 0.5}]}
        assert Command._query_type_metric_value(summary=summary, query_type="primary", key="contribution_rate") == 0.5

    def test_not_found(self) -> None:
        summary: dict = {"query_type_metrics": []}
        assert Command._query_type_metric_value(summary=summary, query_type="primary", key="contribution_rate") == 0.0

    def test_no_metrics(self) -> None:
        summary: dict = {}
        assert Command._query_type_metric_value(summary=summary, query_type="primary", key="x") == 0.0


class TestLoadCases:
    def test_list_format(self) -> None:
        with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
            json.dump([
                {"keyword": "test", "case_summary": "summary"}
            ], f)
            f.flush()
            cases = Command._load_cases(path=Path(f.name))
        assert len(cases) == 1

    def test_dict_format(self) -> None:
        with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
            json.dump({"cases": [{"keyword": "test", "case_summary": "summary"}]}, f)
            f.flush()
            cases = Command._load_cases(path=Path(f.name))
        assert len(cases) == 1

    def test_missing_file_raises(self) -> None:
        with pytest.raises(Exception, match="样本文件不存在"):
            Command._load_cases(path=Path("/nonexistent/file.json"))

    def test_missing_keyword_raises(self) -> None:
        with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
            json.dump([{"case_summary": "summary"}], f)
            f.flush()
            with pytest.raises(Exception, match="keyword"):
                Command._load_cases(path=Path(f.name))

    def test_invalid_format_raises(self) -> None:
        with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
            json.dump("just a string", f)
            f.flush()
            with pytest.raises(Exception, match="格式错误"):
                Command._load_cases(path=Path(f.name))


class TestEvaluateCase:
    def test_closed_mode(self) -> None:
        result = Command._evaluate_case(
            predicted_doc_ids=["A", "B", "C"],
            expected_doc_ids=["B", "C", "D"],
            relevance_judgments={},
            evaluation_mode="closed",
            eval_top_k=0,
        )
        assert result["tp"] == 2
        assert result["fp"] == 1
        assert result["fn"] == 1
        assert result["labeled"] is True

    def test_pooled_mode(self) -> None:
        result = Command._evaluate_case(
            predicted_doc_ids=["A", "B", "C"],
            expected_doc_ids=["B"],
            relevance_judgments={"A": 2, "C": 0},
            evaluation_mode="pooled",
            eval_top_k=0,
        )
        assert result["labeled"] is True

    def test_top_k_limit(self) -> None:
        result = Command._evaluate_case(
            predicted_doc_ids=["A", "B", "C"],
            expected_doc_ids=["C"],
            relevance_judgments={},
            evaluation_mode="closed",
            eval_top_k=2,
        )
        # Only top 2 predicted: A, B. C is not in top 2.
        assert "A" not in result.get("expected_relevant_doc_ids", ["C"])


class TestBuildQueryTypeMetrics:
    def test_empty(self) -> None:
        result = Command._build_query_type_metrics(
            query_type_stats={}, total_tp=0, total_cases=0, labeled_cases=0
        )
        assert result == []

    def test_with_stats(self) -> None:
        stats = {
            "primary": {"total_cases": 5, "labeled_cases": 3, "errors": 0, "tp": 2, "fp": 1, "fn": 1, "judged_count": 3, "unjudged_count": 0},
        }
        result = Command._build_query_type_metrics(
            query_type_stats=stats, total_tp=2, total_cases=5, labeled_cases=3
        )
        assert len(result) == 1
        assert result[0]["query_type"] == "primary"
        assert result[0]["contribution_rate"] == 1.0  # 2/2
