"""群聊工厂测试。"""

from __future__ import annotations

from apps.automation.services.chat.factory import ChatProviderFactory
from apps.automation.services.chat.base import ChatProvider
from apps.core.models.enums import ChatPlatform
from apps.core.dto.chat import ChatResult, MessageContent


class _StubProvider(ChatProvider):
    """测试用提供者。"""

    @property
    def platform(self) -> ChatPlatform:
        return ChatPlatform.FEISHU

    def is_available(self) -> bool:
        return True

    def create_chat(self, chat_name: str, owner_id: str | None = None) -> ChatResult:
        return ChatResult(success=True, chat_id="test")

    def send_message(self, chat_id: str, content: MessageContent) -> ChatResult:
        return ChatResult(success=True)

    def send_file(self, chat_id: str, file_path: str) -> ChatResult:
        return ChatResult(success=True)

    def get_chat_info(self, chat_id: str) -> dict:
        return {}


class _StubDingTalkProvider(ChatProvider):
    """测试用钉钉提供者。"""

    @property
    def platform(self) -> ChatPlatform:
        return ChatPlatform.DINGTALK

    def is_available(self) -> bool:
        return True

    def create_chat(self, chat_name: str, owner_id: str | None = None) -> ChatResult:
        return ChatResult(success=True, chat_id="dt_test")

    def send_message(self, chat_id: str, content: MessageContent) -> ChatResult:
        return ChatResult(success=True)

    def send_file(self, chat_id: str, file_path: str) -> ChatResult:
        return ChatResult(success=True)

    def get_chat_info(self, chat_id: str) -> dict:
        return {}


class TestChatProviderFactory:
    """ChatProviderFactory 测试。"""

    def setup_method(self) -> None:
        ChatProviderFactory._providers.clear()
        ChatProviderFactory._instances.clear()

    def test_register_provider(self) -> None:
        """注册提供者。"""
        ChatProviderFactory.register(ChatPlatform.FEISHU, _StubProvider)
        assert ChatPlatform.FEISHU in ChatProviderFactory._providers

    def test_get_available_platforms(self) -> None:
        """获取可用平台列表。"""
        ChatProviderFactory.register(ChatPlatform.FEISHU, _StubProvider)
        platforms = ChatProviderFactory.get_available_platforms()
        assert ChatPlatform.FEISHU in platforms

    def test_get_available_platforms_empty(self) -> None:
        """无注册平台时返回空列表。"""
        platforms = ChatProviderFactory.get_available_platforms()
        assert len(platforms) == 0

    def test_register_multiple_platforms(self) -> None:
        """注册多个平台。"""
        ChatProviderFactory.register(ChatPlatform.FEISHU, _StubProvider)
        ChatProviderFactory.register(ChatPlatform.DINGTALK, _StubDingTalkProvider)
        platforms = ChatProviderFactory.get_available_platforms()
        assert len(platforms) == 2

    def test_unregister_provider(self) -> None:
        """注销提供者。"""
        ChatProviderFactory.register(ChatPlatform.FEISHU, _StubProvider)
        ChatProviderFactory.unregister(ChatPlatform.FEISHU)
        platforms = ChatProviderFactory.get_available_platforms()
        assert ChatPlatform.FEISHU not in platforms

    def test_get_provider_registered(self) -> None:
        """获取已注册的提供者。"""
        ChatProviderFactory.register(ChatPlatform.FEISHU, _StubProvider)
        provider = ChatProviderFactory.get_provider(ChatPlatform.FEISHU)
        assert isinstance(provider, _StubProvider)

    def test_get_provider_not_registered_raises(self) -> None:
        """获取未注册的提供者抛出异常。"""
        try:
            ChatProviderFactory.get_provider(ChatPlatform.FEISHU)
            assert False, "应抛出异常"
        except Exception:
            pass


class TestChatResult:
    """ChatResult 测试。"""

    def test_success_result(self) -> None:
        result = ChatResult(success=True, chat_id="chat_123")
        assert result.success is True
        assert result.chat_id == "chat_123"

    def test_failure_result(self) -> None:
        result = ChatResult(success=False, message="创建失败")
        assert result.success is False
        assert result.message == "创建失败"
