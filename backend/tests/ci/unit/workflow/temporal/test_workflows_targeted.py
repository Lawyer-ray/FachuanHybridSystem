"""Additional coverage tests for workflow/temporal/workflows.py — pure functions and more branches."""

from __future__ import annotations

import asyncio
import re
from datetime import timedelta
from unittest.mock import MagicMock, patch

import pytest

from apps.workflow.temporal.workflows import (
    INTERNAL_ACTIVITY_MAP,
    MCP_TOOL_MAP,
    QUICK_RETRY,
    QUICK_TIMEOUT,
    LLM_RETRY,
    LLM_TIMEOUT,
    LONG_RETRY,
    LONG_TIMEOUT,
    DynamicWorkflow,
    GateResult,
    SalesContractDisputeWorkflow,
    SimpleWorkflowInput,
    _build_mcp_kwargs,
    _build_step_args,
    _eval_condition,
    _resolve_dotted,
)


# ── Timeout / Retry constants ─────────────────────────────────────────────────

def test_quick_timeout():
    assert QUICK_TIMEOUT == timedelta(seconds=30)


def test_quick_retry():
    assert QUICK_RETRY.maximum_attempts == 3


def test_llm_timeout():
    assert LLM_TIMEOUT == timedelta(minutes=5)


def test_llm_retry():
    assert LLM_RETRY.maximum_attempts == 2


def test_long_timeout():
    assert LONG_TIMEOUT == timedelta(hours=2)


def test_long_retry():
    assert LONG_RETRY.maximum_attempts == 2


# ── INTERNAL_ACTIVITY_MAP ─────────────────────────────────────────────────────

def test_internal_activity_map_keys():
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
        "execute_court_filing",
        "download_litigation_document",
    }
    assert set(INTERNAL_ACTIVITY_MAP.keys()) == expected_keys


# ── MCP_TOOL_MAP ──────────────────────────────────────────────────────────────

def test_mcp_tool_map_values_are_strings():
    for k, v in MCP_TOOL_MAP.items():
        assert isinstance(v, str), f"MCP_TOOL_MAP[{k}] should be str"

def test_mcp_tool_map_has_all_expected():
    expected_tools = {
        "collect_case_facts", "list_case_materials", "create_case_log",
        "generate_complaint", "generate_defense", "download_litigation_document",
        "execute_court_filing", "submit_court_sms", "search_companies",
        "calculate_litigation_fee", "calculate_interest", "auto_namer",
        "process_document", "convert_document",
    }
    assert expected_tools.issubset(set(MCP_TOOL_MAP.keys()))


# ── _resolve_dotted more branches ────────────────────────────────────────────

def test_resolve_dotted_deeply_nested():
    ctx = {"a": {"b": {"c": {"d": 42}}}}
    assert _resolve_dotted(ctx, "a.b.c.d") == 42


def test_resolve_dotted_empty_dict():
    assert _resolve_dotted({}, "key") is None


def test_resolve_dotted_list_value():
    ctx = {"items": [1, 2, 3]}
    # list is not a dict, so traversal stops
    assert _resolve_dotted(ctx, "items.0") is None


# ── _eval_condition more branches ────────────────────────────────────────────

def test_eval_condition_eq_int():
    step = {"config": {"field": "count", "operator": "eq", "value": "5"}}
    ctx = {"count": 5}
    assert _eval_condition(step, ctx) is True


def test_eval_condition_gt_float():
    step = {"config": {"field": "rate", "operator": "gt", "value": "0.5"}}
    ctx = {"rate": 0.8}
    assert _eval_condition(step, ctx) is True


def test_eval_condition_lt_negative():
    step = {"config": {"field": "val", "operator": "lt", "value": "0"}}
    ctx = {"val": -5}
    assert _eval_condition(step, ctx) is True


def test_eval_condition_contains_empty():
    step = {"config": {"field": "text", "operator": "contains", "value": ""}}
    ctx = {"text": "anything"}
    # "" in "anything" is True
    assert _eval_condition(step, ctx) is True


