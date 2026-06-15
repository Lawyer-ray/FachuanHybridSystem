"""workflows.py — round8 tests for remaining uncovered branches.

Covers 145 missing: SalesContractDisputeWorkflow paths, DynamicWorkflow.run
full execution, _execute_step branches, _execute_gate, _build_step_args
template resolution, _build_mcp_kwargs, signal handlers, query handlers.
"""
from __future__ import annotations

import re
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from apps.workflow.temporal.workflows import (
    DynamicWorkflow,
    GateResult,
    SalesContractDisputeWorkflow,
    INTERNAL_ACTIVITY_MAP,
    MCP_TOOL_MAP,
    _build_mcp_kwargs,
    _build_step_args,
    _eval_condition,
    _resolve_dotted,
)


# ── _resolve_dotted ────────────────────────────────────────────────────


class TestResolveDottedRound8:
    def test_empty_path(self):
        assert _resolve_dotted({"a": 1}, "") is None

    def test_deeply_nested(self):
        ctx = {"a": {"b": {"c": {"d": 42}}}}
        assert _resolve_dotted(ctx, "a.b.c.d") == 42

    def test_none_value(self):
        assert _resolve_dotted({"a": None}, "a") is None

    def test_path_through_non_dict(self):
        assert _resolve_dotted({"a": [1, 2]}, "a.0") is None


# ── _eval_condition ────────────────────────────────────────────────────


class TestEvalConditionRound8:
    def test_lt_true(self):
        step = {"config": {"field": "x", "operator": "lt", "value": "10"}}
        assert _eval_condition(step, {"x": "5"}) is True

    def test_lt_false(self):
        step = {"config": {"field": "x", "operator": "lt", "value": "3"}}
        assert _eval_condition(step, {"x": "5"}) is False

    def test_contains_true(self):
        step = {"config": {"field": "x", "operator": "contains", "value": "ell"}}
        assert _eval_condition(step, {"x": "hello"}) is True

    def test_contains_false(self):
        step = {"config": {"field": "x", "operator": "contains", "value": "xyz"}}
        assert _eval_condition(step, {"x": "hello"}) is False

    def test_exists_true(self):
        step = {"config": {"field": "x", "operator": "exists"}}
        assert _eval_condition(step, {"x": "value"}) is True

    def test_exists_false(self):
        step = {"config": {"field": "y", "operator": "exists"}}
        assert _eval_condition(step, {"x": "value"}) is False

    def test_empty_config(self):
        assert _eval_condition({}, {"x": 1}) is False


# ── _build_step_args ───────────────────────────────────────────────────


class TestBuildStepArgsRound8:
    def test_llm_type(self):
        step = {"type": "llm", "config": {"system_prompt": "sys", "user_prompt_template": "hello {{name}}"}}
        ctx = {"name": "world"}
        result = _build_step_args(step, ctx, 1, 1)
        assert result == ["sys", "hello world"]

    def test_delay_type(self):
        step = {"type": "delay", "config": {"duration_minutes": 10}}
        result = _build_step_args(step, {}, 1, 1)
        assert result == [10.0]

    def test_delay_default(self):
        step = {"type": "delay", "config": {}}
        result = _build_step_args(step, {}, 1, 1)
        assert result == [5.0]

    def test_http_type(self):
        step = {"type": "http", "config": {"method": "POST", "url": "http://x", "headers": "H", "body": "B"}}
        result = _build_step_args(step, {}, 1, 1)
        assert result == ["POST", "http://x", "H", "B"]

    def test_http_defaults(self):
        step = {"type": "http", "config": {}}
        result = _build_step_args(step, {}, 1, 1)
        assert result == ["GET", "", "", ""]

    def test_code_type(self):
        step = {"type": "code", "config": {"code": "print(1)"}}
        ctx = {"a": 1}
        result = _build_step_args(step, ctx, 1, 1)
        assert result == ["print(1)", ctx]

    def test_activity_default(self):
        step = {"type": "activity"}
        result = _build_step_args(step, {}, 42, 7)
        assert result == [42]

    def test_template_variable_not_found(self):
        step = {"type": "llm", "config": {"system_prompt": "{{missing.path}}"}}
        result = _build_step_args(step, {}, 1, 1)
        assert result == ["", ""]  # system_prompt + user_prompt_template (empty)


