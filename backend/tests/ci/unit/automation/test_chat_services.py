"""Chat 模块测试 - 工厂、重试配置。"""

from __future__ import annotations

from datetime import datetime
from unittest.mock import MagicMock, patch

import pytest

from apps.automation.services.chat.factory import ChatProviderFactory
from apps.automation.services.chat.retry_config import (
    ErrorStrategyConfig,
    RetryAttempt,
    RetryConfig,
    RetryErrorType,
    RetryManager,
    RetryStrategy,
)
from apps.core.models.enums import ChatPlatform


class TestRetryErrorType:
    """测试重试错误类型枚举。"""

    def test_all_values(self) -> None:
        assert RetryErrorType.NETWORK_ERROR.value == "network_error"
        assert RetryErrorType.TIMEOUT_ERROR.value == "timeout_error"
        assert RetryErrorType.PERMISSION_ERROR.value == "permission_error"
        assert RetryErrorType.NOT_FOUND_ERROR.value == "not_found_error"
        assert RetryErrorType.VALIDATION_ERROR.value == "validation_error"
        assert RetryErrorType.UNKNOWN_ERROR.value == "unknown_error"


class TestRetryStrategy:
    """测试重试策略枚举。"""

    def test_all_values(self) -> None:
        assert RetryStrategy.NO_RETRY.value == "no_retry"
        assert RetryStrategy.FIXED_DELAY.value == "fixed_delay"
        assert RetryStrategy.EXPONENTIAL_BACKOFF.value == "exponential_backoff"
        assert RetryStrategy.LINEAR_BACKOFF.value == "linear_backoff"


class TestRetryAttempt:
    """测试重试尝试记录。"""

    def test_to_dict(self) -> None:
        attempt = RetryAttempt(
            attempt_number=1,
            timestamp=datetime(2025, 1, 1, 12, 0, 0),
            error_type=RetryErrorType.NETWORK_ERROR,
            error_message="连接超时",
            delay_seconds=2.0,
            success=False,
        )
        d = attempt.to_dict()
        assert d["attempt_number"] == 1
        assert d["error_type"] == "network_error"
        assert d["error_message"] == "连接超时"
        assert d["delay_seconds"] == 2.0
        assert d["success"] is False

    def test_to_dict_success(self) -> None:
        attempt = RetryAttempt(
            attempt_number=2,
            timestamp=datetime(2025, 1, 1, 12, 0, 0),
            error_type=RetryErrorType.UNKNOWN_ERROR,
            error_message="",
            delay_seconds=0.0,
            success=True,
        )
        d = attempt.to_dict()
        assert d["success"] is True


