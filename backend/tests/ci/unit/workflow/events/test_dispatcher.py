"""Tests for workflow/events/dispatcher.py (0% coverage).

Covers: on_court_reply — no runs, signal + status update, empty documents.
"""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest


class _AsyncListIter:
    """Helper to mock Django async iteration."""

    def __init__(self, items: list) -> None:
        self._items = items

    def __aiter__(self):
        return self

    async def __anext__(self):
        if self._items:
            return self._items.pop(0)
        raise StopAsyncIteration


@pytest.mark.asyncio
class TestOnCourtReplyNoRuns:
    @patch("apps.workflow.events.dispatcher._client", None)
    @patch("temporalio.client.Client")
    @patch("apps.workflow.events.dispatcher.WorkflowRun")
    async def test_no_matching_runs(self, mock_model, mock_client_cls):
        from apps.workflow.events.dispatcher import on_court_reply

        mock_filter_qs = _AsyncListIter([])
        mock_model.objects.filter.return_value = mock_filter_qs

        await on_court_reply(case_id=999, status="approved")

        mock_client_cls.connect.assert_not_called()

    @patch("apps.workflow.events.dispatcher._client", None)
    @patch("temporalio.client.Client")
    @patch("apps.workflow.events.dispatcher.WorkflowRun")
    async def test_filters_correctly(self, mock_model, mock_client_cls):
        from apps.workflow.events.dispatcher import on_court_reply

        mock_filter_qs = _AsyncListIter([])
        mock_model.objects.filter.return_value = mock_filter_qs

        await on_court_reply(case_id=42, status="rejected")

        call_kwargs = mock_model.objects.filter.call_args[1]
        assert call_kwargs["case_id"] == 42
        assert call_kwargs["current_step_id"] == "wait_court"


def _run_fixture(workflow_id: str) -> SimpleNamespace:
    """构造 on_court_reply 用的 run（真实模型有 pk，条件更新按 pk 定位）。"""
    return SimpleNamespace(
        pk=11,
        temporal_workflow_id=workflow_id,
        status="waiting_event",
        current_step_id="wait_court",
    )


def _update_qs() -> MagicMock:
    """条件更新的 queryset mock（filter(...).aupdate(...)）。"""
    qs = MagicMock()
    qs.aupdate = AsyncMock(return_value=1)
    return qs


@pytest.mark.asyncio
class TestOnCourtReplySignal:
    @patch("apps.workflow.events.dispatcher._client", None)
    @patch("temporalio.client.Client")
    @patch("apps.workflow.events.dispatcher.WorkflowRun")
    async def test_signals_and_updates_status(self, mock_model, mock_client_cls):
        from apps.workflow.events.dispatcher import on_court_reply

        run = _run_fixture("wf-abc")
        update_qs = _update_qs()
        # filter 第一次返回等待中的 run 列表，第二次（条件更新）返回 update queryset
        mock_model.objects.filter.side_effect = [_AsyncListIter([run]), update_qs]
        mock_model.Status.WAITING_EVENT = "waiting_event"
        mock_model.Status.RUNNING = "running"

        mock_handle = MagicMock()
        mock_handle.signal = AsyncMock()
        mock_client = MagicMock()
        mock_client.get_workflow_handle.return_value = mock_handle
        mock_client_cls.connect = AsyncMock(return_value=mock_client)

        await on_court_reply(case_id=1, status="rejected", documents=["doc1.pdf"])

        mock_handle.signal.assert_awaited_once_with(
            "gate_approved",
            {"step_id": "wait_court", "approved": True, "comment": "rejected", "documents": ["doc1.pdf"]},
        )
        # 条件更新：仅当仍为 WAITING_EVENT 时置 RUNNING（不覆盖 worker 终态）
        mock_model.objects.filter.assert_any_call(pk=run.pk, status="waiting_event")
        update_qs.aupdate.assert_awaited_once_with(status="running")


@pytest.mark.asyncio
class TestOnCourtReplyEmptyDocuments:
    @patch("apps.workflow.events.dispatcher._client", None)
    @patch("temporalio.client.Client")
    @patch("apps.workflow.events.dispatcher.WorkflowRun")
    async def test_empty_documents_default(self, mock_model, mock_client_cls):
        from apps.workflow.events.dispatcher import on_court_reply

        run = _run_fixture("wf-def")
        mock_model.objects.filter.side_effect = [_AsyncListIter([run]), _update_qs()]
        mock_model.Status.WAITING_EVENT = "waiting_event"
        mock_model.Status.RUNNING = "running"

        mock_handle = MagicMock()
        mock_handle.signal = AsyncMock()
        mock_client = MagicMock()
        mock_client.get_workflow_handle.return_value = mock_handle
        mock_client_cls.connect = AsyncMock(return_value=mock_client)

        await on_court_reply(case_id=2, status="approved", documents=None)

        mock_handle.signal.assert_awaited_once_with(
            "gate_approved", {"step_id": "wait_court", "approved": True, "comment": "approved", "documents": []}
        )

    @patch("apps.workflow.events.dispatcher._client", None)
    @patch("temporalio.client.Client")
    @patch("apps.workflow.events.dispatcher.WorkflowRun")
    async def test_empty_list_documents(self, mock_model, mock_client_cls):
        from apps.workflow.events.dispatcher import on_court_reply

        run = _run_fixture("wf-ghi")
        mock_model.objects.filter.side_effect = [_AsyncListIter([run]), _update_qs()]
        mock_model.Status.WAITING_EVENT = "waiting_event"
        mock_model.Status.RUNNING = "running"

        mock_handle = MagicMock()
        mock_handle.signal = AsyncMock()
        mock_client = MagicMock()
        mock_client.get_workflow_handle.return_value = mock_handle
        mock_client_cls.connect = AsyncMock(return_value=mock_client)

        await on_court_reply(case_id=3, status="approved", documents=[])

        mock_handle.signal.assert_awaited_once_with(
            "gate_approved", {"step_id": "wait_court", "approved": True, "comment": "approved", "documents": []}
        )