# ── _build_mcp_kwargs ──────────────────────────────────────────────────


class TestBuildMcpKwargsRound8:
    def test_basic_kwargs(self):
        step = {"config": {"param1": "value1", "param2": 42}}
        result = _build_mcp_kwargs(step, {}, 1, 1)
        assert result["case_id"] == 1
        assert result["param1"] == "value1"
        assert result["param2"] == 42

    def test_template_from_context(self):
        step = {"config": {"msg": "case {{case_id}} run {{run_id}}"}}
        result = _build_mcp_kwargs(step, {"case_id": 10, "run_id": 20}, 10, 20)
        assert result["msg"] == "case 10 run 20"

    def test_previous_step_reference(self):
        step = {"config": {"ref": "{{previous_step.result.name}}"}}
        ctx = {"_last_output": {"result": {"name": "test"}}}
        result = _build_mcp_kwargs(step, ctx, 1, 1)
        assert result["ref"] == "test"

    def test_bool_and_float_values(self):
        step = {"config": {"flag": True, "ratio": 0.5}}
        result = _build_mcp_kwargs(step, {}, 1, 1)
        assert result["flag"] is True
        assert result["ratio"] == 0.5

    def test_empty_config(self):
        step = {"config": {}}
        result = _build_mcp_kwargs(step, {}, 1, 1)
        assert result == {"case_id": 1}

    def test_non_string_non_numeric_value_skipped(self):
        step = {"config": {"items": [1, 2, 3]}}
        result = _build_mcp_kwargs(step, {}, 1, 1)
        assert "items" not in result


# ── SalesContractDisputeWorkflow signal handlers ────────────────────────


class TestSalesContractWorkflowSignals:
    def test_confirm_facts_approved(self):
        wf = SalesContractDisputeWorkflow.__new__(SalesContractDisputeWorkflow)
        wf._gate = None

        async def set_gate():
            await wf.confirm_facts_approved({"approved": True, "comment": "OK"})

        import asyncio
        asyncio.get_event_loop().run_until_complete(set_gate())

        assert wf._gate is not None
        assert wf._gate.approved is True
        assert wf._gate.comment == "OK"

    def test_review_complaint_approved(self):
        wf = SalesContractDisputeWorkflow.__new__(SalesContractDisputeWorkflow)
        wf._gate = None

        async def set_gate():
            await wf.review_complaint_approved({"approved": False, "comment": "reject"})

        import asyncio
        asyncio.get_event_loop().run_until_complete(set_gate())

        assert wf._gate is not None
        assert wf._gate.approved is False
        assert wf._gate.comment == "reject"

    def test_current_state_no_gate(self):
        wf = SalesContractDisputeWorkflow.__new__(SalesContractDisputeWorkflow)
        wf._gate = None
        state = wf.current_state()
        assert state["gate"] is None

    def test_current_state_with_gate(self):
        wf = SalesContractDisputeWorkflow.__new__(SalesContractDisputeWorkflow)
        wf._gate = GateResult(approved=True, comment="yes")
        state = wf.current_state()
        assert state["gate"]["approved"] is True
        assert state["gate"]["comment"] == "yes"


# ── DynamicWorkflow signal & query ─────────────────────────────────────


class TestDynamicWorkflowSignalsAndQuery:
    def test_gate_approved_signal(self):
        wf = DynamicWorkflow.__new__(DynamicWorkflow)
        wf._pending_gates = {}

        async def signal():
            await wf.gate_approved({"step_id": "s1", "approved": True, "comment": "ok"})

        import asyncio
        asyncio.get_event_loop().run_until_complete(signal())

        assert "s1" in wf._pending_gates
        assert wf._pending_gates["s1"].approved is True

    def test_gate_approved_default_step_id(self):
        wf = DynamicWorkflow.__new__(DynamicWorkflow)
        wf._pending_gates = {}

        async def signal():
            await wf.gate_approved({"approved": True})

        import asyncio
        asyncio.get_event_loop().run_until_complete(signal())

        assert "" in wf._pending_gates

    def test_current_state(self):
        wf = DynamicWorkflow.__new__(DynamicWorkflow)
        wf._pending_gates = {"s1": GateResult(approved=True, comment="yes")}
        wf._current_gate_step_id = "s1"

        state = wf.current_state()
        assert state["current_gate_step_id"] == "s1"
        assert "s1" in state["pending_gates"]


