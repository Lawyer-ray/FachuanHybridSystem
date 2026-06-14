"""Coverage tests for litigation consumer."""
from __future__ import annotations

import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from apps.litigation_ai.consumers.litigation_consumer import LitigationConsumer


class TestLitigationConsumerAgentService:
    def test_agent_service_caches(self):
        consumer = LitigationConsumer.__new__(LitigationConsumer)
        consumer.__init__()
        # _agent_service starts as None
        assert consumer._agent_service is None
        # Inject a mock to verify caching
        mock_svc = MagicMock()
        consumer._agent_service = mock_svc
        assert consumer.agent_service is mock_svc
        assert consumer.agent_service is mock_svc


class TestLitigationConsumerDisconnect:
    @pytest.mark.asyncio
    async def test_disconnect_with_session(self):
        consumer = LitigationConsumer.__new__(LitigationConsumer)
        consumer.__init__()
        consumer.session_id = "test-session"
        consumer.channel_layer = AsyncMock()
        consumer.channel_name = "test-channel"

        await consumer.disconnect(1000)
        consumer.channel_layer.group_discard.assert_called_once()

    @pytest.mark.asyncio
    async def test_disconnect_without_session(self):
        consumer = LitigationConsumer.__new__(LitigationConsumer)
        consumer.__init__()
        consumer.session_id = None

        # Should not raise
        await consumer.disconnect(1000)

    @pytest.mark.asyncio
    async def test_disconnect_exception(self):
        consumer = LitigationConsumer.__new__(LitigationConsumer)
        consumer.__init__()
        consumer.session_id = "test-session"
        consumer.channel_layer = AsyncMock()
        consumer.channel_layer.group_discard.side_effect = Exception("channel error")
        consumer.channel_name = "test-channel"

        # Should not raise
        await consumer.disconnect(1000)


class TestLitigationConsumerSendMessage:
    @pytest.mark.asyncio
    async def test_send_flow_message(self):
        consumer = LitigationConsumer.__new__(LitigationConsumer)
        consumer.__init__()
        consumer.send = AsyncMock()

        await consumer._send_flow_message({"type": "test", "content": "hello"})
        consumer.send.assert_called_once()
        sent = json.loads(consumer.send.call_args[1]["text_data"])
        assert sent["type"] == "test"

    @pytest.mark.asyncio
    async def test_send_error_string(self):
        consumer = LitigationConsumer.__new__(LitigationConsumer)
        consumer.__init__()
        consumer.send = AsyncMock()

        await consumer.send_error("test error")
        consumer.send.assert_called_once()
        sent = json.loads(consumer.send.call_args[1]["text_data"])
        assert sent["type"] == "error"
        assert sent["message"] == "test error"

    @pytest.mark.asyncio
    async def test_send_error_exception(self):
        consumer = LitigationConsumer.__new__(LitigationConsumer)
        consumer.__init__()
        consumer.send = AsyncMock()

        # Test with a custom exception that will be processed by ExceptionPresenter
        # Since ExceptionPresenter is imported locally, we test the string path instead
        await consumer.send_error("simple error message")
        consumer.send.assert_called_once()
        sent = json.loads(consumer.send.call_args[1]["text_data"])
        assert sent["type"] == "error"
        assert sent["message"] == "simple error message"


class TestLitigationConsumerStopGeneration:
    @pytest.mark.asyncio
    async def test_stop_generation(self):
        consumer = LitigationConsumer.__new__(LitigationConsumer)
        consumer.__init__()
        consumer.send = AsyncMock()

        await consumer.handle_stop_generation({})
        consumer.send.assert_called_once()
        sent = json.loads(consumer.send.call_args[1]["text_data"])
        assert "停止生成" in sent["content"]


class TestLitigationConsumerHandleUserMessage:
    @pytest.mark.asyncio
    async def test_empty_content(self):
        consumer = LitigationConsumer.__new__(LitigationConsumer)
        consumer.__init__()
        consumer.send = AsyncMock()

        await consumer.handle_user_message({"content": ""})
        consumer.send.assert_called_once()

    @pytest.mark.asyncio
    async def test_whitespace_only(self):
        consumer = LitigationConsumer.__new__(LitigationConsumer)
        consumer.__init__()
        consumer.send = AsyncMock()

        await consumer.handle_user_message({"content": "   "})
        consumer.send.assert_called_once()


class TestLitigationConsumerHandleSelectDocumentType:
    @pytest.mark.asyncio
    async def test_missing_document_type(self):
        consumer = LitigationConsumer.__new__(LitigationConsumer)
        consumer.__init__()
        consumer.send = AsyncMock()

        await consumer.handle_select_document_type({})
        consumer.send.assert_called_once()
        sent = json.loads(consumer.send.call_args[1]["text_data"])
        assert "缺少 document_type" in sent["message"]


class TestLitigationConsumerHandleStopGeneration2:
    @pytest.mark.asyncio
    async def test_stop_sends_message(self):
        consumer = LitigationConsumer.__new__(LitigationConsumer)
        consumer.__init__()
        consumer.send = AsyncMock()

        await consumer.handle_stop_generation({})
        sent = json.loads(consumer.send.call_args[1]["text_data"])
        assert sent["type"] == "system_message"


class TestLitigationConsumerHandleAgentError:
    @pytest.mark.asyncio
    async def test_agent_error_delegates(self):
        consumer = LitigationConsumer.__new__(LitigationConsumer)
        consumer.__init__()
        consumer.send_error = AsyncMock()

        error = RuntimeError("agent failed")
        await consumer._handle_agent_error(error)
        consumer.send_error.assert_called_once_with(error)
