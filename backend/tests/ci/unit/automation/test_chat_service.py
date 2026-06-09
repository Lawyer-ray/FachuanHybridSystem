"""
Tests for apps.automation.services.chat — 飞书/群聊相关服务
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch, PropertyMock

import pytest


# ============================================================
# FeishuFileMixin 测试
# ============================================================


class TestFeishuFileMixin:
    """FeishuFileMixin 测试"""

    def _make_mixin(self):
        from apps.automation.services.chat._feishu_file_mixin import FeishuFileMixin

        class ConcreteFeishuFile(FeishuFileMixin):
            BASE_URL = "https://open.feishu.cn"
            ENDPOINTS = {"upload_file": "/im/v1/files", "send_message": "/im/v1/messages"}
            config = {"TIMEOUT": 30}

            def is_available(self):
                return True

            def _get_tenant_access_token(self):
                return "test_token"

        return ConcreteFeishuFile()

    def test_get_file_type_pdf(self) -> None:
        mixin = self._make_mixin()
        assert mixin._get_file_type("/path/file.pdf") == "pdf"

    def test_get_file_type_docx(self) -> None:
        mixin = self._make_mixin()
        assert mixin._get_file_type("/path/file.docx") == "docx"

    def test_get_file_type_unknown(self) -> None:
        mixin = self._make_mixin()
        assert mixin._get_file_type("/path/file.xyz") == "stream"

    def test_get_file_type_mp4(self) -> None:
        mixin = self._make_mixin()
        assert mixin._get_file_type("/path/video.mp4") == "mp4"

    def test_get_file_type_pptx(self) -> None:
        mixin = self._make_mixin()
        assert mixin._get_file_type("/path/slide.pptx") == "pptx"

    def test_get_mime_type(self) -> None:
        mixin = self._make_mixin()
        mime = mixin._get_mime_type("/path/file.pdf")
        assert "pdf" in mime.lower() or mime == "application/octet-stream"

    def test_send_file_not_available(self, tmp_path) -> None:
        from apps.automation.services.chat._feishu_file_mixin import FeishuFileMixin
        from apps.core.exceptions import ConfigurationException

        mixin = self._make_mixin()
        mixin.is_available = lambda: False
        with pytest.raises(ConfigurationException):
            mixin.send_file("chat_id", str(tmp_path / "file.pdf"))

    def test_send_file_not_exists(self) -> None:
        from apps.core.exceptions import MessageSendException

        mixin = self._make_mixin()
        with pytest.raises(MessageSendException):
            mixin.send_file("chat_id", "/nonexistent/file.pdf")

    def test_send_file_too_large(self, tmp_path) -> None:
        """Test that files exceeding MAX_FILE_SIZE raise MessageSendException."""
        from apps.core.exceptions import MessageSendException

        mixin = self._make_mixin()
        mixin.MAX_FILE_SIZE = 10  # 10 bytes
        test_file = tmp_path / "large.pdf"
        test_file.write_bytes(b"x" * 100)
        with pytest.raises(MessageSendException) as exc_info:
            mixin.send_file("chat_id", str(test_file))
        assert "过大" in str(exc_info.value)


# ============================================================
# ChatProviderFactory 测试
# ============================================================


class TestChatProviderFactory:
    """ChatProviderFactory 测试"""

    def test_register_and_get(self) -> None:
        from apps.automation.services.chat.factory import ChatProviderFactory
        from apps.automation.services.chat.base import ChatProvider
        from apps.core.models.enums import ChatPlatform

        class MockProvider(ChatProvider):
            @property
            def platform(self):
                return ChatPlatform.FEISHU

            def is_available(self):
                return True

            def create_chat(self, chat_name, owner_id=None):
                pass

            def send_message(self, chat_id, content):
                pass

            def send_file(self, chat_id, file_path):
                pass

            def get_chat_info(self, chat_id):
                pass

        ChatProviderFactory.clear_cache()
        ChatProviderFactory.register(ChatPlatform.FEISHU, MockProvider)
        provider = ChatProviderFactory.get_provider(ChatPlatform.FEISHU)
        assert provider.platform == ChatPlatform.FEISHU
        ChatProviderFactory.unregister(ChatPlatform.FEISHU)

    def test_register_non_chat_provider_raises(self) -> None:
        from apps.automation.services.chat.factory import ChatProviderFactory
        from apps.core.models.enums import ChatPlatform

        with pytest.raises(TypeError):
            ChatProviderFactory.register(ChatPlatform.FEISHU, object)

    def test_get_unregistered_platform_raises(self) -> None:
        from apps.automation.services.chat.factory import ChatProviderFactory
        from apps.core.models.enums import ChatPlatform
        from apps.core.exceptions import UnsupportedPlatformException

        ChatProviderFactory.clear_cache()
        ChatProviderFactory.unregister(ChatPlatform.WECHAT_WORK)
        with pytest.raises(UnsupportedPlatformException):
            ChatProviderFactory.get_provider(ChatPlatform.WECHAT_WORK)

    def test_is_platform_registered(self) -> None:
        from apps.automation.services.chat.factory import ChatProviderFactory
        from apps.core.models.enums import ChatPlatform

        ChatProviderFactory.clear_cache()
        # After clearing, nothing should be registered
        assert ChatProviderFactory.is_platform_registered(ChatPlatform.FEISHU) is False

    def test_clear_cache(self) -> None:
        from apps.automation.services.chat.factory import ChatProviderFactory

        ChatProviderFactory.clear_cache()
        assert ChatProviderFactory._instances == {}

    def test_unregister_nonexistent(self) -> None:
        from apps.automation.services.chat.factory import ChatProviderFactory
        from apps.core.models.enums import ChatPlatform

        # Use a platform that's definitely not registered
        ChatProviderFactory.unregister(ChatPlatform.DINGTALK)  # ensure clean state
        result = ChatProviderFactory.unregister(ChatPlatform.DINGTALK)
        assert result is False

    def test_get_registered_platforms(self) -> None:
        from apps.automation.services.chat.factory import ChatProviderFactory

        ChatProviderFactory.clear_cache()
        platforms = ChatProviderFactory.get_registered_platforms()
        assert isinstance(platforms, list)


# ============================================================
# RetryConfig 测试
# ============================================================


class TestRetryConfig:
    """RetryConfig 测试"""

    def test_error_type_enum_values(self) -> None:
        from apps.automation.services.chat.retry_config import RetryErrorType

        assert RetryErrorType.NETWORK_ERROR.value == "network_error"
        assert RetryErrorType.PERMISSION_ERROR.value == "permission_error"

    def test_retry_strategy_enum(self) -> None:
        from apps.automation.services.chat.retry_config import RetryStrategy

        assert RetryStrategy.EXPONENTIAL_BACKOFF.value == "exponential_backoff"
        assert RetryStrategy.NO_RETRY.value == "no_retry"

    def test_retry_attempt_to_dict(self) -> None:
        from apps.automation.services.chat.retry_config import RetryAttempt, RetryErrorType
        from datetime import datetime

        attempt = RetryAttempt(
            attempt_number=1,
            timestamp=datetime(2025, 1, 1),
            error_type=RetryErrorType.NETWORK_ERROR,
            error_message="test error",
            delay_seconds=1.0,
            success=False,
        )
        d = attempt.to_dict()
        assert d["attempt_number"] == 1
        assert d["error_type"] == "network_error"
        assert d["success"] is False

    def test_error_strategy_config(self) -> None:
        from apps.automation.services.chat.retry_config import ErrorStrategyConfig, RetryStrategy

        cfg = ErrorStrategyConfig(
            strategy=RetryStrategy.EXPONENTIAL_BACKOFF,
            max_retries=3,
            base_delay=1.0,
            backoff_factor=2.0,
            max_delay=60.0,
        )
        assert cfg.max_retries == 3
        assert cfg.base_delay == 1.0
