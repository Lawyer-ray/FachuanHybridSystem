"""Coverage tests for litigation_ai/consumers/litigation_consumer.py — uncovered branches.

Covers:
  - _dispatch_by_step: INIT, DOCUMENT_TYPE, LITIGATION_GOAL, EVIDENCE_SELECTION,
    DOC_PLAN, GENERATING/REFINING, unknown step
  - handle_select_document_type: valid document_type
  - handle_select_evidence: with all evidence IDs
  - handle_confirm_generate
  - _handle_document_type_step: parsed type, parse failure, empty parsed type
  - _handle_user_message_agent: success, error
  - send_history_messages
  - _add_message
  - _get_current_step
  - _get_session: found, not found
"""
from __future__ import annotations

import json
from types import SimpleNamespace
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest


def _make_consumer(**kwargs) -> Any:
    from apps.litigation_ai.consumers.litigation_consumer import LitigationConsumer

    c = LitigationConsumer.__new__(LitigationConsumer)
    c.session_id = kwargs.get("session_id", "test_session")
    c.user = MagicMock()
    c.user.id = kwargs.get("user_id", 1)
    c.session = MagicMock()
    c.session.case_id = kwargs.get("case_id", 10)
    c._agent_service = None
    c.send = AsyncMock()
    return c


# ===========================================================================
# _dispatch_by_step
# ===========================================================================


class TestDispatchByStep:
    @pytest.mark.asyncio
    async def test_init_step(self) -> None:
        c = _make_consumer()
        mock_flow = MagicMock()
        mock_flow.handle_init = AsyncMock()
        from apps.litigation_ai.services import ConversationStep

        await c._dispatch_by_step(mock_flow, MagicMock(), ConversationStep.INIT, "hello")
        mock_flow.handle_init.assert_called_once()

    @pytest.mark.asyncio
    async def test_document_type_step(self) -> None:
        c = _make_consumer()
        mock_flow = MagicMock()
        c._handle_document_type_step = AsyncMock()
        from apps.litigation_ai.services import ConversationStep

        await c._dispatch_by_step(mock_flow, MagicMock(), ConversationStep.DOCUMENT_TYPE, "complaint")
        c._handle_document_type_step.assert_called_once()

    @pytest.mark.asyncio
    async def test_litigation_goal_step(self) -> None:
        c = _make_consumer()
        mock_flow = MagicMock()
        mock_flow.handle_litigation_goal_collection = AsyncMock()
        from apps.litigation_ai.services import ConversationStep

        await c._dispatch_by_step(mock_flow, MagicMock(), ConversationStep.LITIGATION_GOAL, "goal text")
        mock_flow.handle_litigation_goal_collection.assert_called_once()

    @pytest.mark.asyncio
    async def test_evidence_selection_step(self) -> None:
        c = _make_consumer()
        mock_flow = MagicMock()
        mock_flow.handle_evidence_selection = AsyncMock()
        from apps.litigation_ai.services import ConversationStep

        await c._dispatch_by_step(mock_flow, MagicMock(), ConversationStep.EVIDENCE_SELECTION, "")
        mock_flow.handle_evidence_selection.assert_called_once()

    @pytest.mark.asyncio
    async def test_doc_plan_step(self) -> None:
        c = _make_consumer()
        mock_flow = MagicMock()
        mock_flow.handle_doc_plan_selection = AsyncMock()
        from apps.litigation_ai.services import ConversationStep

        await c._dispatch_by_step(mock_flow, MagicMock(), ConversationStep.DOC_PLAN, "plan text")
        mock_flow.handle_doc_plan_selection.assert_called_once()

    @pytest.mark.asyncio
    async def test_generating_step(self) -> None:
        c = _make_consumer()
        mock_flow = MagicMock()
        mock_flow.handle_refining = AsyncMock()
        from apps.litigation_ai.services import ConversationStep

        await c._dispatch_by_step(mock_flow, MagicMock(), ConversationStep.GENERATING, "refine")
        mock_flow.handle_refining.assert_called_once()

    @pytest.mark.asyncio
    async def test_refining_step(self) -> None:
        c = _make_consumer()
        mock_flow = MagicMock()
        mock_flow.handle_refining = AsyncMock()
        from apps.litigation_ai.services import ConversationStep

        await c._dispatch_by_step(mock_flow, MagicMock(), ConversationStep.REFINING, "more")
        mock_flow.handle_refining.assert_called_once()

    @pytest.mark.asyncio
    async def test_unknown_step_does_nothing(self) -> None:
        c = _make_consumer()
        mock_flow = MagicMock()
        # COMPLETED is not in the handlers dict and not in (GENERATING, REFINING)
        from apps.litigation_ai.services import ConversationStep

        await c._dispatch_by_step(mock_flow, MagicMock(), ConversationStep.COMPLETED, "done")
        mock_flow.handle_refining.assert_not_called()


