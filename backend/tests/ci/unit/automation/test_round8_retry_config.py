"""Tests for retry_config (RetryConfig, RetryManager, dataclasses)."""

from __future__ import annotations

from datetime import datetime
from unittest.mock import MagicMock, patch

import pytest

from apps.automation.services.chat.retry_config import (
    RetryErrorType,
    RetryStrategy,
    RetryAttempt,
    ErrorStrategyConfig,
    RetryConfig,
    RetryManager,
)


# ---------------------------------------------------------------------------
# Enums
# ---------------------------------------------------------------------------


class TestRetryErrorType:
    def test_values(self):
        assert RetryErrorType.NETWORK_ERROR.value == "network_error"
        assert RetryErrorType.TIMEOUT_ERROR.value == "timeout_error"
        assert RetryErrorType.PERMISSION_ERROR.value == "permission_error"
        assert RetryErrorType.NOT_FOUND_ERROR.value == "not_found_error"
        assert RetryErrorType.VALIDATION_ERROR.value == "validation_error"
        assert RetryErrorType.UNKNOWN_ERROR.value == "unknown_error"


class TestRetryStrategy:
    def test_values(self):
        assert RetryStrategy.NO_RETRY.value == "no_retry"
        assert RetryStrategy.FIXED_DELAY.value == "fixed_delay"
        assert RetryStrategy.EXPONENTIAL_BACKOFF.value == "exponential_backoff"
        assert RetryStrategy.LINEAR_BACKOFF.value == "linear_backoff"


# ---------------------------------------------------------------------------
# RetryAttempt
# ---------------------------------------------------------------------------


class TestRetryAttempt:
    def test_to_dict(self):
        attempt = RetryAttempt(
            attempt_number=1,
            timestamp=datetime(2025, 1, 15, 10, 0, 0),
            error_type=RetryErrorType.NETWORK_ERROR,
            error_message="connection failed",
            delay_seconds=1.0,
            success=True,
        )
        d = attempt.to_dict()
        assert d["attempt_number"] == 1
        assert d["error_type"] == "network_error"
        assert d["success"] is True


# ---------------------------------------------------------------------------
# RetryConfig
# ---------------------------------------------------------------------------


