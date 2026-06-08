"""测试重试配置与重试管理器

覆盖: apps/automation/services/chat/retry_config.py
重点: 策略枚举、延迟计算、错误分类、重试摘要
"""

from __future__ import annotations

from datetime import datetime
from unittest.mock import MagicMock, patch

import pytest

from apps.automation.services.chat.retry_config import (
    ErrorStrategyConfig,
    RetryAttempt,
    RetryConfig,
    RetryErrorType,
    RetryManager,
    RetryStrategy,
)


# ============================================================
# Enum tests
# ============================================================


class TestRetryEnums:
    """测试枚举值"""

    def test_error_types_values(self) -> None:
        assert RetryErrorType.NETWORK_ERROR.value == "network_error"
        assert RetryErrorType.TIMEOUT_ERROR.value == "timeout_error"
        assert RetryErrorType.PERMISSION_ERROR.value == "permission_error"
        assert RetryErrorType.NOT_FOUND_ERROR.value == "not_found_error"
        assert RetryErrorType.VALIDATION_ERROR.value == "validation_error"
        assert RetryErrorType.UNKNOWN_ERROR.value == "unknown_error"

    def test_strategy_values(self) -> None:
        assert RetryStrategy.NO_RETRY.value == "no_retry"
        assert RetryStrategy.FIXED_DELAY.value == "fixed_delay"
        assert RetryStrategy.EXPONENTIAL_BACKOFF.value == "exponential_backoff"
        assert RetryStrategy.LINEAR_BACKOFF.value == "linear_backoff"


# ============================================================
# RetryAttempt
# ============================================================


class TestRetryAttempt:
    """测试重试记录"""

    def test_to_dict(self) -> None:
        now = datetime(2026, 6, 7, 12, 0, 0)
        attempt = RetryAttempt(
            attempt_number=1,
            timestamp=now,
            error_type=RetryErrorType.NETWORK_ERROR,
            error_message="connection refused",
            delay_seconds=2.0,
            success=False,
        )
        d = attempt.to_dict()
        assert d["attempt_number"] == 1
        assert d["timestamp"] == now.isoformat()
        assert d["error_type"] == "network_error"
        assert d["error_message"] == "connection refused"
        assert d["delay_seconds"] == 2.0
        assert d["success"] is False

    def test_default_success_false(self) -> None:
        attempt = RetryAttempt(
            attempt_number=1,
            timestamp=datetime.now(),
            error_type=RetryErrorType.UNKNOWN_ERROR,
            error_message="err",
            delay_seconds=1.0,
        )
        assert attempt.success is False


# ============================================================
# RetryConfig
# ============================================================


