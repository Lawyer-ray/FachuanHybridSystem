"""Coverage tests for workflow/temporal/workflows.py helper functions and dataclasses.

Covers:
  - SimpleWorkflowInput, GateResult dataclasses
  - _resolve_dotted
  - _eval_condition (all operators)
  - _build_step_args (all step types: llm, delay, http, code, activity)
  - _build_mcp_kwargs (template resolution, previous_step, non-string values)
  - INTERNAL_ACTIVITY_MAP / MCP_TOOL_MAP contents
"""
from __future__ import annotations

from typing import Any

import pytest

from apps.workflow.temporal.workflows import (
    GateResult,
    INTERNAL_ACTIVITY_MAP,
    MCP_TOOL_MAP,
    SimpleWorkflowInput,
    _build_mcp_kwargs,
    _build_step_args,
    _eval_condition,
    _resolve_dotted,
)
from apps.workflow.temporal.activities import _HAS_COURT_FILING


class TestSimpleWorkflowInput:
    def test_creation(self):
        inp = SimpleWorkflowInput(case_id=1, run_id=2)
        assert inp.case_id == 1
        assert inp.run_id == 2

    def test_equality(self):
        a = SimpleWorkflowInput(case_id=1, run_id=2)
        b = SimpleWorkflowInput(case_id=1, run_id=2)
        assert a == b


class TestGateResult:
    def test_defaults(self):
        g = GateResult()
        assert g.approved is False
        assert g.comment == ""

    def test_custom(self):
        g = GateResult(approved=True, comment="ok")
        assert g.approved is True
        assert g.comment == "ok"


class TestResolveDotted:
    def test_simple_key(self):
        assert _resolve_dotted({"a": 1}, "a") == 1

    def test_nested_key(self):
        assert _resolve_dotted({"a": {"b": 2}}, "a.b") == 2

    def test_missing_key(self):
        assert _resolve_dotted({"a": 1}, "b") is None

    def test_non_dict_intermediate(self):
        assert _resolve_dotted("not_a_dict", "a.b") is None

    def test_deeply_nested(self):
        ctx = {"a": {"b": {"c": 42}}}
        assert _resolve_dotted(ctx, "a.b.c") == 42

    def test_none_value(self):
        assert _resolve_dotted({"a": None}, "a") is None

    def test_empty_path(self):
        assert _resolve_dotted({"a": 1}, "") is None


class TestEvalCondition:
    def test_eq_operator(self):
        step = {"config": {"field": "status", "operator": "eq", "value": "done"}}
        assert _eval_condition(step, {"status": "done"}) is True
        assert _eval_condition(step, {"status": "pending"}) is False

    def test_neq_operator(self):
        step = {"config": {"field": "x", "operator": "neq", "value": "5"}}
        assert _eval_condition(step, {"x": "3"}) is True
        assert _eval_condition(step, {"x": "5"}) is False

    def test_gt_operator(self):
        step = {"config": {"field": "count", "operator": "gt", "value": "10"}}
        assert _eval_condition(step, {"count": 15}) is True
        assert _eval_condition(step, {"count": 5}) is False

    def test_lt_operator(self):
        step = {"config": {"field": "count", "operator": "lt", "value": "10"}}
        assert _eval_condition(step, {"count": 5}) is True
        assert _eval_condition(step, {"count": 15}) is False

    def test_contains_operator(self):
        step = {"config": {"field": "text", "operator": "contains", "value": "hello"}}
        assert _eval_condition(step, {"text": "say hello world"}) is True
        assert _eval_condition(step, {"text": "goodbye"}) is False

    def test_exists_operator(self):
        step = {"config": {"field": "x", "operator": "exists"}}
        assert _eval_condition(step, {"x": 42}) is True
        assert _eval_condition(step, {}) is False

    def test_unknown_operator(self):
        step = {"config": {"field": "x", "operator": "unknown", "value": ""}}
        assert _eval_condition(step, {"x": 1}) is False

    def test_missing_field(self):
        step = {"config": {"field": "missing", "operator": "eq", "value": "x"}}
        assert _eval_condition(step, {}) is False

    def test_gt_with_none(self):
        step = {"config": {"field": "x", "operator": "gt", "value": "0"}}
        assert _eval_condition(step, {}) is False

    def test_lt_with_none(self):
        step = {"config": {"field": "x", "operator": "lt", "value": "100"}}
        assert _eval_condition(step, {}) is True

    def test_contains_with_none(self):
        step = {"config": {"field": "x", "operator": "contains", "value": "test"}}
        assert _eval_condition(step, {}) is False


