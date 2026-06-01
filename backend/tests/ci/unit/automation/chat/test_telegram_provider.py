"""Telegram 群聊提供者单元测试"""

from unittest.mock import MagicMock, patch

import pytest

from apps.core.exceptions import ChatCreationException, ConfigurationException, MessageSendException
from apps.core.models.enums import ChatPlatform


@pytest.fixture
def mock_config():
    """Telegram 完整配置"""
    return {
        "BOT_TOKEN": "123456:ABC-DEF",
        "SUPERGROUP_ID": -1001234567890,
        "TIMEOUT": 30,
    }


@pytest.fixture
def mock_incomplete_config():
    """Telegram 不完整配置"""
    return {
        "BOT_TOKEN": "123456:ABC-DEF",
        # 缺少 SUPERGROUP_ID
        "TIMEOUT": 30,
    }


class TestTelegramProviderPlatform:
    """测试 Telegram Provider 基本属性"""

    @patch("apps.automation.services.chat.telegram_provider.TelegramProvider._load_config")
    def test_platform_returns_telegram(self, mock_load_config, mock_config):
        mock_load_config.return_value = mock_config
        from apps.automation.services.chat.telegram_provider import TelegramProvider

        provider = TelegramProvider()
        assert provider.platform == ChatPlatform.TELEGRAM

    @patch("apps.automation.services.chat.telegram_provider.TelegramProvider._load_config")
    def test_is_available_with_full_config(self, mock_load_config, mock_config):
        mock_load_config.return_value = mock_config
        from apps.automation.services.chat.telegram_provider import TelegramProvider

        provider = TelegramProvider()
        assert provider.is_available() is True

    @patch("apps.automation.services.chat.telegram_provider.TelegramProvider._load_config")
    def test_is_not_available_with_incomplete_config(self, mock_load_config, mock_incomplete_config):
        mock_load_config.return_value = mock_incomplete_config
        from apps.automation.services.chat.telegram_provider import TelegramProvider

        provider = TelegramProvider()
        assert provider.is_available() is False

    @patch("apps.automation.services.chat.telegram_provider.TelegramProvider._load_config")
    def test_is_not_available_without_bot_token(self, mock_load_config):
        config = {
            "SUPERGROUP_ID": -1001234567890,
            "TIMEOUT": 30,
        }
        mock_load_config.return_value = config
        from apps.automation.services.chat.telegram_provider import TelegramProvider

        provider = TelegramProvider()
        assert provider.is_available() is False


class TestTelegramProviderCreateChat:
    """测试 Telegram 创建话题（一案一群）"""

    @patch("apps.automation.services.chat.telegram_provider.TelegramProvider._load_config")
    def test_create_chat_without_config_raises(self, mock_load_config, mock_incomplete_config):
        mock_load_config.return_value = mock_incomplete_config
        from apps.automation.services.chat.telegram_provider import TelegramProvider

        provider = TelegramProvider()
        with pytest.raises(ConfigurationException):
            provider.create_chat("测试话题")

    @patch("apps.automation.services.chat.telegram_provider.TelegramProvider._load_config")
    @patch("apps.automation.services.chat.telegram_provider.httpx.post")
    def test_create_chat_success(self, mock_post, mock_load_config, mock_config):
        mock_load_config.return_value = mock_config
        from apps.automation.services.chat.telegram_provider import TelegramProvider

        # Mock createForumTopic
        mock_create_response = MagicMock()
        mock_create_response.status_code = 200
        mock_create_response.json.return_value = {
            "ok": True,
            "result": {
                "message_thread_id": 42,
            },
        }

        # Mock send initial message
        mock_send_response = MagicMock()
        mock_send_response.status_code = 200
        mock_send_response.json.return_value = {
            "ok": True,
            "result": {"message_id": 1},
        }

        mock_post.side_effect = [mock_create_response, mock_send_response]

        provider = TelegramProvider()
        result = provider.create_chat("测试案件话题")

        assert result.success is True
        # chat_id 格式: supergroup_id:thread_id
        assert result.chat_id == "-1001234567890:42"
        assert result.chat_name == "测试案件话题"

    @patch("apps.automation.services.chat.telegram_provider.TelegramProvider._load_config")
    @patch("apps.automation.services.chat.telegram_provider.httpx.post")
    def test_create_chat_api_error(self, mock_post, mock_load_config, mock_config):
        mock_load_config.return_value = mock_config
        from apps.automation.services.chat.telegram_provider import TelegramProvider

        mock_create_response = MagicMock()
        mock_create_response.status_code = 200
        mock_create_response.json.return_value = {
            "ok": False,
            "error_code": 400,
            "description": "Bad Request: chat not found",
        }

        mock_post.return_value = mock_create_response

        provider = TelegramProvider()
        with pytest.raises(ChatCreationException):
            provider.create_chat("测试话题")

    @patch("apps.automation.services.chat.telegram_provider.TelegramProvider._load_config")
    @patch("apps.automation.services.chat.telegram_provider.httpx.post")
    def test_create_chat_returns_combined_chat_id(self, mock_post, mock_load_config, mock_config):
        mock_load_config.return_value = mock_config
        from apps.automation.services.chat.telegram_provider import TelegramProvider

        mock_create_response = MagicMock()
        mock_create_response.status_code = 200
        mock_create_response.json.return_value = {
            "ok": True,
            "result": {
                "message_thread_id": 99,
            },
        }

        mock_send_response = MagicMock()
        mock_send_response.status_code = 200
        mock_send_response.json.return_value = {
            "ok": True,
            "result": {"message_id": 1},
        }

        mock_post.side_effect = [mock_create_response, mock_send_response]

        provider = TelegramProvider()
        result = provider.create_chat("案件A")

        assert ":" in result.chat_id
        parts = result.chat_id.split(":")
        assert parts[0] == "-1001234567890"
        assert parts[1] == "99"


