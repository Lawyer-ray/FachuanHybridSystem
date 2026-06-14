"""litigation_consumer.py — round3 tests for uncovered branches.

Covers:
- receive: None text_data, invalid JSON, non-dict, no message_type, empty content
- handle_user_message: non-agent mode, empty content
- handle_select_document_type: missing document_type
- agent_service property lazy loading
- send_error: string error
- _handle_select_evidence_agent
- _handle_agent_error
"""
from __future__ import annotations

import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest


def _make_consumer(**kwargs):
    from apps.litigation_ai.consumers.litigation_consumer import LitigationConsumer
    c = LitigationConsumer.__new__(LitigationConsumer)
    c.session_id = kwargs.get("session_id", "test_session")
    c.user = MagicMock()
    c.user.id = kwargs.get("user_id", 1)
    c.session = MagicMock()
    c.session.case_id = kwargs.get("case_id", 10)
    c._agent_service = None
    return c


# ── agent_service property ────────────────────────────────────────────────────


class TestAgentServiceProperty:
    def test_lazy_loads(self):
        c = _make_consumer()
        with patch("apps.litigation_ai.services.generation.litigation_agent_service.LitigationAgentService") as MockSvc:
            MockSvc.return_value = MagicMock()
            svc = c.agent_service
            assert svc is not None
            # Second access returns cached
            svc2 = c.agent_service
            assert svc is svc2


# ── send_error ────────────────────────────────────────────────────────────────


class TestSendErrorString:
    @pytest.mark.asyncio
    async def test_string_error(self):
        c = _make_consumer()
        c.send = AsyncMock()
        await c.send_error("something wrong")
        c.send.assert_called_once()
        payload = json.loads(c.send.call_args[1]["text_data"])
        assert payload["type"] == "error"
        assert payload["message"] == "something wrong"


# ── receive edge cases ────────────────────────────────────────────────────────


class TestReceiveEdge:
    @pytest.mark.asyncio
    async def test_none_text_data(self):
        c = _make_consumer()
        c.send = AsyncMock()
        await c.receive(text_data=None)
        c.send.assert_called()
        payload = json.loads(c.send.call_args[1]["text_data"])
        assert "空" in payload["message"]

    @pytest.mark.asyncio
    async def test_invalid_json(self):
        c = _make_consumer()
        c.send = AsyncMock()
        await c.receive(text_data="not json")
        c.send.assert_called()
        payload = json.loads(c.send.call_args[1]["text_data"])
        assert "格式错误" in payload["message"]

    @pytest.mark.asyncio
    async def test_non_dict(self):
        c = _make_consumer()
        c.send = AsyncMock()
        await c.receive(text_data=json.dumps("not a dict"))
        c.send.assert_called()
        payload = json.loads(c.send.call_args[1]["text_data"])
        assert "JSON 对象" in payload["message"]

    @pytest.mark.asyncio
    async def test_no_message_type(self):
        c = _make_consumer()
        c.send = AsyncMock()
        await c.receive(text_data=json.dumps({"content": "hi"}))
        c.send.assert_called()
        payload = json.loads(c.send.call_args[1]["text_data"])
        assert "类型" in payload["message"]

    @pytest.mark.asyncio
    async def test_unsupported_type(self):
        c = _make_consumer()
        c.send = AsyncMock()
        await c.receive(text_data=json.dumps({"type": "unsupported"}))
        c.send.assert_called()
        payload = json.loads(c.send.call_args[1]["text_data"])
        assert "不支持" in payload["message"]


# ── handle_user_message ──────────────────────────────────────────────────────


class TestHandleUserMessage:
    @pytest.mark.asyncio
    async def test_empty_content(self):
        c = _make_consumer()
        c.send = AsyncMock()
        await c.handle_user_message({"content": ""})
        c.send.assert_called()
        payload = json.loads(c.send.call_args[1]["text_data"])
        assert "空" in payload["message"]

    @pytest.mark.asyncio
    async def test_non_agent_mode_dispatches(self):
        c = _make_consumer()
        c.send = AsyncMock()
        c._add_message = AsyncMock()
        c._get_current_step = AsyncMock(return_value="init")
        c._dispatch_by_step = AsyncMock()
        with patch("apps.litigation_ai.consumers.litigation_consumer._use_agent_mode", return_value=False):
            with patch("apps.litigation_ai.services.ConversationFlowService") as MockFS:
                mock_svc = MagicMock()
                MockFS.return_value = mock_svc
                with patch("apps.litigation_ai.services.FlowContext") as MockCtx:
                    await c.handle_user_message({"content": "hello", "metadata": {}})
                    c._add_message.assert_called_once()
                    c._dispatch_by_step.assert_called_once()


# ── handle_select_document_type — missing type ───────────────────────────────


class TestHandleSelectDocumentTypeMissing:
    @pytest.mark.asyncio
    async def test_missing_document_type(self):
        c = _make_consumer()
        c.send = AsyncMock()
        await c.handle_select_document_type({})
        c.send.assert_called()
        payload = json.loads(c.send.call_args[1]["text_data"])
        assert "document_type" in payload["message"]


# ── _handle_select_evidence_agent ────────────────────────────────────────────


class TestHandleSelectEvidenceAgent:
    @pytest.mark.asyncio
    async def test_success(self):
        c = _make_consumer()
        c.send = AsyncMock()
        mock_agent = MagicMock()
        mock_agent.handle_evidence_selection = AsyncMock(return_value={"type": "result"})
        c._agent_service = mock_agent
        await c._handle_select_evidence_agent([1, 2], [1], [2])
        mock_agent.handle_evidence_selection.assert_called_once()

    @pytest.mark.asyncio
    async def test_error(self):
        c = _make_consumer()
        c.send = AsyncMock()
        mock_agent = MagicMock()
        mock_agent.handle_evidence_selection = AsyncMock(side_effect=RuntimeError("fail"))
        c._agent_service = mock_agent
        with patch("apps.core.exceptions.error_presentation.ExceptionPresenter") as MockEP:
            mock_presenter = MagicMock()
            mock_envelope = MagicMock()
            mock_envelope.code = "ERR"
            mock_envelope.message = "fail"
            mock_envelope.errors = {}
            mock_envelope.retryable = False
            mock_presenter.present.return_value = (mock_envelope, None)
            MockEP.return_value = mock_presenter
            with patch("apps.litigation_ai.consumers.litigation_consumer.settings") as ms:
                ms.DEBUG = False
                await c._handle_select_evidence_agent([1], [1], [])


# ── _handle_agent_error ──────────────────────────────────────────────────────


class TestHandleAgentError:
    @pytest.mark.asyncio
    async def test_delegates_to_send_error(self):
        c = _make_consumer()
        c.send = AsyncMock()
        exc = RuntimeError("test")
        await c._handle_agent_error(exc)
        c.send.assert_called()


# ── handle_stop_generation ────────────────────────────────────────────────────


class TestHandleStopGeneration:
    @pytest.mark.asyncio
    async def test_sends_not_implemented(self):
        c = _make_consumer()
        c.send = AsyncMock()
        await c.handle_stop_generation({})
        c.send.assert_called()
        payload = json.loads(c.send.call_args[1]["text_data"])
        assert "暂未实现" in payload["content"]
