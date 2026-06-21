"""Tests for workflow/temporal/workflows.py — Round 2 additional coverage.

Covers: _resolve_dotted edge cases, _eval_condition with nested paths,
_build_step_args for http defaults, _build_mcp_kwargs with non-string values,
INTERNAL_ACTIVITY_MAP completeness, MCP_TOOL_MAP completeness.
"""

from __future__ import annotations

import pytest

from apps.workflow.temporal.workflows import (
    INTERNAL_ACTIVITY_MAP,
    MCP_TOOL_MAP,
    _build_mcp_kwargs,
    _build_step_args,
    _eval_condition,
    _resolve_dotted,
)
from apps.workflow.temporal.activities import _HAS_COURT_FILING


# ── _resolve_dotted ──


class TestResolveDottedExtended:
    def test_deeply_nested(self):
        ctx = {"a": {"b": {"c": {"d": 99}}}}
        assert _resolve_dotted(ctx, "a.b.c.d") == 99

    def test_intermediate_none(self):
        ctx = {"a": None}
        assert _resolve_dotted(ctx, "a.b") is None

    def test_empty_dict(self):
        assert _resolve_dotted({}, "a.b") is None

    def test_single_key(self):
        assert _resolve_dotted({"x": 42}, "x") == 42

    def test_non_dict_at_root(self):
        assert _resolve_dotted(42, "key") is None


# ── _eval_condition ──


class TestEvalConditionExtended:
    def test_neq_false(self):
        step = {"config": {"field": "f", "operator": "neq", "value": "v"}}
        assert _eval_condition(step, {"f": "v"}) is False

    def test_gt_equal_values(self):
        step = {"config": {"field": "count", "operator": "gt", "value": "5"}}
        assert _eval_condition(step, {"count": 5}) is False

    def test_lt_equal_values(self):
        step = {"config": {"field": "count", "operator": "lt", "value": "5"}}
        assert _eval_condition(step, {"count": 5}) is False

    def test_contains_empty_actual(self):
        step = {"config": {"field": "text", "operator": "contains", "value": "x"}}
        assert _eval_condition(step, {"text": ""}) is False

    def test_exists_none_value(self):
        step = {"config": {"field": "data", "operator": "exists", "value": ""}}
        # _resolve_dotted returns None for None values, so exists=False
        assert _eval_condition(step, {"data": None}) is False

    def test_eq_with_numeric_strings(self):
        step = {"config": {"field": "n", "operator": "eq", "value": "0"}}
        assert _eval_condition(step, {"n": 0}) is True


# ── _build_step_args ──


class TestBuildStepArgsExtended:
    def test_http_defaults(self):
        step = {"type": "http", "config": {}}
        args = _build_step_args(step, {}, case_id=1, run_id=2)
        assert args[0] == "GET"
        assert args[1] == ""

    def test_delay_zero(self):
        step = {"type": "delay", "config": {"duration_minutes": 0}}
        args = _build_step_args(step, {}, case_id=1, run_id=2)
        assert args == [0.0]

    def test_llm_with_nested_context(self):
        step = {
            "type": "llm",
            "config": {
                "system_prompt": "sys",
                "user_prompt_template": "{{step_outputs.evidence.summary}}",
            },
        }
        ctx = {"step_outputs": {"evidence": {"summary": "证据汇总"}}}
        args = _build_step_args(step, ctx, case_id=1, run_id=1)
        assert "证据汇总" in args[1]


# ── _build_mcp_kwargs ──


class TestBuildMcpKwargsExtended:
    def test_previous_step_nested(self):
        step = {"config": {"text": "{{previous_step.analysis.result}}"}}
        ctx = {"_last_output": {"analysis": {"result": "分析结果"}}}
        kwargs = _build_mcp_kwargs(step, ctx, case_id=1, run_id=1)
        assert kwargs["text"] == "分析结果"

    def test_bool_value(self):
        step = {"config": {"enable": True, "count": 5, "rate": 0.5, "name": "test"}}
        kwargs = _build_mcp_kwargs(step, {}, case_id=1, run_id=1)
        assert kwargs["enable"] is True
        assert kwargs["count"] == 5
        assert kwargs["rate"] == 0.5
        assert kwargs["name"] == "test"


# ── Maps completeness ──


class TestMapsCompleteness:
    def test_internal_activity_map_keys(self):
        expected = {
            "collect_case_facts", "list_case_materials", "analyze_single_evidence",
            "summarize_evidence", "suggest_arrangement", "apply_arrangement",
            "build_litigation_context", "generate_complaint_simple",
            "generate_complaint", "review_complaint_quality",
            "download_litigation_document",
        }
        if _HAS_COURT_FILING:
            expected.add("execute_court_filing")
        assert expected.issubset(set(INTERNAL_ACTIVITY_MAP.keys()))

    def test_mcp_tool_map_keys(self):
        expected = {
            "collect_case_facts", "list_case_materials", "create_case_log",
            "generate_complaint", "generate_defense", "download_litigation_document",
            "search_companies", "calculate_litigation_fee",
        }
        assert expected.issubset(set(MCP_TOOL_MAP.keys()))