class TestTelegramProviderSendMessage:
    """测试 Telegram 发送消息"""

    @patch("apps.automation.services.chat.telegram_provider.TelegramProvider._load_config")
    def test_send_message_without_config_raises(self, mock_load_config, mock_incomplete_config):
        mock_load_config.return_value = mock_incomplete_config
        from apps.automation.services.chat.telegram_provider import TelegramProvider
        from apps.core.dto.chat import MessageContent

        provider = TelegramProvider()
        with pytest.raises(ConfigurationException):
            provider.send_message("chat_123", MessageContent(title="标题", text="内容"))

    @patch("apps.automation.services.chat.telegram_provider.TelegramProvider._load_config")
    @patch("apps.automation.services.chat.telegram_provider.httpx.post")
    def test_send_message_to_topic(self, mock_post, mock_load_config, mock_config):
        mock_load_config.return_value = mock_config
        from apps.automation.services.chat.telegram_provider import TelegramProvider
        from apps.core.dto.chat import MessageContent

        mock_send_response = MagicMock()
        mock_send_response.status_code = 200
        mock_send_response.json.return_value = {
            "ok": True,
            "result": {"message_id": 100},
        }

        mock_post.return_value = mock_send_response

        provider = TelegramProvider()
        # chat_id 格式: supergroup_id:thread_id
        result = provider.send_message("-1001234567890:42", MessageContent(title="法院通知", text="内容"))

        assert result.success is True
        # 验证消息发送到了正确的话题
        call_payload = mock_post.call_args.kwargs["json"]
        assert call_payload["chat_id"] == "-1001234567890"
        assert call_payload["message_thread_id"] == 42

    @patch("apps.automation.services.chat.telegram_provider.TelegramProvider._load_config")
    @patch("apps.automation.services.chat.telegram_provider.httpx.post")
    def test_send_message_to_plain_chat(self, mock_post, mock_load_config, mock_config):
        mock_load_config.return_value = mock_config
        from apps.automation.services.chat.telegram_provider import TelegramProvider
        from apps.core.dto.chat import MessageContent

        mock_send_response = MagicMock()
        mock_send_response.status_code = 200
        mock_send_response.json.return_value = {
            "ok": True,
            "result": {"message_id": 100},
        }

        mock_post.return_value = mock_send_response

        provider = TelegramProvider()
        result = provider.send_message("-1001234567890", MessageContent(title="通知", text="内容"))

        assert result.success is True
        call_payload = mock_post.call_args.kwargs["json"]
        assert call_payload["chat_id"] == "-1001234567890"
        assert "message_thread_id" not in call_payload

    @patch("apps.automation.services.chat.telegram_provider.TelegramProvider._load_config")
    @patch("apps.automation.services.chat.telegram_provider.httpx.post")
    def test_send_message_api_error(self, mock_post, mock_load_config, mock_config):
        mock_load_config.return_value = mock_config
        from apps.automation.services.chat.telegram_provider import TelegramProvider
        from apps.core.dto.chat import MessageContent

        mock_send_response = MagicMock()
        mock_send_response.status_code = 200
        mock_send_response.json.return_value = {
            "ok": False,
            "error_code": 403,
            "description": "Forbidden: bot is not a member of the group chat",
        }

        mock_post.return_value = mock_send_response

        provider = TelegramProvider()
        with pytest.raises(MessageSendException):
            provider.send_message("-1001234567890:42", MessageContent(title="通知", text="内容"))


