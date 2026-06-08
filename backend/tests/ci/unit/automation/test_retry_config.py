"""重试配置和管理器测试。"""

from __future__ import annotations

from datetime import datetime
from unittest.mock import MagicMock, patch

from apps.automation.services.chat.retry_config import (
    RetryErrorType,
    RetryStrategy,
    RetryAttempt,
    ErrorStrategyConfig,
    RetryConfig,
    RetryManager,
)


class TestRetryErrorType:
    """RetryErrorType 枚举测试。"""

    def test_values(self) -> None:
        assert RetryErrorType.NETWORK_ERROR.value == "network_error"
        assert RetryErrorType.TIMEOUT_ERROR.value == "timeout_error"
        assert RetryErrorType.PERMISSION_ERROR.value == "permission_error"
        assert RetryErrorType.NOT_FOUND_ERROR.value == "not_found_error"
        assert RetryErrorType.VALIDATION_ERROR.value == "validation_error"
        assert RetryErrorType.UNKNOWN_ERROR.value == "unknown_error"


class TestRetryStrategy:
    """RetryStrategy 枚举测试。"""

    def test_values(self) -> None:
        assert RetryStrategy.NO_RETRY.value == "no_retry"
        assert RetryStrategy.FIXED_DELAY.value == "fixed_delay"
        assert RetryStrategy.EXPONENTIAL_BACKOFF.value == "exponential_backoff"
        assert RetryStrategy.LINEAR_BACKOFF.value == "linear_backoff"


class TestRetryAttempt:
    """RetryAttempt 数据类测试。"""

    def test_creation(self) -> None:
        attempt = RetryAttempt(
            attempt_number=1,
            timestamp=datetime.now(),
            error_type=RetryErrorType.NETWORK_ERROR,
            error_message="连接超时",
            delay_seconds=2.0,
            success=False,
        )
        assert attempt.attempt_number == 1
        assert attempt.error_type == RetryErrorType.NETWORK_ERROR
        assert attempt.success is False

    def test_to_dict(self) -> None:
        attempt = RetryAttempt(
            attempt_number=1,
            timestamp=datetime(2025, 1, 1, 12, 0, 0),
            error_type=RetryErrorType.TIMEOUT_ERROR,
            error_message="超时",
            delay_seconds=5.0,
        )
        d = attempt.to_dict()
        assert d["attempt_number"] == 1
        assert d["error_type"] == "timeout_error"
        assert d["delay_seconds"] == 5.0
        assert d["success"] is False


class TestErrorStrategyConfig:
    """ErrorStrategyConfig 数据类测试。"""

    def test_creation(self) -> None:
        config = ErrorStrategyConfig(
            strategy=RetryStrategy.EXPONENTIAL_BACKOFF,
            max_retries=3,
            base_delay=1.0,
            backoff_factor=2.0,
            max_delay=60.0,
        )
        assert config.strategy == RetryStrategy.EXPONENTIAL_BACKOFF
        assert config.max_retries == 3


class TestRetryManager:
    """RetryManager 测试（不触发实际重试）。"""

    def test_classify_by_message_timeout(self) -> None:
        manager = RetryManager.__new__(RetryManager)
        manager.attempts = []
        manager.start_time = None
        result = manager._classify_by_message("request timed out")
        assert result == RetryErrorType.TIMEOUT_ERROR

    def test_classify_by_message_network(self) -> None:
        manager = RetryManager.__new__(RetryManager)
        manager.attempts = []
        manager.start_time = None
        result = manager._classify_by_message("network error occurred")
        assert result == RetryErrorType.NETWORK_ERROR

    def test_classify_by_message_permission(self) -> None:
        manager = RetryManager.__new__(RetryManager)
        manager.attempts = []
        manager.start_time = None
        result = manager._classify_by_message("permission denied")
        assert result == RetryErrorType.PERMISSION_ERROR

    def test_classify_by_message_not_found(self) -> None:
        manager = RetryManager.__new__(RetryManager)
        manager.attempts = []
        manager.start_time = None
        result = manager._classify_by_message("resource not found")
        assert result == RetryErrorType.NOT_FOUND_ERROR

    def test_classify_by_message_unknown(self) -> None:
        manager = RetryManager.__new__(RetryManager)
        manager.attempts = []
        manager.start_time = None
        result = manager._classify_by_message("some random error")
        assert result == RetryErrorType.UNKNOWN_ERROR

    def test_get_retry_summary_empty(self) -> None:
        manager = RetryManager.__new__(RetryManager)
        manager.attempts = []
        manager.start_time = None
        manager.config = MagicMock()
        manager.config.enabled = True
        manager.config.max_retries = 3
        manager.config.timeout_seconds = 300.0
        summary = manager.get_retry_summary()
        assert summary["total_attempts"] == 0
        assert summary["success"] is False

    def test_get_elapsed_time_no_start(self) -> None:
        manager = RetryManager.__new__(RetryManager)
        manager.start_time = None
        assert manager._get_elapsed_time() == 0.0

    def test_is_total_timeout_no_start(self) -> None:
        manager = RetryManager.__new__(RetryManager)
        manager.start_time = None
        assert manager._is_total_timeout() is False
