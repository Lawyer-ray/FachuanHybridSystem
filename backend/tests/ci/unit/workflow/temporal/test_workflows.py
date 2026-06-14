"""Tests for workflow/temporal/workflows.py — pure functions and constants."""

from __future__ import annotations

import re
from datetime import timedelta
from unittest.mock import MagicMock, patch

import pytest


# We test the pure helper functions that don't require Temporal runtime.
from apps.workflow.temporal.workflows import (
    INTERNAL_ACTIVITY_MAP,
    MCP_TOOL_MAP,
    GateResult,
    SimpleWorkflowInput,
    _build_mcp_kwargs,
    _build_step_args,
    _eval_condition,
    _resolve_dotted,
)


# ── Constants ─────────────────────────────────────────────────────────────────

def test_internal_activity_map_has_entries():
    assert "collect_case_facts" in INTERNAL_ACTIVITY_MAP
    assert "generate_complaint" in INTERNAL_ACTIVITY_MAP
    assert "suggest_arrangement" in INTERNAL_ACTIVITY_MAP
    assert "apply_arrangement" in INTERNAL_ACTIVITY_MAP


def test_mcp_tool_map_has_entries():
    assert "collect_case_facts" in MCP_TOOL_MAP
    assert "calculate_litigation_fee" in MCP_TOOL_MAP
    assert "search_companies" in MCP_TOOL_MAP


# ── SimpleWorkflowInput ──────────────────────────────────────────────────────

def test_simple_workflow_input():
    inp = SimpleWorkflowInput(case_id=1, run_id=2)
    assert inp.case_id == 1
    assert inp.run_id == 2


# ── GateResult ────────────────────────────────────────────────────────────────

def test_gate_result_defaults():
    g = GateResult()
    assert g.approved is False
    assert g.comment == ""


def test_gate_result_approved():
    g = GateResult(approved=True, comment="ok")
    assert g.approved is True
    assert g.comment == "ok"


# ── _resolve_dotted ──────────────────────────────────────────────────────────

def test_resolve_dotted_simple():
    ctx = {"a": {"b": {"c": 42}}}
    assert _resolve_dotted(ctx, "a.b.c") == 42


def test_resolve_dotted_missing_key():
    ctx = {"a": {"b": 1}}
    assert _resolve_dotted(ctx, "a.c") is None


def test_resolve_dotted_non_dict():
    assert _resolve_dotted("not_a_dict", "key") is None


def test_resolve_dotted_empty_path():
    ctx = {"a": 1}
    # Empty path splits to [""], which tries to get key ""
    result = _resolve_dotted(ctx, "")
    assert result is None or result == ctx.get("")


def test_resolve_dotted_none_value():
    ctx = {"a": None}
    # "a" returns None, then trying to iterate "b" from None -> non-dict
    assert _resolve_dotted(ctx, "a.b") is None


# ── _eval_condition ──────────────────────────────────────────────────────────

def test_eval_condition_eq_true():
    step = {"config": {"field": "flag", "operator": "eq", "value": "yes"}}
    ctx = {"flag": "yes"}
    assert _eval_condition(step, ctx) is True


def test_eval_condition_eq_false():
    step = {"config": {"field": "flag", "operator": "eq", "value": "yes"}}
    ctx = {"flag": "no"}
    assert _eval_condition(step, ctx) is False


def test_eval_condition_neq():
    step = {"config": {"field": "flag", "operator": "neq", "value": "no"}}
    ctx = {"flag": "yes"}
    assert _eval_condition(step, ctx) is True


def test_eval_condition_gt():
    step = {"config": {"field": "count", "operator": "gt", "value": "5"}}
    ctx = {"count": 10}
    assert _eval_condition(step, ctx) is True
    ctx2 = {"count": 3}
    assert _eval_condition(step, ctx2) is False


def test_eval_condition_lt():
    step = {"config": {"field": "count", "operator": "lt", "value": "5"}}
    ctx = {"count": 3}
    assert _eval_condition(step, ctx) is True
    ctx2 = {"count": 10}
    assert _eval_condition(step, ctx2) is False


def test_eval_condition_contains():
    step = {"config": {"field": "text", "operator": "contains", "value": "违约"}}
    ctx = {"text": "被告违约未付款"}
    assert _eval_condition(step, ctx) is True
    ctx2 = {"text": "被告已付款"}
    assert _eval_condition(step, ctx2) is False


def test_eval_condition_exists():
    step = {"config": {"field": "data", "operator": "exists", "value": ""}}
    ctx = {"data": {"key": "val"}}
    assert _eval_condition(step, ctx) is True
    ctx2 = {}
    assert _eval_condition(step, ctx2) is False


def test_eval_condition_unknown_operator():
    step = {"config": {"field": "flag", "operator": "unknown_op", "value": "x"}}
    ctx = {"flag": "x"}
    assert _eval_condition(step, ctx) is False


def test_eval_condition_missing_field():
    step = {"config": {"field": "missing", "operator": "eq", "value": "x"}}
    ctx = {}
    assert _eval_condition(step, ctx) is False