class TestBuildStepArgs:
    def test_llm_step(self):
        step = {
            "type": "llm",
            "config": {
                "system_prompt": "You are {{role}}",
                "user_prompt_template": "Query: {{query}}",
            },
        }
        ctx = {"role": "helper", "query": "test"}
        args = _build_step_args(step, ctx, case_id=1, run_id=2)
        assert args == ["You are helper", "Query: test"]

    def test_llm_step_empty_prompts(self):
        step = {"type": "llm", "config": {}}
        args = _build_step_args(step, {}, case_id=1, run_id=2)
        assert args == ["", ""]

    def test_delay_step(self):
        step = {"type": "delay", "config": {"duration_minutes": 10}}
        args = _build_step_args(step, {}, case_id=1, run_id=2)
        assert args == [10.0]

    def test_delay_step_default(self):
        step = {"type": "delay", "config": {}}
        args = _build_step_args(step, {}, case_id=1, run_id=2)
        assert args == [5.0]

    def test_http_step(self):
        step = {
            "type": "http",
            "config": {
                "method": "POST",
                "url": "https://example.com",
                "headers": "Content-Type: application/json",
                "body": '{"key": "val"}',
            },
        }
        args = _build_step_args(step, {}, case_id=1, run_id=2)
        assert args == ["POST", "https://example.com", "Content-Type: application/json", '{"key": "val"}']

    def test_http_step_defaults(self):
        step = {"type": "http", "config": {}}
        args = _build_step_args(step, {}, case_id=1, run_id=2)
        assert args == ["GET", "", "", ""]

    def test_code_step(self):
        step = {"type": "code", "config": {"code": "return 42"}}
        ctx = {"extra": True}
        args = _build_step_args(step, ctx, case_id=1, run_id=2)
        assert args == ["return 42", ctx]

    def test_code_step_default(self):
        step = {"type": "code", "config": {}}
        args = _build_step_args(step, {}, case_id=1, run_id=2)
        assert args == ["", {}]

    def test_activity_step(self):
        step = {"type": "activity"}
        args = _build_step_args(step, {}, case_id=42, run_id=1)
        assert args == [42]

    def test_template_resolution_in_llm(self):
        step = {
            "type": "llm",
            "config": {
                "system_prompt": "ctx={{case_id}}",
                "user_prompt_template": "run={{run_id}}",
            },
        }
        # case_id and run_id come from context, not params
        args = _build_step_args(step, {"case_id": 10, "run_id": 20}, case_id=10, run_id=20)
        assert args == ["ctx=10", "run=20"]

    def test_template_resolution_missing_value(self):
        step = {
            "type": "llm",
            "config": {
                "system_prompt": "val={{missing}}",
                "user_prompt_template": "",
            },
        }
        args = _build_step_args(step, {}, case_id=1, run_id=2)
        assert args[0] == "val="


class TestBuildMcpKwargs:
    def test_basic(self):
        step = {"config": {"query": "test", "count": 5}}
        kwargs = _build_mcp_kwargs(step, {}, case_id=1, run_id=2)
        assert kwargs["case_id"] == 1
        assert kwargs["query"] == "test"
        assert kwargs["count"] == 5

    def test_template_resolution(self):
        step = {"config": {"keyword": "{{case_name}}"}}
        ctx = {"case_name": "合同纠纷"}
        kwargs = _build_mcp_kwargs(step, ctx, case_id=1, run_id=2)
        assert kwargs["keyword"] == "合同纠纷"

    def test_previous_step_reference(self):
        step = {"config": {"doc_id": "{{previous_step.result.doc_id}}"}}
        ctx = {"_last_output": {"result": {"doc_id": "DOC-123"}}}
        kwargs = _build_mcp_kwargs(step, ctx, case_id=1, run_id=2)
        assert kwargs["doc_id"] == "DOC-123"

    def test_bool_value_kept(self):
        step = {"config": {"flag": True}}
        kwargs = _build_mcp_kwargs(step, {}, case_id=1, run_id=2)
        assert kwargs["flag"] is True

    def test_missing_template_value_empty(self):
        step = {"config": {"val": "{{nonexistent.path}}"}}
        kwargs = _build_mcp_kwargs(step, {}, case_id=1, run_id=2)
        assert kwargs["val"] == ""

    def test_empty_config(self):
        step = {"config": {}}
        kwargs = _build_mcp_kwargs(step, {}, case_id=1, run_id=2)
        assert kwargs == {"case_id": 1}


class TestInternalActivityMap:
    def test_contains_expected_keys(self):
        expected_keys = {
            "collect_case_facts",
            "list_case_materials",
            "analyze_single_evidence",
            "summarize_evidence",
            "suggest_arrangement",
            "apply_arrangement",
            "build_litigation_context",
            "generate_complaint_simple",
            "generate_complaint",
            "review_complaint_quality",
            "download_litigation_document",
        }
        if _HAS_COURT_FILING:
            expected_keys.add("execute_court_filing")
        assert expected_keys.issubset(set(INTERNAL_ACTIVITY_MAP.keys()))


class TestMcpToolMap:
    def test_contains_expected_keys(self):
        expected = {
            "collect_case_facts",
            "create_case_log",
            "generate_complaint",
            "search_companies",
            "calculate_interest",
        }
        if _HAS_COURT_FILING:
            expected.add("execute_court_filing")
        assert expected.issubset(set(MCP_TOOL_MAP.keys()))
