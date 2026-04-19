"""钉钉群聊提供者单元测试"""

from unittest.mock import MagicMock, patch

import pytest

from apps.core.exceptions import ChatCreationException, ConfigurationException, MessageSendException
from apps.core.models.enums import ChatPlatform


@pytest.fixture
def mock_config():
    """钉钉完整配置"""
    return {
        "APP_KEY": "test_app_key",
        "APP_SECRET": "test_app_secret",
        "AGENT_ID": "test_agent_id",
        "DEFAULT_OWNER_ID": "test_owner_id",
        "TIMEOUT": 30,
    }


@pytest.fixture
def mock_incomplete_config():
    """钉钉不完整配置"""
    return {
        "APP_KEY": "test_app_key",
        # 缺少 APP_SECRET
        "TIMEOUT": 30,
    }


class TestDingtalkProviderPlatform:
    """测试钉钉 Provider 基本属性"""

    @patch("apps.automation.services.chat.dingtalk_provider.DingtalkProvider._load_config")
    def test_platform_returns_dingtalk(self, mock_load_config, mock_config):
        mock_load_config.return_value = mock_config
        from apps.automation.services.chat.dingtalk_provider import DingtalkProvider

        provider = DingtalkProvider()
        assert provider.platform == ChatPlatform.DINGTALK

    @patch("apps.automation.services.chat.dingtalk_provider.DingtalkProvider._load_config")
    def test_is_available_with_full_config(self, mock_load_config, mock_config):
        mock_load_config.return_value = mock_config
        from apps.automation.services.chat.dingtalk_provider import DingtalkProvider

        provider = DingtalkProvider()
        assert provider.is_available() is True

    @patch("apps.automation.services.chat.dingtalk_provider.DingtalkProvider._load_config")
    def test_is_not_available_with_incomplete_config(self, mock_load_config, mock_incomplete_config):
        mock_load_config.return_value = mock_incomplete_config
        from apps.automation.services.chat.dingtalk_provider import DingtalkProvider

        provider = DingtalkProvider()
        assert provider.is_available() is False

    @patch("apps.automation.services.chat.dingtalk_provider.DingtalkProvider._load_config")
    def test_is_not_available_without_default_owner_id(self, mock_load_config):
        config = {
            "APP_KEY": "test_app_key",
            "APP_SECRET": "test_app_secret",
            "AGENT_ID": "test_agent_id",
            "TIMEOUT": 30,
        }
        mock_load_config.return_value = config
        from apps.automation.services.chat.dingtalk_provider import DingtalkProvider

        provider = DingtalkProvider()
        assert provider.is_available() is False


class TestDingtalkProviderCreateChat:
    """测试钉钉创建群聊"""

    @patch("apps.automation.services.chat.dingtalk_provider.DingtalkProvider._load_config")
    def test_create_chat_without_config_raises(self, mock_load_config, mock_incomplete_config):
        mock_load_config.return_value = mock_incomplete_config
        from apps.automation.services.chat.dingtalk_provider import DingtalkProvider

        provider = DingtalkProvider()
        with pytest.raises(ConfigurationException):
            provider.create_chat("测试群聊")

    @patch("apps.automation.services.chat.dingtalk_provider.DingtalkProvider._load_config")
    @patch("apps.automation.services.chat.dingtalk_provider.httpx.post")
    def test_create_chat_success(self, mock_post, mock_load_config, mock_config):
        mock_load_config.return_value = mock_config
        from apps.automation.services.chat.dingtalk_provider import DingtalkProvider

        # Mock access_token
        mock_token_response = MagicMock()
        mock_token_response.status_code = 200
        mock_token_response.json.return_value = {
            "errcode": 0,
            "access_token": "test_access_token",
            "expires_in": 7200,
        }

        # Mock create chat
        mock_create_response = MagicMock()
        mock_create_response.status_code = 200
        mock_create_response.json.return_value = {
            "openConversationId": "conv_123",
            "chatId": "chat_123",
        }

        # Mock send initial message
        mock_send_response = MagicMock()
        mock_send_response.status_code = 200
        mock_send_response.json.return_value = {"code": "OK"}

        mock_post.side_effect = [mock_token_response, mock_create_response, mock_send_response]

        provider = DingtalkProvider()
        result = provider.create_chat("测试案件群")

        assert result.success is True
        assert result.chat_id == "chat_123"
        assert result.chat_name == "测试案件群"

    @patch("apps.automation.services.chat.dingtalk_provider.DingtalkProvider._load_config")
    @patch("apps.automation.services.chat.dingtalk_provider.httpx.post")
    def test_create_chat_with_owner_id(self, mock_post, mock_load_config, mock_config):
        mock_load_config.return_value = mock_config
        from apps.automation.services.chat.dingtalk_provider import DingtalkProvider

        mock_token_response = MagicMock()
        mock_token_response.status_code = 200
        mock_token_response.json.return_value = {
            "errcode": 0,
            "access_token": "test_access_token",
            "expires_in": 7200,
        }

        mock_create_response = MagicMock()
        mock_create_response.status_code = 200
        mock_create_response.json.return_value = {
            "openConversationId": "conv_456",
            "chatId": "chat_456",
        }

        mock_send_response = MagicMock()
        mock_send_response.status_code = 200
        mock_send_response.json.return_value = {"code": "OK"}

        mock_post.side_effect = [mock_token_response, mock_create_response, mock_send_response]

        provider = DingtalkProvider()
        result = provider.create_chat("测试案件群", owner_id="custom_owner")

        assert result.success is True
        # 验证创建群聊请求中使用了指定的 owner_id
        create_call = mock_post.call_args_list[1]
        assert create_call.kwargs["json"]["ownerUserId"] == "custom_owner"

    @patch("apps.automation.services.chat.dingtalk_provider.DingtalkProvider._load_config")
    @patch("apps.automation.services.chat.dingtalk_provider.httpx.post")
    def test_create_chat_api_error(self, mock_post, mock_load_config, mock_config):
        mock_load_config.return_value = mock_config
        from apps.automation.services.chat.dingtalk_provider import DingtalkProvider

        mock_token_response = MagicMock()
        mock_token_response.status_code = 200
        mock_token_response.json.return_value = {
            "errcode": 0,
            "access_token": "test_access_token",
            "expires_in": 7200,
        }

        mock_create_response = MagicMock()
        mock_create_response.status_code = 200
        mock_create_response.json.return_value = {
            "code": "invalidParameter",
            "message": "参数错误",
        }

        mock_post.side_effect = [mock_token_response, mock_create_response]

        provider = DingtalkProvider()
        with pytest.raises(ChatCreationException):
            provider.create_chat("测试案件群")