# ── GateResult ─────────────────────────────────────────────────────────


class TestGateResult:
    def test_defaults(self):
        g = GateResult()
        assert g.approved is False
        assert g.comment == ""

    def test_custom(self):
        g = GateResult(approved=True, comment="ok")
        assert g.approved is True
        assert g.comment == "ok"


# ── INTERNAL_ACTIVITY_MAP & MCP_TOOL_MAP ───────────────────────────────


class TestActivityMaps:
    def test_internal_activity_map_has_entries(self):
        assert len(INTERNAL_ACTIVITY_MAP) > 0
        assert "collect_case_facts" in INTERNAL_ACTIVITY_MAP

    def test_mcp_tool_map_has_entries(self):
        assert len(MCP_TOOL_MAP) > 0
        assert "get_case" in MCP_TOOL_MAP.values()


# ── DynamicWorkflow._execute_step branches ─────────────────────────────


class TestDynamicWorkflowExecuteStepBranches:
    @pytest.mark.asyncio
    async def test_condition_step(self):
        wf = DynamicWorkflow.__new__(DynamicWorkflow)
        wf._pending_gates = {}
        wf._current_gate_step_id = None

        step = {
            "id": "cond1",
            "name": "Check",
            "type": "condition",
            "config": {"field": "case_id", "operator": "eq", "value": "42"},
        }

        with patch("apps.workflow.temporal.workflows.workflow") as mock_wf:
            mock_wf.execute_activity = AsyncMock()
            result = await wf._execute_step(
                step=step, step_id="cond1", step_name="Check",
                step_type="condition", mcp_tool=None,
                case_id=42, run_id=1, context={"case_id": 42}, timeout_hours=1,
            )
        assert result == {"met": True}

    @pytest.mark.asyncio
    async def test_condition_step_not_met(self):
        wf = DynamicWorkflow.__new__(DynamicWorkflow)
        wf._pending_gates = {}

        step = {
            "id": "cond1",
            "name": "Check",
            "type": "condition",
            "config": {"field": "case_id", "operator": "eq", "value": "99"},
        }

        with patch("apps.workflow.temporal.workflows.workflow") as mock_wf:
            mock_wf.execute_activity = AsyncMock()
            result = await wf._execute_step(
                step=step, step_id="cond1", step_name="Check",
                step_type="condition", mcp_tool=None,
                case_id=42, run_id=1, context={"case_id": 42}, timeout_hours=1,
            )
        assert result == {"met": False}

    @pytest.mark.asyncio
    async def test_activity_step_no_mapping(self):
        wf = DynamicWorkflow.__new__(DynamicWorkflow)
        wf._pending_gates = {}

        step = {"id": "nonexistent_step", "name": "No Map"}

        with patch("apps.workflow.temporal.workflows.workflow") as mock_wf:
            mock_wf.execute_activity = AsyncMock()
            with pytest.raises(ValueError, match="无 mcp_tool 且无 internal activity"):
                await wf._execute_step(
                    step=step, step_id="nonexistent_step", step_name="No Map",
                    step_type="activity", mcp_tool=None,
                    case_id=1, run_id=1, context={}, timeout_hours=1,
                )

    @pytest.mark.asyncio
    async def test_activity_step_with_mcp_tool(self):
        wf = DynamicWorkflow.__new__(DynamicWorkflow)
        wf._pending_gates = {}

        step = {"id": "act1", "name": "Act", "config": {"param": "val"}}

        with patch("apps.workflow.temporal.workflows.workflow") as mock_wf:
            mock_wf.execute_activity = AsyncMock(return_value={"result": "ok"})
            result = await wf._execute_step(
                step=step, step_id="act1", step_name="Act",
                step_type="activity", mcp_tool="get_case",
                case_id=1, run_id=1, context={}, timeout_hours=1,
            )
        assert result == {"result": "ok"}

    @pytest.mark.asyncio
    async def test_llm_step(self):
        wf = DynamicWorkflow.__new__(DynamicWorkflow)
        wf._pending_gates = {}

        step = {
            "id": "llm1", "name": "LLM",
            "type": "llm",
            "config": {"system_prompt": "sys", "user_prompt_template": "hello"},
        }

        with patch("apps.workflow.temporal.workflows.workflow") as mock_wf:
            mock_wf.execute_activity = AsyncMock(return_value={"output": "done"})
            result = await wf._execute_step(
                step=step, step_id="llm1", step_name="LLM",
                step_type="llm", mcp_tool=None,
                case_id=1, run_id=1, context={}, timeout_hours=1,
            )
        assert result == {"output": "done"}

    @pytest.mark.asyncio
    async def test_http_step(self):
        wf = DynamicWorkflow.__new__(DynamicWorkflow)
        wf._pending_gates = {}

        step = {
            "id": "http1", "name": "HTTP",
            "type": "http",
            "config": {"method": "GET", "url": "http://test"},
        }

        with patch("apps.workflow.temporal.workflows.workflow") as mock_wf:
            mock_wf.execute_activity = AsyncMock(return_value={"status": 200})
            result = await wf._execute_step(
                step=step, step_id="http1", step_name="HTTP",
                step_type="http", mcp_tool=None,
                case_id=1, run_id=1, context={}, timeout_hours=1,
            )
        assert result == {"status": 200}

    @pytest.mark.asyncio
    async def test_code_step(self):
        wf = DynamicWorkflow.__new__(DynamicWorkflow)
        wf._pending_gates = {}

        step = {
            "id": "code1", "name": "Code",
            "type": "code",
            "config": {"code": "return 42"},
        }

        with patch("apps.workflow.temporal.workflows.workflow") as mock_wf:
            mock_wf.execute_activity = AsyncMock(return_value={"output": 42})
            result = await wf._execute_step(
                step=step, step_id="code1", step_name="Code",
                step_type="code", mcp_tool=None,
                case_id=1, run_id=1, context={}, timeout_hours=1,
            )
        assert result == {"output": 42}

    @pytest.mark.asyncio
    async def test_delay_step(self):
        wf = DynamicWorkflow.__new__(DynamicWorkflow)
        wf._pending_gates = {}

        step = {
            "id": "delay1", "name": "Delay",
            "type": "delay",
            "config": {"duration_minutes": 2},
        }

        with patch("apps.workflow.temporal.workflows.workflow") as mock_wf:
            mock_wf.execute_activity = AsyncMock()
            result = await wf._execute_step(
                step=step, step_id="delay1", step_name="Delay",
                step_type="delay", mcp_tool=None,
                case_id=1, run_id=1, context={}, timeout_hours=1,
            )
        assert result == {}


