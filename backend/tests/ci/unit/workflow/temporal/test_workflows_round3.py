"""Tests for workflow/temporal/workflows.py — additional coverage.

Covers: _eval_condition gt/lt with valid values, contains with match,
_build_step_args code/http/llm types, _build_mcp_kwargs with previous_step
and non-string values, GateResult dataclass, INTERNAL_ACTIVITY_MAP/MCP_TOOL_MAP.
"""

from __future__ import annotations

import pytest

from apps.workflow.temporal.workflows import (
    GateResult,
    INTERNAL_ACTIVITY_MAP,
    MCP_TOOL_MAP,
    _build_mcp_kwargs,
    _build_step_args,
    _eval_condition,
    _resolve_dotted,
)


# ---------------------------------------------------------------------------
# _eval_condition — more operators
# ---------------------------------------------------------------------------


class TestEvalConditionMore:
    def test_gt_true(self):
        step = {"config": {"field": "count", "operator": "gt", "value": "3"}}
        assert _eval_condition(step, {"count": 5}) is True

    def test_gt_with_none_actual(self):
        step = {"config": {"field": "x", "operator": "gt", "value": "1"}}
        assert _eval_condition(step, {}) is False  # None > 1 => 0 > 1 => False

    def test_lt_true(self):
        step = {"config": {"field": "count", "operator": "lt", "value": "10"}}
        assert _eval_condition(step, {"count": 3}) is True

    def test_contains_true(self):
        step = {"config": {"field": "text", "operator": "contains", "value": "hello"}}
        assert _eval_condition(step, {"text": "say hello world"}) is True

    def test_exists_true(self):
        step = {"config": {"field": "data", "operator": "exists", "value": ""}}
        assert _eval_condition(step, {"data": "something"}) is True

    def test_unknown_operator_returns_false(self):
        step = {"config": {"field": "x", "operator": "unknown_op", "value": "1"}}
        assert _eval_condition(step, {"x": 1}) is False

    def test_neq_true(self):
        step = {"config": {"field": "f", "operator": "neq", "value": "v"}}
        assert _eval_condition(step, {"f": "other"}) is True


# ---------------------------------------------------------------------------
# _build_step_args — code and http types
# ---------------------------------------------------------------------------


class TestBuildStepArgsMore:
    def test_code_type(self):
        step = {"type": "code", "config": {"code": "print('hi')"}}
        args = _build_step_args(step, {"x": 1}, case_id=1, run_id=2)
        assert args[0] == "print('hi')"
        assert args[1] == {"x": 1}

    def test_http_with_custom_values(self):
        step = {
            "type": "http",
            "config": {"method": "POST", "url": "https://api.example.com", "headers": "{}", "body": "{}"},
        }
        args = _build_step_args(step, {}, case_id=1, run_id=2)
        assert args[0] == "POST"
        assert args[1] == "https://api.example.com"
        assert args[2] == "{}"
        assert args[3] == "{}"

    def test_llm_with_template_vars(self):
        step = {
            "type": "llm",
            "config": {
                "system_prompt": "You are {{role}}",
                "user_prompt_template": "Case {{case_id}} facts: {{step_outputs.facts.summary}}",
            },
        }
        ctx = {"role": "lawyer", "step_outputs": {"facts": {"summary": "事实摘要"}}}
        args = _build_step_args(step, ctx, case_id=42, run_id=1)
        assert "lawyer" in args[0]
        assert "事实摘要" in args[1]

    def test_llm_with_missing_vars(self):
        step = {
            "type": "llm",
            "config": {
                "system_prompt": "sys",
                "user_prompt_template": "{{missing.path}}",
            },
        }
        args = _build_step_args(step, {}, case_id=1, run_id=1)
        assert args[1] == ""  # missing vars resolve to ""

    def test_delay_default_duration(self):
        step = {"type": "delay", "config": {}}
        args = _build_step_args(step, {}, case_id=1, run_id=1)
        assert args == [5.0]  # default 5 minutes

    def test_activity_type_default(self):
        step = {"type": "activity", "config": {}}
        args = _build_step_args(step, {}, case_id=42, run_id=1)
        assert args == [42]


# ---------------------------------------------------------------------------
# _build_mcp_kwargs — previous_step resolution
# ---------------------------------------------------------------------------


class TestBuildMcpKwargsMore:
    def test_previous_step_simple(self):
        step = {"config": {"text": "{{previous_step.result}}"}}
        ctx = {"_last_output": {"result": "value"}}
        kwargs = _build_mcp_kwargs(step, ctx, case_id=1, run_id=1)
        assert kwargs["text"] == "value"

    def test_previous_step_missing(self):
        step = {"config": {"text": "{{previous_step.missing}}"}}
        ctx = {"_last_output": {}}
        kwargs = _build_mcp_kwargs(step, ctx, case_id=1, run_id=1)
        assert kwargs["text"] == ""

    def test_non_string_config_values(self):
        step = {"config": {"num": 42, "flag": True, "rate": 3.14, "text": "hello"}}
        kwargs = _build_mcp_kwargs(step, {}, case_id=1, run_id=1)
        assert kwargs["num"] == 42
        assert kwargs["flag"] is True
        assert kwargs["rate"] == 3.14
        assert kwargs["text"] == "hello"

    def test_case_id_always_injected(self):
        step = {"config": {}}
        kwargs = _build_mcp_kwargs(step, {}, case_id=99, run_id=1)
        assert kwargs["case_id"] == 99

    def test_context_var_resolution(self):
        step = {"config": {"name": "{{case_name}}"}}
        ctx = {"case_name": "Test Case"}
        kwargs = _build_mcp_kwargs(step, ctx, case_id=1, run_id=1)
        assert kwargs["name"] == "Test Case"


# ---------------------------------------------------------------------------
# GateResult
# ---------------------------------------------------------------------------


class TestGateResult:
    def test_defaults(self):
        g = GateResult()
        assert g.approved is False
        assert g.comment == ""

    def test_with_values(self):
        g = GateResult(approved=True, comment="ok")
        assert g.approved is True
        assert g.comment == "ok"


# ---------------------------------------------------------------------------
# Maps completeness — verify all expected keys exist
# ---------------------------------------------------------------------------


class TestMapsCompletenessExtended:
    def test_mcp_tool_map_has_court_filing_keys(self):
        assert "execute_court_filing" in MCP_TOOL_MAP
        assert "execute_guarantee" in MCP_TOOL_MAP
        assert "submit_court_sms" in MCP_TOOL_MAP

    def test_internal_activity_map_has_llm_steps(self):
        assert "generate_complaint" in INTERNAL_ACTIVITY_MAP
        assert "generate_complaint_simple" in INTERNAL_ACTIVITY_MAP
        assert "review_complaint_quality" in INTERNAL_ACTIVITY_MAP


# ---------------------------------------------------------------------------
# _resolve_dotted — edge cases
# ---------------------------------------------------------------------------


class TestResolveDottedMore:
    def test_dict_with_none_value(self):
        assert _resolve_dotted({"a": {"b": None}}, "a.b") is None

    def test_list_at_path(self):
        assert _resolve_dotted({"a": [1, 2, 3]}, "a") == [1, 2, 3]

    def test_empty_path(self):
        # Empty path splits to [""] which looks up key "" in dict -> None
        assert _resolve_dotted({"a": 1}, "") is None