class TestDingtalkProviderSendMessage:
    """测试钉钉发送消息"""

    @patch("apps.automation.services.chat.dingtalk_provider.DingtalkProvider._load_config")
    def test_send_message_without_config_raises(self, mock_load_config, mock_incomplete_config):
        mock_load_config.return_value = mock_incomplete_config
        from apps.automation.services.chat.dingtalk_provider import DingtalkProvider
        from apps.core.dto.chat import MessageContent

        provider = DingtalkProvider()
        with pytest.raises(ConfigurationException):
            provider.send_message("chat_123", MessageContent(title="标题", text="内容"))

    @patch("apps.automation.services.chat.dingtalk_provider.DingtalkProvider._load_config")
    @patch("apps.automation.services.chat.dingtalk_provider.httpx.post")
    def test_send_message_success(self, mock_post, mock_load_config, mock_config):
        mock_load_config.return_value = mock_config
        from apps.automation.services.chat.dingtalk_provider import DingtalkProvider
        from apps.core.dto.chat import MessageContent

        mock_token_response = MagicMock()
        mock_token_response.status_code = 200
        mock_token_response.json.return_value = {
            "errcode": 0,
            "access_token": "test_access_token",
            "expires_in": 7200,
        }

        mock_send_response = MagicMock()
        mock_send_response.status_code = 200
        mock_send_response.json.return_value = {"code": "OK"}

        mock_post.side_effect = [mock_token_response, mock_send_response]

        provider = DingtalkProvider()
        result = provider.send_message("chat_123", MessageContent(title="法院通知", text="内容"))

        assert result.success is True
        assert result.chat_id == "chat_123"


class TestDingtalkProviderGetChatInfo:
    """测试钉钉获取群聊信息"""

    @patch("apps.automation.services.chat.dingtalk_provider.DingtalkProvider._load_config")
    @patch("apps.automation.services.chat.dingtalk_provider.httpx.get")
    def test_get_chat_info_success(self, mock_get, mock_load_config, mock_config):
        mock_load_config.return_value = mock_config
        from apps.automation.services.chat.dingtalk_provider import DingtalkProvider

        # Need to first get access_token
        with patch("apps.automation.services.chat.dingtalk_provider.httpx.post") as mock_post:
            mock_token_response = MagicMock()
            mock_token_response.status_code = 200
            mock_token_response.json.return_value = {
                "errcode": 0,
                "access_token": "test_access_token",
                "expires_in": 7200,
            }
            mock_post.return_value = mock_token_response

            mock_info_response = MagicMock()
            mock_info_response.status_code = 200
            mock_info_response.json.return_value = {
                "title": "测试群聊",
            }
            mock_get.return_value = mock_info_response

            provider = DingtalkProvider()
            result = provider.get_chat_info("chat_123")

            assert result.success is True
            assert result.chat_name == "测试群聊"


class TestDingtalkProviderFactory:
    """测试钉钉 Provider 工厂注册"""

    @patch("apps.automation.services.chat.dingtalk_provider.DingtalkProvider._load_config")
    def test_dingtalk_provider_registered(self, mock_load_config, mock_config):
        mock_load_config.return_value = mock_config
        from apps.automation.services.chat import ChatProviderFactory
        from apps.automation.services.chat.dingtalk_provider import DingtalkProvider

        ChatProviderFactory.register(ChatPlatform.DINGTALK, DingtalkProvider)
        assert ChatProviderFactory.is_platform_registered(ChatPlatform.DINGTALK)

        provider = ChatProviderFactory.get_provider(ChatPlatform.DINGTALK)
        assert isinstance(provider, DingtalkProvider)
        assert provider.platform == ChatPlatform.DINGTALK