# ── DynamicWorkflow.run ────────────────────────────────────────────────


class TestDynamicWorkflowRun:
    @pytest.mark.asyncio
    async def test_empty_steps(self):
        wf = DynamicWorkflow.__new__(DynamicWorkflow)
        wf._pending_gates = {}
        wf._current_gate_step_id = None

        with patch("apps.workflow.temporal.workflows.workflow") as mock_wf:
            mock_wf.execute_activity = AsyncMock(return_value={"steps_schema": []})
            result = await wf.run({"case_id": 1, "run_id": 1, "template_id": 1})
        assert result["status"] == "completed"
        assert "模板无步骤定义" in result["message"]

    @pytest.mark.asyncio
    async def test_steps_as_dict(self):
        wf = DynamicWorkflow.__new__(DynamicWorkflow)
        wf._pending_gates = {}
        wf._current_gate_step_id = None

        with patch("apps.workflow.temporal.workflows.workflow") as mock_wf:
            mock_wf.execute_activity = AsyncMock(return_value={"steps_schema": {"steps": []}})
            result = await wf.run({"case_id": 1, "run_id": 1, "template_id": 1})
        assert result["status"] == "completed"

    @pytest.mark.asyncio
    async def test_step_exception_skip(self):
        wf = DynamicWorkflow.__new__(DynamicWorkflow)
        wf._pending_gates = {}
        wf._current_gate_step_id = None

        call_count = 0

        async def mock_activity(*args, **kwargs):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                # fetch_template_schema
                return {"steps_schema": [
                    {"id": "s1", "name": "S1", "type": "condition", "config": {"field": "x", "operator": "eq", "value": "y"}, "config_on_fail": {"on_fail": "skip"}},
                ]}
            return {"met": False}

        with patch("apps.workflow.temporal.workflows.workflow") as mock_wf:
            mock_wf.execute_activity = mock_activity
            result = await wf.run({"case_id": 1, "run_id": 1, "template_id": 1})
        # Steps executed, condition not met marks skipped
        assert result["status"] == "completed"

    @pytest.mark.asyncio
    async def test_step_exception_abort(self):
        wf = DynamicWorkflow.__new__(DynamicWorkflow)
        wf._pending_gates = {}
        wf._current_gate_step_id = None

        call_count = 0

        async def mock_activity(*args, **kwargs):
            nonlocal call_count
            call_count += 1
            # call 1: fetch_template_schema → return steps
            if call_count == 1:
                return {"steps_schema": [
                    {"id": "s1", "name": "S1", "type": "activity", "mcp_tool": "nonexistent_tool",
                     "config": {"on_fail": "abort"}},
                ]}
            # call 4: execute_mcp_tool → raise
            if call_count == 4:
                raise RuntimeError("activity failed")
            # calls 2,3,5,6: update_run_status / record_step → succeed
            return None

        with patch("apps.workflow.temporal.workflows.workflow") as mock_wf:
            mock_wf.execute_activity = mock_activity
            result = await wf.run({"case_id": 1, "run_id": 1, "template_id": 1})
        assert result["status"] == "failed"
        assert result["failed_step"] == "s1"


