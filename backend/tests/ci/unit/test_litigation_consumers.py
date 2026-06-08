"""litigation_ai/consumers/ 单元测试（litigation_consumer + mock_trial_consumer）。"""

from __future__ import annotations

import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from apps.litigation_ai.consumers.litigation_consumer import LitigationConsumer, _use_agent_mode


class TestUseAgentMode:
    """_use_agent_mode 函数测试。"""

    @patch("apps.litigation_ai.consumers.litigation_consumer.settings")
    def test_default_false(self, mock_settings: MagicMock) -> None:
        del mock_settings.LITIGATION_USE_AGENT_MODE
        # getattr with default will return False
        assert _use_agent_mode() is False

    @patch("apps.litigation_ai.consumers.litigation_consumer.settings")
    def test_true_when_set(self, mock_settings: MagicMock) -> None:
        mock_settings.LITIGATION_USE_AGENT_MODE = True
        assert _use_agent_mode() is True

    @patch("apps.litigation_ai.consumers.litigation_consumer.settings")
    def test_false_when_set(self, mock_settings: MagicMock) -> None:
        mock_settings.LITIGATION_USE_AGENT_MODE = False
        assert _use_agent_mode() is False


class TestLitigationConsumerInit:
    """LitigationConsumer 初始化测试。"""

    def test_init_defaults(self) -> None:
        consumer = LitigationConsumer.__new__(LitigationConsumer)
        consumer.__init__()
        assert consumer.session_id is None
        assert consumer.user is None
        assert consumer.session is None
        assert consumer._agent_service is None


class TestLitigationConsumerGetMessageHandler:
    """_get_message_handler 测试。"""

    def _make_consumer(self):
        consumer = LitigationConsumer.__new__(LitigationConsumer)
        consumer.session_id = None
        consumer.user = None
        consumer.session = None
        consumer._agent_service = None
        return consumer

    def test_known_types(self) -> None:
        consumer = self._make_consumer()
        assert consumer._get_message_handler("user_message") is not None
        assert consumer._get_message_handler("select_document_type") is not None
        assert consumer._get_message_handler("select_evidence") is not None
        assert consumer._get_message_handler("confirm_generate") is not None
        assert consumer._get_message_handler("stop_generation") is not None

    def test_unknown_type_returns_none(self) -> None:
        consumer = self._make_consumer()
        assert consumer._get_message_handler("unknown_type") is None


class TestLitigationConsumerSendError:
    """send_error 测试。"""

    @pytest.mark.asyncio
    async def test_string_error(self) -> None:
        consumer = LitigationConsumer.__new__(LitigationConsumer)
        consumer.session_id = None
        consumer.user = None
        consumer.session = None
        consumer._agent_service = None
        consumer.send = AsyncMock()
        await consumer.send_error("test error")
        consumer.send.assert_called_once()
        call_args = consumer.send.call_args
        payload = json.loads(call_args[1]["text_data"])
        assert payload["type"] == "error"
        assert payload["message"] == "test error"

    @pytest.mark.asyncio
    async def test_string_error_with_code(self) -> None:
        consumer = LitigationConsumer.__new__(LitigationConsumer)
        consumer.session_id = None
        consumer.user = None
        consumer.session = None
        consumer._agent_service = None
        consumer.send = AsyncMock()
        await consumer.send_error("error", code="MY_CODE")
        call_args = consumer.send.call_args
        payload = json.loads(call_args[1]["text_data"])
        assert payload["code"] == "MY_CODE"


class TestLitigationConsumerSendFlowMessage:
    """_send_flow_message 测试。"""

    @pytest.mark.asyncio
    async def test_sends_json(self) -> None:
        consumer = LitigationConsumer.__new__(LitigationConsumer)
        consumer.session_id = None
        consumer.user = None
        consumer.session = None
        consumer._agent_service = None
        consumer.send = AsyncMock()
        await consumer._send_flow_message({"type": "test", "content": "hello"})
        consumer.send.assert_called_once()
        call_args = consumer.send.call_args
        payload = json.loads(call_args[1]["text_data"])
        assert payload["type"] == "test"
        assert payload["content"] == "hello"


class TestMockTrialConsumerGetHandler:
    """MockTrialConsumer._get_handler 测试。"""

    def _make_consumer(self):
        from apps.litigation_ai.consumers.mock_trial_consumer import MockTrialConsumer
        consumer = MockTrialConsumer.__new__(MockTrialConsumer)
        consumer.session_id = None
        consumer.user = None
        consumer.session = None
        return consumer

    def test_known_types(self) -> None:
        consumer = self._make_consumer()
        assert consumer._get_handler("user_message") is not None
        assert consumer._get_handler("select_mode") is not None
        assert consumer._get_handler("skip_evidence") is not None
        assert consumer._get_handler("end_debate") is not None
        assert consumer._get_handler("set_difficulty") is not None

    def test_unknown_type_returns_none(self) -> None:
        consumer = self._make_consumer()
        assert consumer._get_handler("unknown") is None


class TestMockTrialConsumerSendMessage:
    """MockTrialConsumer._send_message 测试。"""

    @pytest.mark.asyncio
    async def test_sends_json(self) -> None:
        from apps.litigation_ai.consumers.mock_trial_consumer import MockTrialConsumer
        consumer = MockTrialConsumer.__new__(MockTrialConsumer)
        consumer.session_id = None
        consumer.user = None
        consumer.session = None
        consumer.send = AsyncMock()
        await consumer._send_message({"type": "test", "data": "value"})
        consumer.send.assert_called_once()


class TestMockTrialConsumerSendProgress:
    """MockTrialConsumer._send_progress 测试。"""

    @pytest.mark.asyncio
    async def test_progress_calculation(self) -> None:
        from apps.litigation_ai.consumers.mock_trial_consumer import MockTrialConsumer
        consumer = MockTrialConsumer.__new__(MockTrialConsumer)
        consumer.session_id = None
        consumer.user = None
        consumer.session = None
        consumer.send = AsyncMock()
        await consumer._send_progress(3, 10, "处理中")
        call_args = consumer.send.call_args
        payload = json.loads(call_args[1]["text_data"])
        assert payload["percentage"] == 30
        assert payload["current"] == 3
        assert payload["total"] == 10

    @pytest.mark.asyncio
    async def test_zero_total(self) -> None:
        from apps.litigation_ai.consumers.mock_trial_consumer import MockTrialConsumer
        consumer = MockTrialConsumer.__new__(MockTrialConsumer)
        consumer.session_id = None
        consumer.user = None
        consumer.session = None
        consumer.send = AsyncMock()
        await consumer._send_progress(0, 0)
        call_args = consumer.send.call_args
        payload = json.loads(call_args[1]["text_data"])
        assert payload["percentage"] == 0


class TestMockTrialConsumerSendError:
    """MockTrialConsumer._send_error 测试。"""

    @pytest.mark.asyncio
    async def test_string_error(self) -> None:
        from apps.litigation_ai.consumers.mock_trial_consumer import MockTrialConsumer
        consumer = MockTrialConsumer.__new__(MockTrialConsumer)
        consumer.session_id = None
        consumer.user = None
        consumer.session = None
        consumer.send = AsyncMock()
        await consumer._send_error("test error")
        consumer.send.assert_called_once()
        call_args = consumer.send.call_args
        payload = json.loads(call_args[1]["text_data"])
        assert payload["type"] == "error"
        assert payload["message"] == "test error"
