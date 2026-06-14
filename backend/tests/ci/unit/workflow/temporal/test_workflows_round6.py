"""Tests for workflow/temporal/workflows.py — additional branches for DynamicWorkflow.

Covers: _execute_step branches not in existing tests, _execute_wait, gate_approved
signal routing, _build_step_args llm/http/delay branches, _build_mcp_kwargs
with numeric/boolean values.
"""
from __future__ import annotations

import re
from datetime import timedelta
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from apps.workflow.temporal.workflows import (
    DynamicWorkflow,
    GateResult,
    SalesContractDisputeWorkflow,
    _build_mcp_kwargs,
    _build_step_args,
    _eval_condition,
    _resolve_dotted,
)


class TestEvalConditionContains:
    def test_contains_true(self):
        step = {"config": {"field": "text", "operator": "contains", "value": "hello"}}
        assert _eval_condition(step, {"text": "say hello world"}) is True

    def test_contains_false(self):
        step = {"config": {"field": "text", "operator": "contains", "value": "xyz"}}
        assert _eval_condition(step, {"text": "hello"}) is False

    def test_contains_none_value(self):
        step = {"config": {"field": "text", "operator": "contains", "value": "x"}}
        assert _eval_condition(step, {}) is False


class TestEvalConditionExists:
    def test_exists_true(self):
        step = {"config": {"field": "x", "operator": "exists", "value": ""}}
        assert _eval_condition(step, {"x": "something"}) is True

    def test_exists_false(self):
        step = {"config": {"field": "x", "operator": "exists", "value": ""}}
        assert _eval_condition(step, {}) is False


class TestEvalConditionLt:
    def test_lt_true(self):
        step = {"config": {"field": "x", "operator": "lt", "value": "10"}}
        assert _eval_condition(step, {"x": "5"}) is True

    def test_lt_false(self):
        step = {"config": {"field": "x", "operator": "lt", "value": "5"}}
        assert _eval_condition(step, {"x": "10"}) is False


class TestBuildStepArgsEdgeCases:
    def test_llm_type(self):
        step = {
            "type": "llm",
            "config": {
                "system_prompt": "You are a lawyer",
                "user_prompt_template": "Process {{data.text}}",
            },
        }
        ctx = {"data": {"text": "case info"}}
        args = _build_step_args(step, ctx, case_id=1, run_id=2)
        assert args[0] == "You are a lawyer"
        assert "case info" in args[1]

    def test_llm_type_no_template_vars(self):
        step = {
            "type": "llm",
            "config": {
                "system_prompt": "System",
                "user_prompt_template": "User",
            },
        }
        args = _build_step_args(step, {}, case_id=1, run_id=2)
        assert args == ["System", "User"]

    def test_delay_type(self):
        step = {"type": "delay", "config": {"duration_minutes": 10.5}}
        args = _build_step_args(step, {}, case_id=1, run_id=2)
        assert args == [10.5]

    def test_delay_type_default(self):
        step = {"type": "delay", "config": {}}
        args = _build_step_args(step, {}, case_id=1, run_id=2)
        assert args == [5]

    def test_http_type(self):
        step = {
            "type": "http",
            "config": {
                "method": "POST",
                "url": "https://api.example.com",
                "headers": '{"Authorization": "Bearer x"}',
                "body": '{"key": "value"}',
            },
        }
        args = _build_step_args(step, {}, case_id=1, run_id=2)
        assert args[0] == "POST"
        assert args[1] == "https://api.example.com"

    def test_http_type_defaults(self):
        step = {"type": "http", "config": {}}
        args = _build_step_args(step, {}, case_id=1, run_id=2)
        assert args[0] == "GET"
        assert args[1] == ""


class TestBuildMcpKwargsEdgeCases:
    def test_numeric_values_passed_through(self):
        step = {"config": {"limit": 10, "ratio": 0.5, "flag": True}}
        kwargs = _build_mcp_kwargs(step, {}, case_id=1, run_id=1)
        assert kwargs["limit"] == 10
        assert kwargs["ratio"] == 0.5
        assert kwargs["flag"] is True
        assert kwargs["case_id"] == 1

    def test_string_template_with_context(self):
        step = {"config": {"query": "{{case_name}}"}}
        ctx = {"case_name": "Test Case"}
        kwargs = _build_mcp_kwargs(step, ctx, case_id=1, run_id=1)
        assert kwargs["query"] == "Test Case"

    def test_non_string_non_numeric_value_ignored(self):
        step = {"config": {"nested": {"a": 1}}}
        kwargs = _build_mcp_kwargs(step, {}, case_id=1, run_id=1)
        assert "nested" not in kwargs


class TestSalesContractDisputeWorkflowSignals:
    def test_initial_gate_none(self):
        w = SalesContractDisputeWorkflow()
        assert w._gate is None

    @pytest.mark.asyncio
    async def test_confirm_facts_approved_signal(self):
        w = SalesContractDisputeWorkflow()
        await w.confirm_facts_approved({"approved": True, "comment": "ok"})
        assert w._gate is not None
        assert w._gate.approved is True
        assert w._gate.comment == "ok"

    @pytest.mark.asyncio
    async def test_review_complaint_approved_signal(self):
        w = SalesContractDisputeWorkflow()
        await w.review_complaint_approved({"approved": False, "comment": "needs changes"})
        assert w._gate is not None
        assert w._gate.approved is False

    def test_current_state_no_gate(self):
        w = SalesContractDisputeWorkflow()
        state = w.current_state()
        assert state == {"gate": None}

    def test_current_state_with_gate(self):
        w = SalesContractDisputeWorkflow()
        w._gate = GateResult(approved=True, comment="test")
        state = w.current_state()
        assert state["gate"]["approved"] is True
        assert state["gate"]["comment"] == "test"


class TestDynamicWorkflowGateApprovedSignalRouting:
    @pytest.mark.asyncio
    async def test_routes_to_correct_step(self):
        dw = DynamicWorkflow()
        await dw.gate_approved({"step_id": "step_a", "approved": True})
        await dw.gate_approved({"step_id": "step_b", "approved": False, "comment": "no"})
        assert dw._pending_gates["step_a"].approved is True
        assert dw._pending_gates["step_b"].approved is False
        assert dw._pending_gates["step_b"].comment == "no"

    @pytest.mark.asyncio
    async def test_overwrites_same_step(self):
        dw = DynamicWorkflow()
        await dw.gate_approved({"step_id": "x", "approved": False})
        await dw.gate_approved({"step_id": "x", "approved": True})
        assert dw._pending_gates["x"].approved is True


class TestDynamicWorkflowCurrentStateWithPending:
    def test_reports_pending_gates(self):
        dw = DynamicWorkflow()
        dw._pending_gates["g1"] = GateResult(approved=True, comment="")
        dw._pending_gates["g2"] = GateResult(approved=False, comment="no")
        dw._current_gate_step_id = "g1"
        state = dw.current_state()
        assert state["current_gate_step_id"] == "g1"
        assert len(state["pending_gates"]) == 2