# ===========================================================================
# handle_select_document_type — valid type
# ===========================================================================


class TestHandleSelectDocumentTypeValid:
    @pytest.mark.asyncio
    async def test_valid_type(self) -> None:
        c = _make_consumer()
        with patch("apps.litigation_ai.services.ConversationFlowService") as MockFS:
            mock_svc = MagicMock()
            mock_svc.handle_document_type_selection = AsyncMock()
            MockFS.return_value = mock_svc
            with patch("apps.litigation_ai.services.FlowContext"):
                await c.handle_select_document_type({"document_type": "complaint"})
                mock_svc.handle_document_type_selection.assert_called_once()


# ===========================================================================
# handle_select_evidence
# ===========================================================================


class TestHandleSelectEvidence:
    @pytest.mark.asyncio
    async def test_with_ids(self) -> None:
        c = _make_consumer()
        with patch("apps.litigation_ai.services.ConversationFlowService") as MockFS:
            mock_svc = MagicMock()
            mock_svc.handle_evidence_selection = AsyncMock()
            MockFS.return_value = mock_svc
            with patch("apps.litigation_ai.services.FlowContext"):
                await c.handle_select_evidence({
                    "evidence_list_ids": [1, 2],
                    "evidence_item_ids": [3],
                    "our_evidence_item_ids": [3],
                    "opponent_evidence_item_ids": [],
                })
                mock_svc.handle_evidence_selection.assert_called_once()

    @pytest.mark.asyncio
    async def test_with_none_lists(self) -> None:
        c = _make_consumer()
        with patch("apps.litigation_ai.services.ConversationFlowService") as MockFS:
            mock_svc = MagicMock()
            mock_svc.handle_evidence_selection = AsyncMock()
            MockFS.return_value = mock_svc
            with patch("apps.litigation_ai.services.FlowContext"):
                await c.handle_select_evidence({})
                mock_svc.handle_evidence_selection.assert_called_once()


# ===========================================================================
# handle_confirm_generate
# ===========================================================================


class TestHandleConfirmGenerate:
    @pytest.mark.asyncio
    async def test_calls_flow_service(self) -> None:
        c = _make_consumer()
        with patch("apps.litigation_ai.services.ConversationFlowService") as MockFS:
            mock_svc = MagicMock()
            mock_svc.handle_confirm_generate = AsyncMock()
            MockFS.return_value = mock_svc
            with patch("apps.litigation_ai.services.FlowContext"):
                await c.handle_confirm_generate({})
                mock_svc.handle_confirm_generate.assert_called_once()


# ===========================================================================
# _handle_document_type_step
# ===========================================================================


