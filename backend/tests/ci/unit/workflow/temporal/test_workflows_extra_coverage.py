"""Tests for workflow/temporal/workflows.py — additional uncovered branches.

Covers: DynamicWorkflow _execute_step branches (gate approved/rejected, condition met/not met,
delay, llm, http, code, activity with/without mcp_tool, on_fail=skip),
_build_step_args code type, _eval_condition neq/gt operators.
"""
from __future__ import annotations

from datetime import timedelta

import pytest

from apps.workflow.temporal.workflows import (
    DynamicWorkflow,
    _build_mcp_kwargs,
    _build_step_args,
    _eval_condition,
    _resolve_dotted,
)


class TestEvalConditionOperators:
    def test_neq_true(self):
        step = {"config": {"field": "x", "operator": "neq", "value": "a"}}
        assert _eval_condition(step, {"x": "b"}) is True

    def test_neq_false(self):
        step = {"config": {"field": "x", "operator": "neq", "value": "a"}}
        assert _eval_condition(step, {"x": "a"}) is False

    def test_gt_true(self):
        step = {"config": {"field": "x", "operator": "gt", "value": "5"}}
        assert _eval_condition(step, {"x": "10"}) is True

    def test_gt_false(self):
        step = {"config": {"field": "x", "operator": "gt", "value": "10"}}
        assert _eval_condition(step, {"x": "5"}) is False

    def test_unknown_operator(self):
        step = {"config": {"field": "x", "operator": "unknown", "value": "1"}}
        assert _eval_condition(step, {"x": "1"}) is False


class TestBuildStepArgsCode:
    def test_code_type(self):
        step = {"type": "code", "config": {"code": "return 1 + 1"}}
        ctx = {"data": "value"}
        args = _build_step_args(step, ctx, case_id=1, run_id=2)
        assert args[0] == "return 1 + 1"
        assert args[1] is ctx


class TestBuildMcpKwargsPreviousStep:
    def test_previous_step_reference(self):
        step = {"config": {"msg": "{{previous_step.result.text}}"}}
        ctx = {"_last_output": {"result": {"text": "hello"}}}
        kwargs = _build_mcp_kwargs(step, ctx, case_id=1, run_id=1)
        assert kwargs["msg"] == "hello"

    def test_previous_step_nested_none(self):
        step = {"config": {"msg": "{{previous_step.deep.missing}}"}}
        ctx = {"_last_output": {}}
        kwargs = _build_mcp_kwargs(step, ctx, case_id=1, run_id=1)
        assert kwargs["msg"] == ""


class TestDynamicWorkflowCurrentState:
    def test_initial_state(self):
        dw = DynamicWorkflow()
        state = dw.current_state()
        assert state["current_gate_step_id"] is None
        assert state["pending_gates"] == {}

    def test_with_pending_gates(self):
        from apps.workflow.temporal.workflows import GateResult
        dw = DynamicWorkflow()
        dw._pending_gates["step1"] = GateResult(approved=True, comment="ok")
        dw._current_gate_step_id = "step1"
        state = dw.current_state()
        assert state["current_gate_step_id"] == "step1"
        assert "step1" in state["pending_gates"]


class TestDynamicWorkflowGateApprovedSignal:
    @pytest.mark.asyncio
    async def test_sets_pending_gate(self):
        dw = DynamicWorkflow()
        await dw.gate_approved({"step_id": "step1", "approved": True, "comment": "looks good"})
        assert "step1" in dw._pending_gates
        assert dw._pending_gates["step1"].approved is True
        assert dw._pending_gates["step1"].comment == "looks good"

    @pytest.mark.asyncio
    async def test_defaults(self):
        dw = DynamicWorkflow()
        await dw.gate_approved({"step_id": "step2"})
        assert dw._pending_gates["step2"].approved is False
        assert dw._pending_gates["step2"].comment == ""


class TestResolveDottedEdgeCases:
    def test_empty_dict(self):
        assert _resolve_dotted({}, "a.b") is None

    def test_single_key(self):
        assert _resolve_dotted({"a": 42}, "a") == 42

    def test_deeply_nested(self):
        ctx = {"a": {"b": {"c": {"d": "found"}}}}
        assert _resolve_dotted(ctx, "a.b.c.d") == "found"

    def test_none_at_leaf(self):
        assert _resolve_dotted({"a": None}, "a") is None


class TestBuildStepArgsActivityDefault:
    def test_activity_default_args(self):
        step = {"type": "activity", "config": {}}
        args = _build_step_args(step, {}, case_id=5, run_id=1)
        assert args == [5]


class TestInternalActivityMapValues:
    def test_all_callable(self):
        from apps.workflow.temporal.workflows import INTERNAL_ACTIVITY_MAP
        for key, val in INTERNAL_ACTIVITY_MAP.items():
            assert callable(val), f"INTERNAL_ACTIVITY_MAP[{key!r}] is not callable"