class TestTelegramProviderGetChatInfo:
    """测试 Telegram 获取群聊信息"""

    @patch("apps.automation.services.chat.telegram_provider.TelegramProvider._load_config")
    @patch("apps.automation.services.chat.telegram_provider.httpx.post")
    def test_get_chat_info_success(self, mock_post, mock_load_config, mock_config):
        mock_load_config.return_value = mock_config
        from apps.automation.services.chat.telegram_provider import TelegramProvider

        mock_info_response = MagicMock()
        mock_info_response.status_code = 200
        mock_info_response.json.return_value = {
            "ok": True,
            "result": {
                "id": -1001234567890,
                "title": "法穿案件群",
                "type": "supergroup",
            },
        }

        mock_post.return_value = mock_info_response

        provider = TelegramProvider()
        result = provider.get_chat_info("-1001234567890:42")

        assert result.success is True
        assert result.chat_name == "法穿案件群"
        # 验证话题信息附加到了 raw_response
        assert result.raw_response["topic_info"]["message_thread_id"] == 42


class TestTelegramProviderParseChatId:
    """测试 Telegram chat_id 解析"""

    @patch("apps.automation.services.chat.telegram_provider.TelegramProvider._load_config")
    def test_parse_plain_chat_id(self, mock_load_config, mock_config):
        mock_load_config.return_value = mock_config
        from apps.automation.services.chat.telegram_provider import TelegramProvider

        provider = TelegramProvider()
        chat_id, thread_id = provider._parse_chat_id("-1001234567890")
        assert chat_id == "-1001234567890"
        assert thread_id is None

    @patch("apps.automation.services.chat.telegram_provider.TelegramProvider._load_config")
    def test_parse_topic_chat_id(self, mock_load_config, mock_config):
        mock_load_config.return_value = mock_config
        from apps.automation.services.chat.telegram_provider import TelegramProvider

        provider = TelegramProvider()
        chat_id, thread_id = provider._parse_chat_id("-1001234567890:42")
        assert chat_id == "-1001234567890"
        assert thread_id == 42

    @patch("apps.automation.services.chat.telegram_provider.TelegramProvider._load_config")
    def test_parse_invalid_thread_id(self, mock_load_config, mock_config):
        mock_load_config.return_value = mock_config
        from apps.automation.services.chat.telegram_provider import TelegramProvider

        provider = TelegramProvider()
        chat_id, thread_id = provider._parse_chat_id("-1001234567890:invalid")
        assert chat_id == "-1001234567890:invalid"
        assert thread_id is None


class TestTelegramProviderFactory:
    """测试 Telegram Provider 工厂注册"""

    @patch("apps.automation.services.chat.telegram_provider.TelegramProvider._load_config")
    def test_telegram_provider_registered(self, mock_load_config, mock_config):
        mock_load_config.return_value = mock_config
        from apps.automation.services.chat import ChatProviderFactory
        from apps.automation.services.chat.telegram_provider import TelegramProvider

        ChatProviderFactory.register(ChatPlatform.TELEGRAM, TelegramProvider)
        assert ChatProviderFactory.is_platform_registered(ChatPlatform.TELEGRAM)

        provider = ChatProviderFactory.get_provider(ChatPlatform.TELEGRAM)
        assert isinstance(provider, TelegramProvider)
        assert provider.platform == ChatPlatform.TELEGRAM