class TestRetryConfig:
    """测试重试配置。"""

    @patch("apps.automation.services.chat.retry_config._get_system_config_service")
    def test_default_config(self, mock_get_svc: MagicMock) -> None:
        """测试默认配置加载。"""
        mock_svc = MagicMock()
        mock_svc.get_value.return_value = ""
        mock_get_svc.return_value = mock_svc

        config = RetryConfig()
        assert config.enabled is True
        assert config.max_retries == 3
        assert config.base_delay == 1.0
        assert config.max_delay == 60.0
        assert config.backoff_factor == 2.0
        assert config.timeout_seconds == 300.0

    @patch("apps.automation.services.chat.retry_config._get_system_config_service")
    def test_custom_config(self, mock_get_svc: MagicMock) -> None:
        """测试自定义配置。"""
        mock_svc = MagicMock()
        values = {
            "FEISHU_OWNER_RETRY_ENABLED": "false",
            "FEISHU_OWNER_MAX_RETRIES": "5",
            "FEISHU_OWNER_RETRY_BASE_DELAY": "2.0",
            "FEISHU_OWNER_RETRY_MAX_DELAY": "120.0",
            "FEISHU_OWNER_RETRY_BACKOFF_FACTOR": "3.0",
            "FEISHU_OWNER_RETRY_TIMEOUT": "600.0",
        }
        mock_svc.get_value.side_effect = lambda key, default="": values.get(key, default)
        mock_get_svc.return_value = mock_svc

        config = RetryConfig()
        assert config.enabled is False
        assert config.max_retries == 5
        assert config.base_delay == 2.0
        assert config.max_delay == 120.0
        assert config.backoff_factor == 3.0
        assert config.timeout_seconds == 600.0

    @patch("apps.automation.services.chat.retry_config._get_system_config_service")
    def test_is_enabled(self, mock_get_svc: MagicMock) -> None:
        mock_svc = MagicMock()
        mock_svc.get_value.return_value = ""
        mock_get_svc.return_value = mock_svc

        config = RetryConfig()
        assert config.is_enabled() is True

    @patch("apps.automation.services.chat.retry_config._get_system_config_service")
    def test_get_max_retries_by_error_type(self, mock_get_svc: MagicMock) -> None:
        mock_svc = MagicMock()
        mock_svc.get_value.return_value = ""
        mock_get_svc.return_value = mock_svc

        config = RetryConfig()
        assert config.get_max_retries(RetryErrorType.PERMISSION_ERROR) == 0
        assert config.get_max_retries(RetryErrorType.VALIDATION_ERROR) == 0
        assert config.get_max_retries(RetryErrorType.NETWORK_ERROR) == 3

    @patch("apps.automation.services.chat.retry_config._get_system_config_service")
    def test_get_strategy(self, mock_get_svc: MagicMock) -> None:
        mock_svc = MagicMock()
        mock_svc.get_value.return_value = ""
        mock_get_svc.return_value = mock_svc

        config = RetryConfig()
        assert config.get_strategy(RetryErrorType.PERMISSION_ERROR) == RetryStrategy.NO_RETRY
        assert config.get_strategy(RetryErrorType.NETWORK_ERROR) == RetryStrategy.EXPONENTIAL_BACKOFF
        assert config.get_strategy(RetryErrorType.NOT_FOUND_ERROR) == RetryStrategy.FIXED_DELAY
        assert config.get_strategy(RetryErrorType.UNKNOWN_ERROR) == RetryStrategy.LINEAR_BACKOFF

    @patch("apps.automation.services.chat.retry_config._get_system_config_service")
    def test_should_retry_disabled(self, mock_get_svc: MagicMock) -> None:
        mock_svc = MagicMock()
        values = {"FEISHU_OWNER_RETRY_ENABLED": "false"}
        mock_svc.get_value.side_effect = lambda key, default="": values.get(key, default)
        mock_get_svc.return_value = mock_svc

        config = RetryConfig()
        assert config.should_retry(RetryErrorType.NETWORK_ERROR, 0) is False

    @patch("apps.automation.services.chat.retry_config._get_system_config_service")
    def test_should_retry_no_retry_strategy(self, mock_get_svc: MagicMock) -> None:
        mock_svc = MagicMock()
        mock_svc.get_value.return_value = ""
        mock_get_svc.return_value = mock_svc

        config = RetryConfig()
        assert config.should_retry(RetryErrorType.PERMISSION_ERROR, 0) is False

    @patch("apps.automation.services.chat.retry_config._get_system_config_service")
    def test_should_retry_exceeds_max(self, mock_get_svc: MagicMock) -> None:
        mock_svc = MagicMock()
        mock_svc.get_value.return_value = ""
        mock_get_svc.return_value = mock_svc

        config = RetryConfig()
        assert config.should_retry(RetryErrorType.NETWORK_ERROR, 3) is False

    @patch("apps.automation.services.chat.retry_config._get_system_config_service")
    def test_calculate_delay_exponential(self, mock_get_svc: MagicMock) -> None:
        mock_svc = MagicMock()
        mock_svc.get_value.return_value = ""
        mock_get_svc.return_value = mock_svc

        config = RetryConfig()
        # exponential: base * factor^attempt = 1.0 * 2.0^0 = 1.0
        assert config.calculate_delay(RetryErrorType.NETWORK_ERROR, 0) == 1.0
        # 1.0 * 2.0^1 = 2.0
        assert config.calculate_delay(RetryErrorType.NETWORK_ERROR, 1) == 2.0
        # 1.0 * 2.0^2 = 4.0
        assert config.calculate_delay(RetryErrorType.NETWORK_ERROR, 2) == 4.0

    @patch("apps.automation.services.chat.retry_config._get_system_config_service")
    def test_calculate_delay_fixed(self, mock_get_svc: MagicMock) -> None:
        mock_svc = MagicMock()
        mock_svc.get_value.return_value = ""
        mock_get_svc.return_value = mock_svc

        config = RetryConfig()
        # NOT_FOUND_ERROR: fixed_delay, base=5.0, max=5.0
        assert config.calculate_delay(RetryErrorType.NOT_FOUND_ERROR, 0) == 5.0
        assert config.calculate_delay(RetryErrorType.NOT_FOUND_ERROR, 5) == 5.0

    @patch("apps.automation.services.chat.retry_config._get_system_config_service")
    def test_calculate_delay_no_retry(self, mock_get_svc: MagicMock) -> None:
        mock_svc = MagicMock()
        mock_svc.get_value.return_value = ""
        mock_get_svc.return_value = mock_svc

        config = RetryConfig()
        assert config.calculate_delay(RetryErrorType.PERMISSION_ERROR, 0) == 0.0

    @patch("apps.automation.services.chat.retry_config._get_system_config_service")
    def test_calculate_delay_linear(self, mock_get_svc: MagicMock) -> None:
        mock_svc = MagicMock()
        mock_svc.get_value.return_value = ""
        mock_get_svc.return_value = mock_svc

        config = RetryConfig()
        # UNKNOWN_ERROR: linear_backoff, base=1.0, factor=1.5
        # delay = 1.0 + 0*1.5 = 1.0
        assert config.calculate_delay(RetryErrorType.UNKNOWN_ERROR, 0) == 1.0
        # delay = 1.0 + 1*1.5 = 2.5
        assert config.calculate_delay(RetryErrorType.UNKNOWN_ERROR, 1) == 2.5

    @patch("apps.automation.services.chat.retry_config._get_system_config_service")
    def test_get_timeout_seconds(self, mock_get_svc: MagicMock) -> None:
        mock_svc = MagicMock()
        mock_svc.get_value.return_value = ""
        mock_get_svc.return_value = mock_svc

        config = RetryConfig()
        assert config.get_timeout_seconds() == 300.0

    @patch("apps.automation.services.chat.retry_config._get_system_config_service")
    def test_error_strategies_populated(self, mock_get_svc: MagicMock) -> None:
        mock_svc = MagicMock()
        mock_svc.get_value.return_value = ""
        mock_get_svc.return_value = mock_svc

        config = RetryConfig()
        assert len(config.error_strategies) == 6
        for error_type in RetryErrorType:
            assert error_type in config.error_strategies


