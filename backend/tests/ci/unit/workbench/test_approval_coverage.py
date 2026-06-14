"""Tests for workbench/agents/approval.py (missing: 32 lines).

Covers: ApprovalManager resolve/wait_for_approval, process_tool_call_with_approval.
"""
from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, MagicMock

import pytest

from apps.workbench.agents.approval import (
    HIGH_RISK_TOOLS,
    ApprovalManager,
    process_tool_call_with_approval,
)


class TestApprovalManager:
    def test_resolve_nonexistent(self) -> None:
        mgr = ApprovalManager()
        assert mgr.resolve("nonexistent", True) is False

    def test_resolve_success(self) -> None:
        mgr = ApprovalManager()
        event = asyncio.Event()
        mgr._events["test_id"] = event
        mgr._results["test_id"] = False
        result = mgr.resolve("test_id", True)
        assert result is True
        assert mgr._results["test_id"] is True
        assert event.is_set()

    def test_resolve_wrong_user(self) -> None:
        mgr = ApprovalManager()
        event = asyncio.Event()
        mgr._events["test_id"] = event
        mgr._results["test_id"] = False
        mgr._user_ids["test_id"] = 1
        result = mgr.resolve("test_id", True, user_id=2)
        assert result is False

    def test_resolve_correct_user(self) -> None:
        mgr = ApprovalManager()
        event = asyncio.Event()
        mgr._events["test_id"] = event
        mgr._results["test_id"] = False
        mgr._user_ids["test_id"] = 1
        result = mgr.resolve("test_id", True, user_id=1)
        assert result is True

    @pytest.mark.asyncio
    async def test_wait_for_approval_timeout(self) -> None:
        mgr = ApprovalManager()
        result = await mgr.wait_for_approval("timeout_test", timeout=0.1)
        assert result is False

    @pytest.mark.asyncio
    async def test_wait_for_approval_approved(self) -> None:
        mgr = ApprovalManager()

        async def approve() -> None:
            await asyncio.sleep(0.05)
            mgr.resolve("approved_test", True)

        task = asyncio.create_task(approve())
        result = await mgr.wait_for_approval("approved_test", timeout=5)
        assert result is True
        await task

    @pytest.mark.asyncio
    async def test_wait_for_approval_rejected(self) -> None:
        mgr = ApprovalManager()

        async def reject() -> None:
            await asyncio.sleep(0.05)
            mgr.resolve("rejected_test", False)

        task = asyncio.create_task(reject())
        result = await mgr.wait_for_approval("rejected_test", timeout=5)
        assert result is False
        await task


class TestHighRiskTools:
    def test_known_tools(self) -> None:
        assert "delete_case" in HIGH_RISK_TOOLS
        assert "file_lawsuit" in HIGH_RISK_TOOLS

    def test_is_frozen(self) -> None:
        assert isinstance(HIGH_RISK_TOOLS, frozenset)


class TestProcessToolCallWithApproval:
    @pytest.mark.asyncio
    async def test_low_risk_tool_passes_through(self) -> None:
        event_queue = asyncio.Queue()
        call_tool = AsyncMock(return_value={"result": "ok"})
        result = await process_tool_call_with_approval(
            ctx=None, call_tool=call_tool, name="search_case",
            tool_args={"q": "test"}, event_queue=event_queue,
        )
        call_tool.assert_called_once_with("search_case", {"q": "test"})
        assert result == {"result": "ok"}

    @pytest.mark.asyncio
    async def test_high_risk_tool_approved(self) -> None:
        event_queue = asyncio.Queue()
        call_tool = AsyncMock(return_value={"result": "deleted"})

        from apps.workbench.agents.approval import approval_manager

        async def approve() -> None:
            await asyncio.sleep(0.05)
            # Get the approval_id from the queue
            event = await event_queue.get()
            approval_id = event["approval_id"]
            approval_manager.resolve(approval_id, True)

        task = asyncio.create_task(approve())
        result = await process_tool_call_with_approval(
            ctx=None, call_tool=call_tool, name="delete_case",
            tool_args={"id": 1}, event_queue=event_queue,
        )
        await task
        call_tool.assert_called_once_with("delete_case", {"id": 1})

    @pytest.mark.asyncio
    async def test_high_risk_tool_rejected(self) -> None:
        event_queue = asyncio.Queue()
        call_tool = AsyncMock(return_value={"result": "deleted"})

        from apps.workbench.agents.approval import approval_manager

        async def reject() -> None:
            await asyncio.sleep(0.05)
            event = await event_queue.get()
            approval_id = event["approval_id"]
            approval_manager.resolve(approval_id, False)

        task = asyncio.create_task(reject())
        result = await process_tool_call_with_approval(
            ctx=None, call_tool=call_tool, name="delete_case",
            tool_args={"id": 1}, event_queue=event_queue,
        )
        await task
        call_tool.assert_not_called()
        assert result.get("user_denied") is True
