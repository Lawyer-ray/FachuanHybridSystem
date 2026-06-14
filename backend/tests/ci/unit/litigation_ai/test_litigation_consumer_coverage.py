"""litigation_ai/consumers/litigation_consumer.py 单元测试。"""

from __future__ import annotations

import json
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from apps.litigation_ai.consumers.litigation_consumer import LitigationConsumer


def _make_consumer(**overrides: Any) -> LitigationConsumer:
    consumer = LitigationConsumer.__new__(LitigationConsumer)
    consumer.session_id = overrides.get("session_id", "test-session")
    consumer.user = overrides.get("user")
    consumer.session = overrides.get("session")
    consumer._agent_service = overrides.get("_agent_service")
    consumer.send = AsyncMock()  # type: ignore[assignment]
    consumer.close = AsyncMock()  # type: ignore[assignment]
    consumer.channel_layer = MagicMock()
    consumer.channel_name = "test-channel"
    consumer.scope = overrides.get("scope", {})
    return consumer


class TestGetMessageHandlerUnknown:
    def test_unknown_type_returns_none(self) -> None:
        consumer = _make_consumer()
        assert consumer._get_message_handler("unknown_type") is None

    def test_empty_string_returns_none(self) -> None:
        consumer = _make_consumer()
        assert consumer._get_message_handler("") is None


class TestDisconnect:
    @pytest.mark.asyncio
    async def test_disconnect_with_session(self) -> None:
        consumer = _make_consumer(session_id="s1")
        consumer.channel_layer.group_discard = AsyncMock()
        await consumer.disconnect(1000)
        consumer.channel_layer.group_discard.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_disconnect_without_session(self) -> None:
        consumer = _make_consumer(session_id=None)
        await consumer.disconnect(1000)
        assert not consumer.channel_layer.group_discard.called

    @pytest.mark.asyncio
    async def test_disconnect_exception_logged(self) -> None:
        consumer = _make_consumer(session_id="s1")
        consumer.channel_layer.group_discard = AsyncMock(side_effect=RuntimeError("fail"))
        await consumer.disconnect(1000)


class TestSendError:
    @pytest.mark.asyncio
    async def test_send_error_string(self) -> None:
        consumer = _make_consumer()
        await consumer.send_error("some error")
        consumer.send.assert_awaited_once()
        payload = json.loads(consumer.send.call_args[1]["text_data"])
        assert payload["type"] == "error"
        assert payload["message"] == "some error"

    @pytest.mark.asyncio
    async def test_send_error_with_code(self) -> None:
        consumer = _make_consumer()
        await consumer.send_error("err", code="MY_CODE")
        payload = json.loads(consumer.send.call_args[1]["text_data"])
        assert payload["code"] == "MY_CODE"

    @pytest.mark.asyncio
    async def test_send_error_exception(self) -> None:
        consumer = _make_consumer()
        exc = ValueError("boom")
        with patch(
            "apps.litigation_ai.consumers.litigation_consumer.settings"
        ) as mock_settings:
            mock_settings.DEBUG = False
            with patch("apps.core.exceptions.error_presentation.ExceptionPresenter") as MockPresenter:
                mock_presenter = MagicMock()
                mock_presenter.present.return_value = (
                    MagicMock(code="ERR", message="boom", errors=[], retryable=False),
                    None,
                )
                MockPresenter.return_value = mock_presenter
                await consumer.send_error(exc)
        consumer.send.assert_awaited_once()


class TestSendFlowMessage:
    @pytest.mark.asyncio
    async def test_send_flow_message(self) -> None:
        consumer = _make_consumer()
        await consumer._send_flow_message({"type": "ping"})
        consumer.send.assert_awaited_once()
        payload = json.loads(consumer.send.call_args[1]["text_data"])
        assert payload == {"type": "ping"}


class TestHandleStopGeneration:
    @pytest.mark.asyncio
    async def test_stop_generation(self) -> None:
        consumer = _make_consumer()
        await consumer.handle_stop_generation({})
        consumer.send.assert_awaited_once()
        payload = json.loads(consumer.send.call_args[1]["text_data"])
        assert "停止生成暂未实现" in payload["content"]


class TestHandleUserMessageEmpty:
    @pytest.mark.asyncio
    async def test_empty_content(self) -> None:
        consumer = _make_consumer(session_id="s1", user=MagicMock(id=1), session=MagicMock(case_id="c1"))
        await consumer.handle_user_message({"content": "   "})
        consumer.send.assert_awaited_once()
        payload = json.loads(consumer.send.call_args[1]["text_data"])
        assert payload["type"] == "error"


class TestHandleSelectDocumentTypeNoType:
    @pytest.mark.asyncio
    async def test_missing_document_type(self) -> None:
        consumer = _make_consumer(session_id="s1", user=MagicMock(id=1), session=MagicMock(case_id="c1"))
        await consumer.handle_select_document_type({})
        consumer.send.assert_awaited_once()
        payload = json.loads(consumer.send.call_args[1]["text_data"])
        assert "缺少 document_type" in payload["message"]


class TestAgentServiceProperty:
    def test_agent_service_lazy(self) -> None:
        consumer = _make_consumer()
        assert consumer._agent_service is None
        with patch(
            "apps.litigation_ai.consumers.litigation_consumer.LitigationConsumer.agent_service",
            new_callable=lambda: property(lambda self: MagicMock()),
        ):
            pass


class TestHandleAgentError:
    @pytest.mark.asyncio
    async def test_agent_error(self) -> None:
        consumer = _make_consumer()
        await consumer._handle_agent_error(RuntimeError("boom"))
        consumer.send.assert_awaited_once()


class TestHandleUserMessageAgent:
    @pytest.mark.asyncio
    async def test_agent_mode_calls_service(self) -> None:
        mock_service = AsyncMock()
        mock_service.handle_message.return_value = {"type": "response"}
        consumer = _make_consumer(_agent_service=mock_service)
        consumer.session = MagicMock(case_id="c1")
        consumer.session_id = "s1"
        await consumer._handle_user_message_agent("hello", {})
        mock_service.handle_message.assert_awaited_once()
        consumer.send.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_agent_mode_error(self) -> None:
        mock_service = AsyncMock()
        mock_service.handle_message.side_effect = RuntimeError("fail")
        consumer = _make_consumer(_agent_service=mock_service)
        consumer.session = MagicMock(case_id="c1")
        consumer.session_id = "s1"
        await consumer._handle_user_message_agent("hello", {})
        consumer.send.assert_awaited_once()
        payload = json.loads(consumer.send.call_args[1]["text_data"])
        assert payload["type"] == "error"


class TestHandleSelectEvidenceAgent:
    @pytest.mark.asyncio
    async def test_evidence_agent_calls_service(self) -> None:
        mock_service = AsyncMock()
        mock_service.handle_evidence_selection.return_value = {"type": "done"}
        consumer = _make_consumer(_agent_service=mock_service)
        consumer.session = MagicMock(case_id="c1")
        consumer.session_id = "s1"
        await consumer._handle_select_evidence_agent([1], [2], [3])
        mock_service.handle_evidence_selection.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_evidence_agent_error(self) -> None:
        mock_service = AsyncMock()
        mock_service.handle_evidence_selection.side_effect = RuntimeError("fail")
        consumer = _make_consumer(_agent_service=mock_service)
        consumer.session = MagicMock(case_id="c1")
        consumer.session_id = "s1"
        await consumer._handle_select_evidence_agent([], [], [])
        consumer.send.assert_awaited_once()