class TestHandleDocumentTypeStep:
    @pytest.mark.asyncio
    async def test_parsed_type_success(self) -> None:
        c = _make_consumer()
        mock_flow = MagicMock()
        mock_flow.handle_document_type_selection = AsyncMock()

        mock_session_obj = MagicMock()
        mock_session_obj.metadata = {"recommended_types": ["complaint", "defense"]}

        with patch("apps.litigation_ai.models.LitigationSession") as MockModel:
            MockModel.objects.get.return_value = mock_session_obj
            with patch("apps.litigation_ai.chains.DocumentTypeParseChain") as MockChain:
                mock_chain_instance = MagicMock()
                mock_chain_instance.arun = AsyncMock(return_value=SimpleNamespace(document_type="complaint"))
                MockChain.return_value = mock_chain_instance
                ctx = MagicMock()
                ctx.session_id = "s1"
                await c._handle_document_type_step(mock_flow, ctx, "complaint")
                mock_flow.handle_document_type_selection.assert_called_once()

    @pytest.mark.asyncio
    async def test_parse_exception_sends_fallback(self) -> None:
        c = _make_consumer()

        mock_session_obj = MagicMock()
        mock_session_obj.metadata = None

        with patch("apps.litigation_ai.models.LitigationSession") as MockModel:
            MockModel.objects.get.return_value = mock_session_obj
            with patch("apps.litigation_ai.chains.DocumentTypeParseChain") as MockChain:
                mock_chain_instance = MagicMock()
                mock_chain_instance.arun = AsyncMock(side_effect=ValueError("parse error"))
                MockChain.return_value = mock_chain_instance
                ctx = MagicMock()
                ctx.session_id = "s1"
                mock_flow = MagicMock()
                await c._handle_document_type_step(mock_flow, ctx, "garbage")
                c.send.assert_called()
                payload = json.loads(c.send.call_args[1]["text_data"])
                assert "没有理解" in payload["content"]

    @pytest.mark.asyncio
    async def test_empty_parsed_type_sends_fallback(self) -> None:
        c = _make_consumer()

        mock_session_obj = MagicMock()
        mock_session_obj.metadata = {}

        with patch("apps.litigation_ai.models.LitigationSession") as MockModel:
            MockModel.objects.get.return_value = mock_session_obj
            with patch("apps.litigation_ai.chains.DocumentTypeParseChain") as MockChain:
                mock_chain_instance = MagicMock()
                mock_chain_instance.arun = AsyncMock(return_value=SimpleNamespace(document_type=""))
                MockChain.return_value = mock_chain_instance
                ctx = MagicMock()
                ctx.session_id = "s1"
                mock_flow = MagicMock()
                await c._handle_document_type_step(mock_flow, ctx, "garbage")
                c.send.assert_called()
                payload = json.loads(c.send.call_args[1]["text_data"])
                assert "没有理解" in payload["content"]


# ===========================================================================
# _handle_user_message_agent
# ===========================================================================


class TestHandleUserMessageAgent:
    @pytest.mark.asyncio
    async def test_success(self) -> None:
        c = _make_consumer()
        mock_agent = MagicMock()
        mock_agent.handle_message = AsyncMock(return_value={"type": "response", "content": "result"})
        c._agent_service = mock_agent
        await c._handle_user_message_agent("hello", {})
        mock_agent.handle_message.assert_called_once()
        c.send.assert_called()

    @pytest.mark.asyncio
    async def test_error_calls_agent_error(self) -> None:
        c = _make_consumer()
        mock_agent = MagicMock()
        mock_agent.handle_message = AsyncMock(side_effect=RuntimeError("fail"))
        c._agent_service = mock_agent
        c._handle_agent_error = AsyncMock()
        await c._handle_user_message_agent("hello", {})
        c._handle_agent_error.assert_called_once()


# ===========================================================================
# send_history_messages
# ===========================================================================


class TestSendHistoryMessages:
    @pytest.mark.asyncio
    async def test_sends_history(self) -> None:
        c = _make_consumer()
        mock_msg = MagicMock()
        mock_msg.id = 1
        mock_msg.role = "user"
        mock_msg.content = "hello"
        mock_msg.metadata = {}
        mock_msg.created_at = MagicMock()
        mock_msg.created_at.isoformat.return_value = "2024-01-01T00:00:00"

        with patch("apps.litigation_ai.services.LitigationConversationService") as MockSvc:
            mock_svc = MagicMock()
            mock_svc.get_messages.return_value = [mock_msg]
            MockSvc.return_value = mock_svc
            # database_sync_to_async is called as a function inside send_history_messages
            with patch("apps.litigation_ai.consumers.litigation_consumer.database_sync_to_async") as mock_dba:
                # Make it return an awaitable that returns [mock_msg]
                mock_dba.return_value = AsyncMock(return_value=[mock_msg])
                await c.send_history_messages()
                c.send.assert_called()
                payload = json.loads(c.send.call_args[1]["text_data"])
                assert payload["type"] == "history"
                assert len(payload["messages"]) == 1


# ===========================================================================
# _add_message
# ===========================================================================


class TestAddMessage:
    @pytest.mark.asyncio
    async def test_adds_message(self) -> None:
        c = _make_consumer(session_id="00000000-0000-0000-0000-000000000001")
        with patch("apps.litigation_ai.services.LitigationConversationService") as MockSvc:
            mock_svc = MagicMock()
            mock_svc.add_message.return_value = MagicMock()
            MockSvc.return_value = mock_svc
            result = await c._add_message("user", "hello", {"key": "val"})
            assert result is not None