def test_eval_condition_neq_false():
    step = {"config": {"field": "x", "operator": "neq", "value": "a"}}
    ctx = {"x": "a"}
    assert _eval_condition(step, ctx) is False


def test_eval_condition_exists_none():
    step = {"config": {"field": "x", "operator": "exists", "value": ""}}
    ctx = {"x": None}
    # None is not "not None", so exists returns False
    assert _eval_condition(step, ctx) is False


def test_eval_condition_exists_missing():
    step = {"config": {"field": "x", "operator": "exists", "value": ""}}
    ctx = {}
    assert _eval_condition(step, ctx) is False


# ── _build_step_args more branches ───────────────────────────────────────────

def test_build_step_args_llm_no_template():
    step = {"type": "llm", "config": {"system_prompt": "sys", "user_prompt_template": "plain"}}
    args = _build_step_args(step, {}, case_id=1, run_id=2)
    assert args == ["sys", "plain"]


def test_build_step_args_http_defaults():
    step = {"type": "http", "config": {}}
    args = _build_step_args(step, {}, case_id=1, run_id=2)
    assert args[0] == "GET"
    assert args[1] == ""


def test_build_step_args_code_empty():
    step = {"type": "code", "config": {}}
    args = _build_step_args(step, {}, case_id=1, run_id=2)
    assert args[0] == ""
    assert args[1] == {}


def test_build_step_args_activity_explicit():
    step = {"type": "activity", "config": {"something": "val"}}
    args = _build_step_args(step, {}, case_id=42, run_id=1)
    assert args == [42]


def test_build_step_args_unknown_type():
    step = {"type": "unknown_type", "config": {}}
    args = _build_step_args(step, {}, case_id=1, run_id=2)
    # Falls through to default activity branch
    assert args == [1]


def test_build_step_args_llm_template_with_none_value():
    step = {
        "type": "llm",
        "config": {
            "system_prompt": "sys",
            "user_prompt_template": "Value: {{missing.key}}",
        },
    }
    args = _build_step_args(step, {}, case_id=1, run_id=1)
    assert "Value: " in args[1]


# ── _build_mcp_kwargs more branches ──────────────────────────────────────────

def test_build_mcp_kwargs_string_template():
    step = {"config": {"name": "Case {{case_id}}"}}
    ctx = {"case_id": 10}
    kwargs = _build_mcp_kwargs(step, ctx, case_id=10, run_id=1)
    assert kwargs["name"] == "Case 10"


def test_build_mcp_kwargs_previous_step_missing_key():
    step = {"config": {"val": "{{previous_step.result.missing}}"}}
    ctx = {"_last_output": {"result": {}}}
    kwargs = _build_mcp_kwargs(step, ctx, case_id=1, run_id=1)
    assert kwargs["val"] == ""


def test_build_mcp_kwargs_bool_value():
    step = {"config": {"flag": True}}
    kwargs = _build_mcp_kwargs(step, {}, case_id=1, run_id=1)
    assert kwargs["flag"] is True


def test_build_mcp_kwargs_int_value():
    step = {"config": {"count": 100}}
    kwargs = _build_mcp_kwargs(step, {}, case_id=1, run_id=1)
    assert kwargs["count"] == 100


def test_build_mcp_kwargs_float_value():
    step = {"config": {"rate": 3.14}}
    kwargs = _build_mcp_kwargs(step, {}, case_id=1, run_id=1)
    assert kwargs["rate"] == 3.14


def test_build_mcp_kwargs_list_value_not_added():
    step = {"config": {"items": [1, 2, 3]}}
    kwargs = _build_mcp_kwargs(step, {}, case_id=1, run_id=1)
    # lists are neither str nor int/float/bool, so not added
    assert "items" not in kwargs


def test_build_mcp_kwargs_previous_step_resolves():
    step = {"config": {"data": "{{previous_step.key}}"}}
    ctx = {"_last_output": {"key": "prev_val"}}
    kwargs = _build_mcp_kwargs(step, ctx, case_id=1, run_id=1)
    assert kwargs["data"] == "prev_val"