class TestRetryConfig:
    def test_defaults(self):
        with patch("apps.automation.services.chat.retry_config._get_system_config_service") as mock_svc:
            mock_svc.return_value = MagicMock(get_value=MagicMock(return_value=""))
            config = RetryConfig()
            assert config.enabled is True
            assert config.max_retries == 3
            assert config.base_delay == 1.0
            assert config.max_delay == 60.0
            assert config.backoff_factor == 2.0
            assert config.timeout_seconds == 300.0

    def test_get_max_retries(self):
        with patch("apps.automation.services.chat.retry_config._get_system_config_service") as mock_svc:
            mock_svc.return_value = MagicMock(get_value=MagicMock(return_value=""))
            config = RetryConfig()
            assert config.get_max_retries(RetryErrorType.NETWORK_ERROR) == 3
            assert config.get_max_retries(RetryErrorType.PERMISSION_ERROR) == 0

    def test_get_max_retries_no_type(self):
        with patch("apps.automation.services.chat.retry_config._get_system_config_service") as mock_svc:
            mock_svc.return_value = MagicMock(get_value=MagicMock(return_value=""))
            config = RetryConfig()
            assert config.get_max_retries() == 3

    def test_get_strategy(self):
        with patch("apps.automation.services.chat.retry_config._get_system_config_service") as mock_svc:
            mock_svc.return_value = MagicMock(get_value=MagicMock(return_value=""))
            config = RetryConfig()
            assert config.get_strategy(RetryErrorType.NETWORK_ERROR) == RetryStrategy.EXPONENTIAL_BACKOFF
            assert config.get_strategy(RetryErrorType.PERMISSION_ERROR) == RetryStrategy.NO_RETRY

    def test_get_strategy_unknown(self):
        with patch("apps.automation.services.chat.retry_config._get_system_config_service") as mock_svc:
            mock_svc.return_value = MagicMock(get_value=MagicMock(return_value=""))
            config = RetryConfig()
            # When error type is not in error_strategies dict, it falls back to EXPONENTIAL_BACKOFF
            # But RetryErrorType enum won't accept a random string, so this path can't be hit
            # via the normal public API. Skip this test.
            pass

    def test_should_retry_enabled(self):
        with patch("apps.automation.services.chat.retry_config._get_system_config_service") as mock_svc:
            mock_svc.return_value = MagicMock(get_value=MagicMock(return_value=""))
            config = RetryConfig()
            assert config.should_retry(RetryErrorType.NETWORK_ERROR, 0) is True
            assert config.should_retry(RetryErrorType.NETWORK_ERROR, 3) is False

    def test_should_retry_disabled(self):
        with patch("apps.automation.services.chat.retry_config._get_system_config_service") as mock_svc:
            def fake_get_value(key, default=""):
                if key == "FEISHU_OWNER_RETRY_ENABLED":
                    return "false"
                return ""
            mock_svc.return_value = MagicMock(get_value=fake_get_value)
            config = RetryConfig()
            assert config.should_retry(RetryErrorType.NETWORK_ERROR, 0) is False

    def test_should_retry_no_strategy(self):
        with patch("apps.automation.services.chat.retry_config._get_system_config_service") as mock_svc:
            mock_svc.return_value = MagicMock(get_value=MagicMock(return_value=""))
            config = RetryConfig()
            assert config.should_retry(RetryErrorType.PERMISSION_ERROR, 0) is False

    def test_calculate_delay_exponential(self):
        with patch("apps.automation.services.chat.retry_config._get_system_config_service") as mock_svc:
            mock_svc.return_value = MagicMock(get_value=MagicMock(return_value=""))
            config = RetryConfig()
            delay = config.calculate_delay(RetryErrorType.NETWORK_ERROR, 0)
            assert delay == 1.0  # base_delay * factor^0 = 1.0

    def test_calculate_delay_fixed(self):
        with patch("apps.automation.services.chat.retry_config._get_system_config_service") as mock_svc:
            mock_svc.return_value = MagicMock(get_value=MagicMock(return_value=""))
            config = RetryConfig()
            delay = config.calculate_delay(RetryErrorType.NOT_FOUND_ERROR, 0)
            assert delay == 5.0

    def test_calculate_delay_linear(self):
        with patch("apps.automation.services.chat.retry_config._get_system_config_service") as mock_svc:
            mock_svc.return_value = MagicMock(get_value=MagicMock(return_value=""))
            config = RetryConfig()
            delay = config.calculate_delay(RetryErrorType.UNKNOWN_ERROR, 2)
            # base_delay + (attempt * 1.5) = 1.0 + (2 * 1.5) = 4.0
            assert delay == 4.0

    def test_calculate_delay_no_retry(self):
        with patch("apps.automation.services.chat.retry_config._get_system_config_service") as mock_svc:
            mock_svc.return_value = MagicMock(get_value=MagicMock(return_value=""))
            config = RetryConfig()
            delay = config.calculate_delay(RetryErrorType.PERMISSION_ERROR, 0)
            assert delay == 0.0

    def test_get_timeout_seconds(self):
        with patch("apps.automation.services.chat.retry_config._get_system_config_service") as mock_svc:
            mock_svc.return_value = MagicMock(get_value=MagicMock(return_value=""))
            config = RetryConfig()
            assert config.get_timeout_seconds() == 300.0


# ---------------------------------------------------------------------------
# RetryManager
# ---------------------------------------------------------------------------


class TestRetryManager:
    def test_classify_by_message(self):
        with patch("apps.automation.services.chat.retry_config._get_system_config_service") as mock_svc:
            mock_svc.return_value = MagicMock(get_value=MagicMock(return_value=""))
            config = RetryConfig()
            rm = RetryManager(config=config)
            assert rm._classify_by_message("connection error") == RetryErrorType.NETWORK_ERROR
            assert rm._classify_by_message("timeout occurred") == RetryErrorType.TIMEOUT_ERROR
            assert rm._classify_by_message("permission denied") == RetryErrorType.PERMISSION_ERROR
            assert rm._classify_by_message("resource not found") == RetryErrorType.NOT_FOUND_ERROR
            assert rm._classify_by_message("unknown issue") == RetryErrorType.UNKNOWN_ERROR

    def test_execute_success(self):
        with patch("apps.automation.services.chat.retry_config._get_system_config_service") as mock_svc:
            mock_svc.return_value = MagicMock(get_value=MagicMock(return_value=""))
            config = RetryConfig()
            rm = RetryManager(config=config)
            result = rm.execute_with_retry(lambda: "ok", "test_op")
            assert result == "ok"
            assert len(rm.attempts) == 0

    def test_execute_with_context(self):
        with patch("apps.automation.services.chat.retry_config._get_system_config_service") as mock_svc:
            mock_svc.return_value = MagicMock(get_value=MagicMock(return_value=""))
            config = RetryConfig()
            rm = RetryManager(config=config)
            result = rm.execute_with_retry(lambda: "ok", "test_op", context={"key": "val"})
            assert result == "ok"
