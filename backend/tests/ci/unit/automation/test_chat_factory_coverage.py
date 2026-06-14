"""Coverage tests for automation/services/chat/factory.py — ChatProviderFactory."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from apps.core.exceptions import ConfigurationException, UnsupportedPlatformException
from apps.core.models.enums import ChatPlatform
from apps.automation.services.chat.factory import ChatProviderFactory
from apps.automation.services.chat.base import ChatProvider


class MockChatProvider(ChatProvider):
    """Minimal concrete provider for testing."""

    @property
    def platform(self) -> ChatPlatform:
        return ChatPlatform.FEISHU

    def create_chat(self, chat_name: str, owner_id: str | None = None):
        return MagicMock()

    def send_message(self, chat_id: str, content):
        return MagicMock()

    def send_file(self, chat_id: str, file_path: str):
        return MagicMock()

    def get_chat_info(self, chat_id: str):
        return MagicMock()

    def is_available(self) -> bool:
        return True


class MockChatProviderBadPlatform(ChatProvider):
    """Provider with mismatched platform."""

    @property
    def platform(self) -> ChatPlatform:
        return ChatPlatform.DINGTALK

    def create_chat(self, chat_name: str, owner_id: str | None = None):
        return MagicMock()

    def send_message(self, chat_id: str, content):
        return MagicMock()

    def send_file(self, chat_id: str, file_path: str):
        return MagicMock()

    def get_chat_info(self, chat_id: str):
        return MagicMock()

    def is_available(self) -> bool:
        return True


@pytest.fixture(autouse=True)
def clean_factory():
    """Ensure factory is clean before and after tests."""
    ChatProviderFactory.clear_cache()
    yield
    ChatProviderFactory.clear_cache()
    # Clean up any test registrations
    for p in list(ChatProviderFactory.get_registered_platforms()):
        ChatProviderFactory.unregister(p)


class TestChatProviderFactoryRegister:
    def test_register_valid_provider(self) -> None:
        ChatProviderFactory.register(ChatPlatform.FEISHU, MockChatProvider)
        assert ChatProviderFactory.is_platform_registered(ChatPlatform.FEISHU)

    def test_register_non_chat_provider_raises(self) -> None:
        with pytest.raises(TypeError, match="必须继承 ChatProvider"):
            ChatProviderFactory.register(ChatPlatform.FEISHU, dict)  # type: ignore[arg-type]

    def test_register_clears_cached_instance(self) -> None:
        ChatProviderFactory.register(ChatPlatform.FEISHU, MockChatProvider)
        ChatProviderFactory.get_provider(ChatPlatform.FEISHU)
        # Re-register should clear cache
        ChatProviderFactory.register(ChatPlatform.FEISHU, MockChatProvider)
        assert ChatPlatform.FEISHU not in ChatProviderFactory._instances


class TestChatProviderFactoryGetProvider:
    def test_get_provider_unregistered(self) -> None:
        with pytest.raises(UnsupportedPlatformException):
            ChatProviderFactory.get_provider(ChatPlatform.FEISHU)

    def test_get_provider_returns_cached(self) -> None:
        ChatProviderFactory.register(ChatPlatform.FEISHU, MockChatProvider)
        p1 = ChatProviderFactory.get_provider(ChatPlatform.FEISHU)
        p2 = ChatProviderFactory.get_provider(ChatPlatform.FEISHU)
        assert p1 is p2

    def test_get_provider_bad_platform_property(self) -> None:
        ChatProviderFactory.register(ChatPlatform.FEISHU, MockChatProviderBadPlatform)
        with pytest.raises(ConfigurationException):
            ChatProviderFactory.get_provider(ChatPlatform.FEISHU)


class TestChatProviderFactoryMisc:
    def test_unregister_existing(self) -> None:
        ChatProviderFactory.register(ChatPlatform.FEISHU, MockChatProvider)
        assert ChatProviderFactory.unregister(ChatPlatform.FEISHU) is True
        assert not ChatProviderFactory.is_platform_registered(ChatPlatform.FEISHU)

    def test_unregister_nonexistent(self) -> None:
        assert ChatProviderFactory.unregister(ChatPlatform.FEISHU) is False

    def test_get_available_platforms(self) -> None:
        ChatProviderFactory.register(ChatPlatform.FEISHU, MockChatProvider)
        available = ChatProviderFactory.get_available_platforms()
        assert ChatPlatform.FEISHU in available

    def test_get_registered_platforms(self) -> None:
        ChatProviderFactory.register(ChatPlatform.FEISHU, MockChatProvider)
        registered = ChatProviderFactory.get_registered_platforms()
        assert ChatPlatform.FEISHU in registered

    def test_clear_cache(self) -> None:
        ChatProviderFactory.register(ChatPlatform.FEISHU, MockChatProvider)
        ChatProviderFactory.get_provider(ChatPlatform.FEISHU)
        assert ChatPlatform.FEISHU in ChatProviderFactory._instances
        ChatProviderFactory.clear_cache()
        assert ChatPlatform.FEISHU not in ChatProviderFactory._instances