def test_eval_condition_none_actual():
    step = {"config": {"field": "flag", "operator": "eq", "value": "None"}}
    ctx = {"flag": None}
    assert _eval_condition(step, ctx) is True


def test_eval_condition_gt_none_actual():
    step = {"config": {"field": "count", "operator": "gt", "value": "5"}}
    ctx = {}
    # actual is None -> float(None or 0) = 0 -> 0 > 5 = False
    assert _eval_condition(step, ctx) is False


def test_eval_condition_empty_config():
    step = {}
    ctx = {}
    assert _eval_condition(step, ctx) is False


# ── _build_step_args ──────────────────────────────────────────────────────────

def test_build_step_args_default_activity():
    step = {"type": "activity", "config": {}}
    args = _build_step_args(step, {}, case_id=1, run_id=2)
    assert args == [1]


def test_build_step_args_llm_type():
    step = {
        "type": "llm",
        "config": {
            "system_prompt": "You are a lawyer",
            "user_prompt_template": "Analyze case {{case_id}}",
        },
    }
    ctx = {"case_id": 42}
    args = _build_step_args(step, ctx, case_id=42, run_id=1)
    assert args[0] == "You are a lawyer"
    assert "42" in args[1]


def test_build_step_args_delay_type():
    step = {"type": "delay", "config": {"duration_minutes": 10}}
    args = _build_step_args(step, {}, case_id=1, run_id=2)
    assert args == [10.0]


def test_build_step_args_delay_default():
    step = {"type": "delay", "config": {}}
    args = _build_step_args(step, {}, case_id=1, run_id=2)
    assert args == [5.0]


def test_build_step_args_http_type():
    step = {
        "type": "http",
        "config": {
            "method": "POST",
            "url": "https://example.com",
            "headers": '{"Content-Type": "application/json"}',
            "body": '{"key": "value"}',
        },
    }
    args = _build_step_args(step, {}, case_id=1, run_id=2)
    assert args[0] == "POST"
    assert args[1] == "https://example.com"


def test_build_step_args_code_type():
    step = {"type": "code", "config": {"code": "print('hello')"}}
    ctx = {"case_id": 1}
    args = _build_step_args(step, ctx, case_id=1, run_id=2)
    assert args[0] == "print('hello')"
    assert args[1] == ctx


def test_build_step_args_template_resolution():
    step = {
        "type": "llm",
        "config": {
            "system_prompt": "system",
            "user_prompt_template": "Case {{case_id}} and {{step_outputs.collect.result}}",
        },
    }
    ctx = {"case_id": 5, "step_outputs": {"collect": {"result": "facts_data"}}}
    args = _build_step_args(step, ctx, case_id=5, run_id=1)
    assert "5" in args[1]
    assert "facts_data" in args[1]


def test_build_step_args_template_missing_variable():
    step = {
        "type": "llm",
        "config": {
            "system_prompt": "system",
            "user_prompt_template": "Value is {{missing.var}}",
        },
    }
    args = _build_step_args(step, {}, case_id=1, run_id=1)
    # missing var resolves to empty string
    assert "Value is " in args[1]


# ── _build_mcp_kwargs ────────────────────────────────────────────────────────

def test_build_mcp_kwargs_basic():
    step = {"config": {"param1": "value1"}}
    kwargs = _build_mcp_kwargs(step, {}, case_id=10, run_id=1)
    assert kwargs["case_id"] == 10
    assert kwargs["param1"] == "value1"


def test_build_mcp_kwargs_template_resolution():
    step = {"config": {"title": "Case {{case_id}} info"}}
    ctx = {"case_id": 42}
    kwargs = _build_mcp_kwargs(step, ctx, case_id=42, run_id=1)
    assert "42" in kwargs["title"]


def test_build_mcp_kwargs_previous_step():
    step = {"config": {"data": "{{previous_step.result.key}}"}}
    ctx = {"_last_output": {"result": {"key": "prev_value"}}}
    kwargs = _build_mcp_kwargs(step, ctx, case_id=1, run_id=1)
    assert kwargs["data"] == "prev_value"


def test_build_mcp_kwargs_numeric_values():
    step = {"config": {"count": 5, "rate": 0.5, "enabled": True}}
    kwargs = _build_mcp_kwargs(step, {}, case_id=1, run_id=1)
    assert kwargs["count"] == 5
    assert kwargs["rate"] == 0.5
    assert kwargs["enabled"] is True


def test_build_mcp_kwargs_empty_config():
    step = {"config": {}}
    kwargs = _build_mcp_kwargs(step, {}, case_id=1, run_id=1)
    assert kwargs == {"case_id": 1}


def test_build_mcp_kwargs_missing_config():
    step = {}
    kwargs = _build_mcp_kwargs(step, {}, case_id=1, run_id=1)
    assert kwargs == {"case_id": 1}


def test_build_mcp_kwargs_previous_step_missing():
    step = {"config": {"data": "{{previous_step.result.key}}"}}
    ctx = {}  # no _last_output
    kwargs = _build_mcp_kwargs(step, ctx, case_id=1, run_id=1)
    assert kwargs["data"] == ""
