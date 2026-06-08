"""Tests for litigation_ai.consumers.litigation_consumer."""

from __future__ import annotations

import json
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from apps.litigation_ai.consumers.litigation_consumer import LitigationConsumer, _use_agent_mode


class TestUseAgentMode:
    @patch("apps.litigation_ai.consumers.litigation_consumer.settings")
    def test_agent_mode_enabled(self, mock_settings):
        mock_settings.LITIGATION_USE_AGENT_MODE = True
        assert _use_agent_mode() is True

    @patch("apps.litigation_ai.consumers.litigation_consumer.settings")
    def test_agent_mode_disabled(self, mock_settings):
        mock_settings.LITIGATION_USE_AGENT_MODE = False
        assert _use_agent_mode() is False

    @patch("apps.litigation_ai.consumers.litigation_consumer.settings")
    def test_agent_mode_missing_attr(self, mock_settings):
        del mock_settings.LITIGATION_USE_AGENT_MODE
        assert _use_agent_mode() is False


class TestLitigationConsumerInit:
    def test_default_attributes(self):
        consumer = LitigationConsumer.__new__(LitigationConsumer)
        consumer.__init__()
        assert consumer.session_id is None
        assert consumer.user is None


class TestLitigationConsumerGetMessageHandler:
    def test_known_handlers(self):
        consumer = LitigationConsumer.__new__(LitigationConsumer)
        consumer.__init__()
        assert consumer._get_message_handler("user_message") is not None
        assert consumer._get_message_handler("select_document_type") is not None
        assert consumer._get_message_handler("select_evidence") is not None
        assert consumer._get_message_handler("confirm_generate") is not None
        assert consumer._get_message_handler("stop_generation") is not None

    def test_unknown_handler(self):
        consumer = LitigationConsumer.__new__(LitigationConsumer)
        consumer.__init__()
        assert consumer._get_message_handler("unknown_type") is None


class TestLitigationConsumerSendError:
    @pytest.mark.asyncio
    async def test_send_error_string(self):
        consumer = LitigationConsumer.__new__(LitigationConsumer)
        consumer.__init__()
        consumer.send = AsyncMock()
        await consumer.send_error("Something went wrong")
        consumer.send.assert_called_once()
        call_args = consumer.send.call_args
        payload = json.loads(call_args[1]["text_data"])
        assert payload["type"] == "error"
        assert payload["message"] == "Something went wrong"

    @pytest.mark.asyncio
    async def test_send_error_exception(self):
        consumer = LitigationConsumer.__new__(LitigationConsumer)
        consumer.__init__()
        consumer.send = AsyncMock()

        with patch("apps.litigation_ai.consumers.litigation_consumer.settings") as mock_settings:
            mock_settings.DEBUG = False
            with patch(
                "apps.core.exceptions.error_presentation.ExceptionPresenter"
            ) as MockPresenter:
                presenter = MagicMock()
                envelope = MagicMock()
                envelope.code = "INTERNAL_ERROR"
                envelope.message = "Something failed"
                envelope.errors = {}
                envelope.retryable = False
                presenter.present.return_value = (envelope, None)
                MockPresenter.return_value = presenter

                await consumer.send_error(RuntimeError("boom"))
                consumer.send.assert_called_once()


class TestLitigationConsumerReceive:
    @pytest.mark.asyncio
    async def test_receive_empty_text(self):
        consumer = LitigationConsumer.__new__(LitigationConsumer)
        consumer.__init__()
        consumer.send = AsyncMock()
        await consumer.receive(text_data=None)
        consumer.send.assert_called_once()

    @pytest.mark.asyncio
    async def test_receive_invalid_json(self):
        consumer = LitigationConsumer.__new__(LitigationConsumer)
        consumer.__init__()
        consumer.send = AsyncMock()
        await consumer.receive(text_data="not json")
        consumer.send.assert_called_once()

    @pytest.mark.asyncio
    async def test_receive_not_dict(self):
        consumer = LitigationConsumer.__new__(LitigationConsumer)
        consumer.__init__()
        consumer.send = AsyncMock()
        await consumer.receive(text_data='[1, 2, 3]')
        consumer.send.assert_called_once()

    @pytest.mark.asyncio
    async def test_receive_missing_type(self):
        consumer = LitigationConsumer.__new__(LitigationConsumer)
        consumer.__init__()
        consumer.send = AsyncMock()
        await consumer.receive(text_data='{"key": "value"}')
        consumer.send.assert_called_once()

    @pytest.mark.asyncio
    async def test_receive_unknown_type(self):
        consumer = LitigationConsumer.__new__(LitigationConsumer)
        consumer.__init__()
        consumer.send = AsyncMock()
        await consumer.receive(text_data='{"type": "unknown"}')
        consumer.send.assert_called_once()


class TestLitigationConsumerStopGeneration:
    @pytest.mark.asyncio
    async def test_stop_generation(self):
        consumer = LitigationConsumer.__new__(LitigationConsumer)
        consumer.__init__()
        consumer.send = AsyncMock()
        consumer.session_id = "s1"
        consumer._send_flow_message = AsyncMock()
        await consumer.handle_stop_generation({})
        consumer._send_flow_message.assert_called_once()


class TestLitigationConsumerHandleUserMessage:
    @pytest.mark.asyncio
    async def test_empty_content(self):
        consumer = LitigationConsumer.__new__(LitigationConsumer)
        consumer.__init__()
        consumer.send = AsyncMock()
        await consumer.handle_user_message({"content": ""})
        consumer.send.assert_called_once()

    @pytest.mark.asyncio
    async def test_handle_stop_generation_sends_message(self):
        consumer = LitigationConsumer.__new__(LitigationConsumer)
        consumer.__init__()
        consumer._send_flow_message = AsyncMock()
        await consumer.handle_stop_generation({"type": "stop_generation"})
        consumer._send_flow_message.assert_called_once()
        call_args = consumer._send_flow_message.call_args[0][0]
        assert "停止生成" in call_args["content"]