# ===========================================================================
# _get_current_step
# ===========================================================================


class TestGetCurrentStep:
    @pytest.mark.asyncio
    async def test_returns_step(self) -> None:
        c = _make_consumer()
        mock_flow = MagicMock()
        mock_flow.get_current_step.return_value = "init"
        result = await c._get_current_step(mock_flow)
        assert result == "init"


# ===========================================================================
# _get_session
# ===========================================================================


class TestGetSession:
    @pytest.mark.asyncio
    async def test_session_found(self) -> None:
        c = _make_consumer()
        mock_session = MagicMock()
        with patch("apps.litigation_ai.models.LitigationSession") as MockModel:
            MockModel.objects.filter.return_value.first.return_value = mock_session
            result = await c._get_session("00000000-0000-0000-0000-000000000001")
            assert result == mock_session

    @pytest.mark.asyncio
    async def test_session_not_found(self) -> None:
        c = _make_consumer()
        with patch("apps.litigation_ai.models.LitigationSession") as MockModel:
            MockModel.objects.filter.return_value.first.return_value = None
            result = await c._get_session("00000000-0000-0000-0000-000000000002")
            assert result is None


# ===========================================================================
# connect — edge cases
# ===========================================================================


class TestConnectEdgeCases:
    @pytest.mark.asyncio
    async def test_anonymous_user_closes(self) -> None:
        from django.contrib.auth.models import AnonymousUser

        c = _make_consumer()
        c.scope = {"user": AnonymousUser()}
        c.close = AsyncMock()
        await c.connect()
        c.close.assert_called_with(code=4001)

    @pytest.mark.asyncio
    async def test_no_session_id_closes(self) -> None:
        c = _make_consumer()
        c.scope = {"user": MagicMock(id=1), "url_route": {"kwargs": {}}}
        c.close = AsyncMock()
        await c.connect()
        c.close.assert_called_with(code=4002)


# ===========================================================================
# receive — exception path
# ===========================================================================


class TestReceiveException:
    @pytest.mark.asyncio
    async def test_handler_exception_sends_error(self) -> None:
        c = _make_consumer()
        # send_error is used in the except block, mock it
        c.send_error = AsyncMock()
        # Make handler raise
        c._get_message_handler = MagicMock(return_value=MagicMock(side_effect=RuntimeError("boom")))
        await c.receive(text_data=json.dumps({"type": "user_message", "content": "hi"}))
        c.send_error.assert_called()

    @pytest.mark.asyncio
    async def test_handler_returns_none(self) -> None:
        """If handler returns None (unsupported type), send_error is called."""
        c = _make_consumer()
        c.send_error = AsyncMock()
        c._get_message_handler = MagicMock(return_value=None)
        await c.receive(text_data=json.dumps({"type": "bogus"}))
        c.send_error.assert_called()


# ===========================================================================
# send_error — Exception branch
# ===========================================================================


class TestSendErrorException:
    @pytest.mark.asyncio
    async def test_exception_with_debug_false(self) -> None:
        c = _make_consumer()
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
                await c.send_error(RuntimeError("boom"))
                c.send.assert_called()
                payload = json.loads(c.send.call_args[1]["text_data"])
                assert payload["type"] == "error"
                assert payload["code"] == "ERR"


# ===========================================================================
# handle_user_message — agent mode
# ===========================================================================


class TestHandleUserMessageAgentMode:
    @pytest.mark.asyncio
    async def test_agent_mode_dispatches(self) -> None:
        c = _make_consumer()
        c._handle_user_message_agent = AsyncMock()
        with patch("apps.litigation_ai.consumers.litigation_consumer._use_agent_mode", return_value=True):
            await c.handle_user_message({"content": "agent query"})
            c._handle_user_message_agent.assert_called_once_with("agent query", {})

    @pytest.mark.asyncio
    async def test_whitespace_content_returns_error(self) -> None:
        c = _make_consumer()
        await c.handle_user_message({"content": "   "})
        c.send.assert_called()
        payload = json.loads(c.send.call_args[1]["text_data"])
        assert "空" in payload["message"]