class TestRetryManager:
    """测试重试管理器。"""

    def _make_config(self) -> RetryConfig:
        with patch("apps.automation.services.chat.retry_config._get_system_config_service") as mock_get_svc:
            mock_svc = MagicMock()
            mock_svc.get_value.return_value = ""
            mock_get_svc.return_value = mock_svc
            return RetryConfig()

    def test_classify_error_timeout(self) -> None:
        manager = RetryManager(self._make_config())
        exc = Exception("connection timed out")
        assert manager.classify_error(exc) == RetryErrorType.TIMEOUT_ERROR

    def test_classify_error_network(self) -> None:
        manager = RetryManager(self._make_config())
        exc = Exception("network error occurred")
        assert manager.classify_error(exc) == RetryErrorType.NETWORK_ERROR

    def test_classify_error_permission(self) -> None:
        manager = RetryManager(self._make_config())
        exc = Exception("permission denied")
        assert manager.classify_error(exc) == RetryErrorType.PERMISSION_ERROR

    def test_classify_error_not_found(self) -> None:
        manager = RetryManager(self._make_config())
        exc = Exception("resource not found")
        assert manager.classify_error(exc) == RetryErrorType.NOT_FOUND_ERROR

    def test_classify_error_unknown(self) -> None:
        manager = RetryManager(self._make_config())
        exc = Exception("something went wrong")
        assert manager.classify_error(exc) == RetryErrorType.UNKNOWN_ERROR

    def test_execute_success_first_try(self) -> None:
        manager = RetryManager(self._make_config())
        result = manager.execute_with_retry(lambda: "ok", "test_op")
        assert result == "ok"
        assert len(manager.attempts) == 0

    def test_execute_success_after_retry(self) -> None:
        manager = RetryManager(self._make_config())
        call_count = 0

        def flaky_op() -> str:
            nonlocal call_count
            call_count += 1
            if call_count < 2:
                raise Exception("network error")
            return "ok"

        with patch("apps.automation.services.chat.retry_config.time.sleep"):
            result = manager.execute_with_retry(flaky_op, "test_op")
        assert result == "ok"
        assert call_count == 2

    def test_execute_failure_exhausted(self) -> None:
        manager = RetryManager(self._make_config())

        def always_fail() -> None:
            raise Exception("network error")

        with patch("apps.automation.services.chat.retry_config.time.sleep"):
            with pytest.raises(Exception, match="network error"):
                manager.execute_with_retry(always_fail, "test_op")

    def test_execute_no_retry_for_permission(self) -> None:
        manager = RetryManager(self._make_config())

        def permission_fail() -> None:
            raise Exception("permission denied")

        with pytest.raises(Exception, match="permission denied"):
            manager.execute_with_retry(permission_fail, "test_op")

    def test_get_retry_summary(self) -> None:
        manager = RetryManager(self._make_config())
        summary = manager.get_retry_summary()
        assert summary["total_attempts"] == 0
        assert summary["success"] is False
        assert summary["config"]["enabled"] is True

    def test_is_total_timeout_no_start(self) -> None:
        manager = RetryManager(self._make_config())
        assert manager._is_total_timeout() is False

    def test_get_elapsed_time_no_start(self) -> None:
        manager = RetryManager(self._make_config())
        assert manager._get_elapsed_time() == 0.0