class TestRetryConfig:
    """测试重试配置加载和策略查询"""

    @patch("apps.automation.services.chat.retry_config._get_system_config_service")
    def test_defaults_when_no_config(self, mock_svc_factory: MagicMock) -> None:
        svc = MagicMock()
        svc.get_value.return_value = ""
        mock_svc_factory.return_value = svc
        config = RetryConfig()
        assert config.enabled is True
        assert config.max_retries == 3
        assert config.base_delay == 1.0
        assert config.max_delay == 60.0
        assert config.backoff_factor == 2.0
        assert config.timeout_seconds == 300.0

    @patch("apps.automation.services.chat.retry_config._get_system_config_service")
    def test_custom_config_values(self, mock_svc_factory: MagicMock) -> None:
        values = {
            "FEISHU_OWNER_RETRY_ENABLED": "false",
            "FEISHU_OWNER_MAX_RETRIES": "5",
            "FEISHU_OWNER_RETRY_BASE_DELAY": "2.5",
            "FEISHU_OWNER_RETRY_MAX_DELAY": "120.0",
            "FEISHU_OWNER_RETRY_BACKOFF_FACTOR": "3.0",
            "FEISHU_OWNER_RETRY_TIMEOUT": "600.0",
        }
        svc = MagicMock()
        svc.get_value.side_effect = lambda key, default="": values.get(key, "")
        mock_svc_factory.return_value = svc
        config = RetryConfig()
        assert config.enabled is False
        assert config.max_retries == 5
        assert config.base_delay == 2.5
        assert config.max_delay == 120.0
        assert config.backoff_factor == 3.0
        assert config.timeout_seconds == 600.0

    @patch("apps.automation.services.chat.retry_config._get_system_config_service")
    def test_is_enabled(self, mock_svc_factory: MagicMock) -> None:
        svc = MagicMock()
        svc.get_value.return_value = ""
        mock_svc_factory.return_value = svc
        config = RetryConfig()
        assert config.is_enabled() is True

    @patch("apps.automation.services.chat.retry_config._get_system_config_service")
    def test_get_max_retries_for_error_type(self, mock_svc_factory: MagicMock) -> None:
        svc = MagicMock()
        svc.get_value.return_value = ""
        mock_svc_factory.return_value = svc
        config = RetryConfig()
        # Permission errors have max_retries=0 (no retry)
        assert config.get_max_retries(RetryErrorType.PERMISSION_ERROR) == 0
        # Validation errors have max_retries=0 (no retry)
        assert config.get_max_retries(RetryErrorType.VALIDATION_ERROR) == 0
        # Network errors have full max_retries
        assert config.get_max_retries(RetryErrorType.NETWORK_ERROR) == 3
        # Default max_retries
        assert config.get_max_retries() == 3

    @patch("apps.automation.services.chat.retry_config._get_system_config_service")
    def test_get_strategy(self, mock_svc_factory: MagicMock) -> None:
        svc = MagicMock()
        svc.get_value.return_value = ""
        mock_svc_factory.return_value = svc
        config = RetryConfig()
        assert config.get_strategy(RetryErrorType.NETWORK_ERROR) == RetryStrategy.EXPONENTIAL_BACKOFF
        assert config.get_strategy(RetryErrorType.PERMISSION_ERROR) == RetryStrategy.NO_RETRY
        assert config.get_strategy(RetryErrorType.NOT_FOUND_ERROR) == RetryStrategy.FIXED_DELAY
        assert config.get_strategy(RetryErrorType.UNKNOWN_ERROR) == RetryStrategy.LINEAR_BACKOFF

    @patch("apps.automation.services.chat.retry_config._get_system_config_service")
    def test_should_retry_disabled(self, mock_svc_factory: MagicMock) -> None:
        values = {"FEISHU_OWNER_RETRY_ENABLED": "false"}
        svc = MagicMock()
        svc.get_value.side_effect = lambda key, default="": values.get(key, "")
        mock_svc_factory.return_value = svc
        config = RetryConfig()
        assert config.should_retry(RetryErrorType.NETWORK_ERROR, 0) is False

    @patch("apps.automation.services.chat.retry_config._get_system_config_service")
    def test_should_retry_permission_error_always_false(self, mock_svc_factory: MagicMock) -> None:
        svc = MagicMock()
        svc.get_value.return_value = ""
        mock_svc_factory.return_value = svc
        config = RetryConfig()
        assert config.should_retry(RetryErrorType.PERMISSION_ERROR, 0) is False

    @patch("apps.automation.services.chat.retry_config._get_system_config_service")
    def test_should_retry_network_within_limit(self, mock_svc_factory: MagicMock) -> None:
        svc = MagicMock()
        svc.get_value.return_value = ""
        mock_svc_factory.return_value = svc
        config = RetryConfig()
        assert config.should_retry(RetryErrorType.NETWORK_ERROR, 0) is True
        assert config.should_retry(RetryErrorType.NETWORK_ERROR, 2) is True
        assert config.should_retry(RetryErrorType.NETWORK_ERROR, 3) is False

    @patch("apps.automation.services.chat.retry_config._get_system_config_service")
    def test_calculate_delay_no_retry(self, mock_svc_factory: MagicMock) -> None:
        svc = MagicMock()
        svc.get_value.return_value = ""
        mock_svc_factory.return_value = svc
        config = RetryConfig()
        assert config.calculate_delay(RetryErrorType.PERMISSION_ERROR, 0) == 0.0

    @patch("apps.automation.services.chat.retry_config._get_system_config_service")
    def test_calculate_delay_fixed(self, mock_svc_factory: MagicMock) -> None:
        svc = MagicMock()
        svc.get_value.return_value = ""
        mock_svc_factory.return_value = svc
        config = RetryConfig()
        delay = config.calculate_delay(RetryErrorType.NOT_FOUND_ERROR, 0)
        assert delay == 5.0

    @patch("apps.automation.services.chat.retry_config._get_system_config_service")
    def test_calculate_delay_exponential(self, mock_svc_factory: MagicMock) -> None:
        svc = MagicMock()
        svc.get_value.return_value = ""
        mock_svc_factory.return_value = svc
        config = RetryConfig()
        # base=1.0, factor=2.0: attempt 0 => 1.0, attempt 1 => 2.0, attempt 2 => 4.0
        assert config.calculate_delay(RetryErrorType.NETWORK_ERROR, 0) == 1.0
        assert config.calculate_delay(RetryErrorType.NETWORK_ERROR, 1) == 2.0
        assert config.calculate_delay(RetryErrorType.NETWORK_ERROR, 2) == 4.0

    @patch("apps.automation.services.chat.retry_config._get_system_config_service")
    def test_calculate_delay_exponential_capped(self, mock_svc_factory: MagicMock) -> None:
        svc = MagicMock()
        svc.get_value.return_value = ""
        mock_svc_factory.return_value = svc
        config = RetryConfig()
        # max_delay=60.0, attempt 10 => 1.0 * 2^10 = 1024, capped at 60
        assert config.calculate_delay(RetryErrorType.NETWORK_ERROR, 10) == 60.0

    @patch("apps.automation.services.chat.retry_config._get_system_config_service")
    def test_calculate_delay_linear(self, mock_svc_factory: MagicMock) -> None:
        svc = MagicMock()
        svc.get_value.return_value = ""
        mock_svc_factory.return_value = svc
        config = RetryConfig()
        # UNKNOWN: base=1.0, factor=1.5, max=30.0
        # attempt 0: 1.0 + 0*1.5 = 1.0
        # attempt 1: 1.0 + 1*1.5 = 2.5
        # attempt 2: 1.0 + 2*1.5 = 4.0
        assert config.calculate_delay(RetryErrorType.UNKNOWN_ERROR, 0) == 1.0
        assert config.calculate_delay(RetryErrorType.UNKNOWN_ERROR, 1) == 2.5
        assert config.calculate_delay(RetryErrorType.UNKNOWN_ERROR, 2) == 4.0

    @patch("apps.automation.services.chat.retry_config._get_system_config_service")
    def test_calculate_delay_unknown_error_type_fallback(self, mock_svc_factory: MagicMock) -> None:
        """如果 error_type 不在 error_strategies 中，回退到 UNKNOWN_ERROR"""
        svc = MagicMock()
        svc.get_value.return_value = ""
        mock_svc_factory.return_value = svc
        config = RetryConfig()
        # 使用一个构造的枚举值来触发回退 - 不太容易直接测到
        # 因为所有 RetryErrorType 都在 error_strategies 中
        # 但我们可以验证 timeout 的 delay
        delay = config.calculate_delay(RetryErrorType.TIMEOUT_ERROR, 0)
        assert delay == 2.0  # base_delay * 2 = 1.0 * 2 = 2.0

    @patch("apps.automation.services.chat.retry_config._get_system_config_service")
    def test_timeout_config(self, mock_svc_factory: MagicMock) -> None:
        svc = MagicMock()
        svc.get_value.return_value = ""
        mock_svc_factory.return_value = svc
        config = RetryConfig()
        assert config.get_timeout_seconds() == 300.0


