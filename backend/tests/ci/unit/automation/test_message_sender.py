"""Tests for apps/automation/integrations/chat/message_sender.py — ChatProviderMessageSender."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from apps.core.dto.chat import ChatResult
from apps.core.models.enums import ChatPlatform


class TestChatMessageSenderProtocol:
    """ChatMessageSender protocol 存在性检查。"""

    def test_protocol_exists(self) -> None:
        from apps.automation.integrations.chat.message_sender import ChatMessageSender

        assert hasattr(ChatMessageSender, "send_text")


class TestChatProviderMessageSender:
    """ChatProviderMessageSender.send_text 单元测试。"""

    def _make_sender(self):
        from apps.automation.integrations.chat.message_sender import ChatProviderMessageSender

        return ChatProviderMessageSender()

    def test_send_text_delegates_to_provider(self) -> None:
        """send_text 调用 ChatProviderFactory.get_provider().send_message()。"""
        mock_factory = MagicMock()
        mock_provider = MagicMock()
        expected = ChatResult(success=True, chat_id="c1", message="ok")
        mock_provider.send_message.return_value = expected
        mock_factory.get_provider.return_value = mock_provider

        sender = self._make_sender()
        fake_factory_mod = MagicMock()
        fake_factory_mod.ChatProviderFactory = mock_factory

        with patch.dict("sys.modules", {"apps.automation.services.chat.factory": fake_factory_mod}):
            result = sender.send_text(
                platform=ChatPlatform.DINGTALK,
                chat_id="chat_123",
                text="hello",
            )

        assert result is expected
        mock_factory.get_provider.assert_called_once_with(ChatPlatform.DINGTALK)

    def test_send_text_constructs_message_content(self) -> None:
        """send_text 构造正确的 MessageContent(title='', text=text, file_path=None)。"""
        mock_factory = MagicMock()
        mock_provider = MagicMock()
        mock_provider.send_message.return_value = ChatResult(success=True, chat_id="c1", message="ok")
        mock_factory.get_provider.return_value = mock_provider

        sender = self._make_sender()
        fake_factory_mod = MagicMock()
        fake_factory_mod.ChatProviderFactory = mock_factory

        with patch.dict("sys.modules", {"apps.automation.services.chat.factory": fake_factory_mod}):
            sender.send_text(
                platform=ChatPlatform.DINGTALK,
                chat_id="chat_123",
                text="hello world",
            )

        call_args = mock_provider.send_message.call_args
        assert call_args[0][0] == "chat_123"
        content = call_args[0][1]
        assert content.text == "hello world"
        assert content.title == ""
        assert content.file_path is None

    def test_send_text_different_platforms(self) -> None:
        """不同平台参数都能正确传递。"""
        mock_factory = MagicMock()
        mock_provider = MagicMock()
        mock_provider.send_message.return_value = ChatResult(success=True, chat_id="c", message="ok")
        mock_factory.get_provider.return_value = mock_provider

        sender = self._make_sender()
        fake_factory_mod = MagicMock()
        fake_factory_mod.ChatProviderFactory = mock_factory

        with patch.dict("sys.modules", {"apps.automation.services.chat.factory": fake_factory_mod}):
            for platform in [ChatPlatform.DINGTALK, ChatPlatform.WECHAT_WORK, ChatPlatform.FEISHU]:
                sender.send_text(platform=platform, chat_id="c", text="t")
                mock_factory.get_provider.assert_called_with(platform)

    def test_frozen_dataclass(self) -> None:
        """ChatProviderMessageSender 是 frozen dataclass。"""
        sender = self._make_sender()
        with pytest.raises(AttributeError):
            sender.foo = "bar"  # type: ignore[misc]