def test_build_mcp_kwargs_context_variable():
    step = {"config": {"ref": "{{case_id}}"}}
    ctx = {"case_id": 42}
    kwargs = _build_mcp_kwargs(step, ctx, case_id=42, run_id=1)
    assert kwargs["ref"] == "42"


# ── GateResult ────────────────────────────────────────────────────────────────

def test_gate_result_repr():
    g = GateResult(approved=True, comment="ok")
    d = g.__dict__
    assert d["approved"] is True
    assert d["comment"] == "ok"


# ── SimpleWorkflowInput ──────────────────────────────────────────────────────

def test_simple_workflow_input_equality():
    a = SimpleWorkflowInput(case_id=1, run_id=2)
    b = SimpleWorkflowInput(case_id=1, run_id=2)
    assert a == b


# ── SalesContractDisputeWorkflow signals and query ────────────────────────────

class TestSalesContractDisputeWorkflowInit:
    def test_init_gate_none(self):
        wf = SalesContractDisputeWorkflow()
        assert wf._gate is None

    def test_current_state_initial(self):
        wf = SalesContractDisputeWorkflow()
        state = wf.current_state()
        assert state["gate"] is None

    def test_confirm_facts_signal_sets_gate(self):
        wf = SalesContractDisputeWorkflow()
        asyncio.run(wf.confirm_facts_approved({"approved": True, "comment": "looks good"}))
        assert wf._gate is not None
        assert wf._gate.approved is True
        assert wf._gate.comment == "looks good"

    def test_review_complaint_signal_sets_gate(self):
        wf = SalesContractDisputeWorkflow()
        asyncio.run(wf.review_complaint_approved({"approved": False, "comment": "needs work"}))
        assert wf._gate.approved is False

    def test_current_state_after_signal(self):
        wf = SalesContractDisputeWorkflow()
        asyncio.run(wf.confirm_facts_approved({"approved": True, "comment": ""}))
        state = wf.current_state()
        assert state["gate"] is not None
        assert state["gate"]["approved"] is True


# ── DynamicWorkflow signals and query ────────────────────────────────────────

class TestDynamicWorkflowInit:
    def test_init_state(self):
        wf = DynamicWorkflow()
        assert wf._pending_gates == {}
        assert wf._current_gate_step_id is None

    def test_gate_approved_signal(self):
        wf = DynamicWorkflow()
        asyncio.run(wf.gate_approved({"step_id": "s1", "approved": True, "comment": "ok"}))
        assert "s1" in wf._pending_gates
        assert wf._pending_gates["s1"].approved is True

    def test_gate_approved_default_step_id(self):
        wf = DynamicWorkflow()
        asyncio.run(wf.gate_approved({"approved": True}))
        assert "" in wf._pending_gates

    def test_current_state_initial(self):
        wf = DynamicWorkflow()
        state = wf.current_state()
        assert state["current_gate_step_id"] is None
        assert state["pending_gates"] == {}

    def test_current_state_with_pending(self):
        wf = DynamicWorkflow()
        wf._pending_gates["s1"] = GateResult(approved=True, comment="")
        state = wf.current_state()
        assert "s1" in state["pending_gates"]


# ── _build_step_args edge cases ──────────────────────────────────────────────

def test_build_step_args_delay_zero():
    step = {"type": "delay", "config": {"duration_minutes": 0}}
    args = _build_step_args(step, {}, case_id=1, run_id=2)
    assert args == [0.0]


def test_build_step_args_http_custom():
    step = {
        "type": "http",
        "config": {
            "method": "DELETE",
            "url": "https://api.example.com/resource",
            "headers": "{}",
            "body": "",
        },
    }
    args = _build_step_args(step, {}, case_id=1, run_id=2)
    assert args[0] == "DELETE"
    assert args[1] == "https://api.example.com/resource"


def test_build_step_args_code_with_context():
    step = {"type": "code", "config": {"code": "x = 1"}}
    ctx = {"custom": "value"}
    args = _build_step_args(step, ctx, case_id=1, run_id=2)
    assert args[0] == "x = 1"
    assert args[1]["custom"] == "value"