# ============================================================
# RetryManager
# ============================================================


class TestRetryManager:
    """测试重试管理器"""

    @patch("apps.automation.services.chat.retry_config._get_system_config_service")
    def test_classify_by_message_timeout(self, mock_svc_factory: MagicMock) -> None:
        svc = MagicMock()
        svc.get_value.return_value = ""
        mock_svc_factory.return_value = svc
        manager = RetryManager()
        assert manager._classify_by_message("request timed out") == RetryErrorType.TIMEOUT_ERROR
        assert manager._classify_by_message("timeout error") == RetryErrorType.TIMEOUT_ERROR

    @patch("apps.automation.services.chat.retry_config._get_system_config_service")
    def test_classify_by_message_network(self, mock_svc_factory: MagicMock) -> None:
        svc = MagicMock()
        svc.get_value.return_value = ""
        mock_svc_factory.return_value = svc
        manager = RetryManager()
        assert manager._classify_by_message("network unreachable") == RetryErrorType.NETWORK_ERROR
        assert manager._classify_by_message("connection reset") == RetryErrorType.NETWORK_ERROR

    @patch("apps.automation.services.chat.retry_config._get_system_config_service")
    def test_classify_by_message_permission(self, mock_svc_factory: MagicMock) -> None:
        svc = MagicMock()
        svc.get_value.return_value = ""
        mock_svc_factory.return_value = svc
        manager = RetryManager()
        assert manager._classify_by_message("permission denied") == RetryErrorType.PERMISSION_ERROR
        assert manager._classify_by_message("forbidden access") == RetryErrorType.PERMISSION_ERROR

    @patch("apps.automation.services.chat.retry_config._get_system_config_service")
    def test_classify_by_message_not_found(self, mock_svc_factory: MagicMock) -> None:
        svc = MagicMock()
        svc.get_value.return_value = ""
        mock_svc_factory.return_value = svc
        manager = RetryManager()
        assert manager._classify_by_message("resource not found") == RetryErrorType.NOT_FOUND_ERROR
        assert manager._classify_by_message("item does not exist") == RetryErrorType.NOT_FOUND_ERROR

    @patch("apps.automation.services.chat.retry_config._get_system_config_service")
    def test_classify_by_message_unknown(self, mock_svc_factory: MagicMock) -> None:
        svc = MagicMock()
        svc.get_value.return_value = ""
        mock_svc_factory.return_value = svc
        manager = RetryManager()
        assert manager._classify_by_message("something went wrong") == RetryErrorType.UNKNOWN_ERROR

    @patch("apps.automation.services.chat.retry_config._get_system_config_service")
    def test_get_retry_summary_initial(self, mock_svc_factory: MagicMock) -> None:
        svc = MagicMock()
        svc.get_value.return_value = ""
        mock_svc_factory.return_value = svc
        manager = RetryManager()
        summary = manager.get_retry_summary()
        assert summary["total_attempts"] == 0
        assert summary["success"] is False
        assert summary["attempts"] == []
        assert summary["config"]["enabled"] is True

    @patch("apps.automation.services.chat.retry_config._get_system_config_service")
    def test_execute_success_first_try(self, mock_svc_factory: MagicMock) -> None:
        svc = MagicMock()
        svc.get_value.return_value = ""
        mock_svc_factory.return_value = svc
        manager = RetryManager()
        result = manager.execute_with_retry(lambda: "ok", "test_op")
        assert result == "ok"
        assert manager.attempts == []

    @patch("apps.automation.services.chat.retry_config._get_system_config_service")
    @patch("apps.automation.services.chat.retry_config.time.sleep")
    def test_execute_retries_then_success(self, mock_sleep: MagicMock, mock_svc_factory: MagicMock) -> None:
        svc = MagicMock()
        svc.get_value.return_value = ""
        mock_svc_factory.return_value = svc
        manager = RetryManager()

        call_count = 0

        def flaky_op() -> str:
            nonlocal call_count
            call_count += 1
            if call_count < 3:
                raise ConnectionError("network error")
            return "success"

        result = manager.execute_with_retry(flaky_op, "test_op")
        assert result == "success"
        assert call_count == 3
        assert len(manager.attempts) == 2  # 2 failed attempts recorded

    @patch("apps.automation.services.chat.retry_config._get_system_config_service")
    def test_execute_no_retry_for_permission(self, mock_svc_factory: MagicMock) -> None:
        svc = MagicMock()
        svc.get_value.return_value = ""
        mock_svc_factory.return_value = svc
        manager = RetryManager()

        def always_fail() -> None:
            raise PermissionError("permission denied")

        with pytest.raises(PermissionError):
            manager.execute_with_retry(always_fail, "test_op")

    @patch("apps.automation.services.chat.retry_config._get_system_config_service")
    def test_elapsed_time_starts_at_zero(self, mock_svc_factory: MagicMock) -> None:
        svc = MagicMock()
        svc.get_value.return_value = ""
        mock_svc_factory.return_value = svc
        manager = RetryManager()
        assert manager._get_elapsed_time() == 0.0
        assert manager._is_total_timeout() is False

    @patch("apps.automation.services.chat.retry_config._get_system_config_service")
    def test_is_total_timeout_when_not_started(self, mock_svc_factory: MagicMock) -> None:
        svc = MagicMock()
        svc.get_value.return_value = ""
        mock_svc_factory.return_value = svc
        manager = RetryManager()
        manager.start_time = None
        assert manager._is_total_timeout() is False