class TestChatProviderFactory:
    """测试 ChatProviderFactory。"""

    def setup_method(self) -> None:
        ChatProviderFactory._providers.clear()
        ChatProviderFactory._instances.clear()

    def teardown_method(self) -> None:
        ChatProviderFactory._providers.clear()
        ChatProviderFactory._instances.clear()

    def test_register_provider(self) -> None:
        from apps.automation.services.chat.base import ChatProvider

        class MockProvider(ChatProvider):
            @property
            def platform(self) -> ChatPlatform:
                return ChatPlatform.FEISHU

            def create_chat(self, chat_name: str, owner_id: str | None = None) -> MagicMock:
                return MagicMock()

            def send_message(self, chat_id: str, content: object) -> MagicMock:
                return MagicMock()

            def send_file(self, chat_id: str, file_path: str) -> MagicMock:
                return MagicMock()

            def get_chat_info(self, chat_id: str) -> MagicMock:
                return MagicMock()

            def is_available(self) -> bool:
                return True

        ChatProviderFactory.register(ChatPlatform.FEISHU, MockProvider)
        assert ChatProviderFactory.is_platform_registered(ChatPlatform.FEISHU) is True

    def test_register_non_subclass_raises(self) -> None:
        with pytest.raises(TypeError, match="必须继承 ChatProvider"):
            ChatProviderFactory.register(ChatPlatform.FEISHU, object)  # type: ignore[arg-type]

    def test_get_unregistered_provider_raises(self) -> None:
        with pytest.raises(Exception):
            ChatProviderFactory.get_provider(ChatPlatform.FEISHU)

    def test_unregister_provider(self) -> None:
        from apps.automation.services.chat.base import ChatProvider

        class MockProvider(ChatProvider):
            @property
            def platform(self) -> ChatPlatform:
                return ChatPlatform.FEISHU

            def create_chat(self, chat_name: str, owner_id: str | None = None) -> MagicMock:
                return MagicMock()

            def send_message(self, chat_id: str, content: object) -> MagicMock:
                return MagicMock()

            def send_file(self, chat_id: str, file_path: str) -> MagicMock:
                return MagicMock()

            def get_chat_info(self, chat_id: str) -> MagicMock:
                return MagicMock()

            def is_available(self) -> bool:
                return True

        ChatProviderFactory.register(ChatPlatform.FEISHU, MockProvider)
        assert ChatProviderFactory.unregister(ChatPlatform.FEISHU) is True
        assert ChatProviderFactory.is_platform_registered(ChatPlatform.FEISHU) is False

    def test_unregister_nonexistent(self) -> None:
        assert ChatProviderFactory.unregister(ChatPlatform.FEISHU) is False

    def test_get_registered_platforms_empty(self) -> None:
        assert ChatProviderFactory.get_registered_platforms() == []

    def test_clear_cache(self) -> None:
        ChatProviderFactory._instances[ChatPlatform.FEISHU] = MagicMock()
        ChatProviderFactory.clear_cache()
        assert len(ChatProviderFactory._instances) == 0