# ── DynamicWorkflow._execute_gate ──────────────────────────────────────


class TestExecuteGate:
    @pytest.mark.asyncio
    async def test_gate_approved_flow(self):
        wf = DynamicWorkflow.__new__(DynamicWorkflow)
        wf._pending_gates = {}
        wf._current_gate_step_id = None

        async def set_gate():
            wf._pending_gates["g1"] = GateResult(approved=True, comment="good")

        import asyncio

        with patch("apps.workflow.temporal.workflows.workflow") as mock_wf:
            # Mock wait_condition to call set_gate then return
            async def wait_side_effect(cond):
                await set_gate()
            mock_wf.wait_condition = wait_side_effect
            mock_wf.execute_activity = AsyncMock()

            result = await wf._execute_gate("g1", "Gate1", 1, {}, 1)
        assert result["approved"] is True
        assert result["comment"] == "good"

    @pytest.mark.asyncio
    async def test_gate_rejected_flow(self):
        wf = DynamicWorkflow.__new__(DynamicWorkflow)
        wf._pending_gates = {}
        wf._current_gate_step_id = None

        async def set_gate():
            wf._pending_gates["g2"] = GateResult(approved=False, comment="no")

        import asyncio

        with patch("apps.workflow.temporal.workflows.workflow") as mock_wf:
            async def wait_side_effect(cond):
                await set_gate()
            mock_wf.wait_condition = wait_side_effect
            mock_wf.execute_activity = AsyncMock()

            result = await wf._execute_gate("g2", "Gate2", 1, {}, 1)
        assert result["approved"] is False
        assert result["comment"] == "no"


# ── DynamicWorkflow._execute_wait ──────────────────────────────────────


class TestExecuteWait:
    @pytest.mark.asyncio
    async def test_wait_flow(self):
        wf = DynamicWorkflow.__new__(DynamicWorkflow)
        wf._pending_gates = {}
        wf._current_gate_step_id = None

        async def set_event():
            wf._pending_gates["w1"] = GateResult(approved=True, comment="event received")

        with patch("apps.workflow.temporal.workflows.workflow") as mock_wf:
            async def wait_side_effect(cond):
                await set_event()
            mock_wf.wait_condition = wait_side_effect
            mock_wf.execute_activity = AsyncMock()

            result = await wf._execute_wait("w1", "Wait1", 1, {"_steps_schema": []}, 1)
        assert result["received"] is True
        assert result["comment"] == "event received"
