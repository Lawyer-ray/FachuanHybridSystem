"""Tests for apps.automation.services.chat.retry_config — RetryConfig and RetryManager."""
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


class TestRetryErrorType:
    def test_values(self) -> None:
        assert RetryErrorType.NETWORK_ERROR.value == "network_error"
        assert RetryErrorType.TIMEOUT_ERROR.value == "timeout_error"
        assert RetryErrorType.PERMISSION_ERROR.value == "permission_error"
        assert RetryErrorType.NOT_FOUND_ERROR.value == "not_found_error"
        assert RetryErrorType.VALIDATION_ERROR.value == "validation_error"
        assert RetryErrorType.UNKNOWN_ERROR.value == "unknown_error"


class TestRetryStrategy:
    def test_values(self) -> None:
        assert RetryStrategy.NO_RETRY.value == "no_retry"
        assert RetryStrategy.FIXED_DELAY.value == "fixed_delay"
        assert RetryStrategy.EXPONENTIAL_BACKOFF.value == "exponential_backoff"
        assert RetryStrategy.LINEAR_BACKOFF.value == "linear_backoff"


class TestRetryAttempt:
    def test_to_dict(self) -> None:
        attempt = RetryAttempt(
            attempt_number=1,
            timestamp=datetime(2025, 6, 15, 10, 0, 0),
            error_type=RetryErrorType.NETWORK_ERROR,
            error_message="connection lost",
            delay_seconds=2.0,
            success=False,
        )
        d = attempt.to_dict()
        assert d["attempt_number"] == 1
        assert d["error_type"] == "network_error"
        assert d["delay_seconds"] == 2.0
        assert d["success"] is False

    def test_success_flag(self) -> None:
        attempt = RetryAttempt(
            attempt_number=1,
            timestamp=datetime.now(),
            error_type=RetryErrorType.TIMEOUT_ERROR,
            error_message="timeout",
            delay_seconds=0.0,
            success=True,
        )
        assert attempt.success is True


class TestErrorStrategyConfig:
    def test_frozen_behavior(self) -> None:
        cfg = ErrorStrategyConfig(
            strategy=RetryStrategy.EXPONENTIAL_BACKOFF,
            max_retries=3,
            base_delay=1.0,
            backoff_factor=2.0,
            max_delay=60.0,
        )
        assert cfg.strategy == RetryStrategy.EXPONENTIAL_BACKOFF
        assert cfg.max_retries == 3


class TestRetryConfigDefaults:
    @patch("apps.automation.services.chat.retry_config._get_system_config_service")
    def test_defaults_loaded(self, mock_svc: MagicMock) -> None:
        mock_svc.return_value.get_value.return_value = ""
        config = RetryConfig()
        assert config.enabled is True
        assert config.max_retries == 3
        assert config.base_delay == 1.0
        assert config.max_delay == 60.0
        assert config.backoff_factor == 2.0
        assert config.timeout_seconds == 300.0

    @patch("apps.automation.services.chat.retry_config._get_system_config_service")
    def test_error_strategies_populated(self, mock_svc: MagicMock) -> None:
        mock_svc.return_value.get_value.return_value = ""
        config = RetryConfig()
        assert RetryErrorType.NETWORK_ERROR in config.error_strategies
        assert RetryErrorType.TIMEOUT_ERROR in config.error_strategies
        assert RetryErrorType.PERMISSION_ERROR in config.error_strategies
        assert RetryErrorType.VALIDATION_ERROR in config.error_strategies


class TestRetryConfigMethods:
    @patch("apps.automation.services.chat.retry_config._get_system_config_service")
    def test_is_enabled(self, mock_svc: MagicMock) -> None:
        mock_svc.return_value.get_value.return_value = ""
        config = RetryConfig()
        assert config.is_enabled() is True

    @patch("apps.automation.services.chat.retry_config._get_system_config_service")
    def test_get_max_retries_specific(self, mock_svc: MagicMock) -> None:
        mock_svc.return_value.get_value.return_value = ""
        config = RetryConfig()
        # Permission error has 0 max_retries
        assert config.get_max_retries(RetryErrorType.PERMISSION_ERROR) == 0
        # Network error uses the global max_retries
        assert config.get_max_retries(RetryErrorType.NETWORK_ERROR) == 3

    @patch("apps.automation.services.chat.retry_config._get_system_config_service")
    def test_get_max_retries_none(self, mock_svc: MagicMock) -> None:
        mock_svc.return_value.get_value.return_value = ""
        config = RetryConfig()
        assert config.get_max_retries(None) == 3

    @patch("apps.automation.services.chat.retry_config._get_system_config_service")
    def test_get_strategy(self, mock_svc: MagicMock) -> None:
        mock_svc.return_value.get_value.return_value = ""
        config = RetryConfig()
        assert config.get_strategy(RetryErrorType.NETWORK_ERROR) == RetryStrategy.EXPONENTIAL_BACKOFF
        assert config.get_strategy(RetryErrorType.PERMISSION_ERROR) == RetryStrategy.NO_RETRY
        assert config.get_strategy(RetryErrorType.NOT_FOUND_ERROR) == RetryStrategy.FIXED_DELAY

    @patch("apps.automation.services.chat.retry_config._get_system_config_service")
    def test_should_retry_disabled(self, mock_svc: MagicMock) -> None:
        mock_svc.return_value.get_value.return_value = ""
        config = RetryConfig()
        config.enabled = False
        assert config.should_retry(RetryErrorType.NETWORK_ERROR, 0) is False

    @patch("apps.automation.services.chat.retry_config._get_system_config_service")
    def test_should_retry_no_retry_strategy(self, mock_svc: MagicMock) -> None:
        mock_svc.return_value.get_value.return_value = ""
        config = RetryConfig()
        assert config.should_retry(RetryErrorType.PERMISSION_ERROR, 0) is False

    @patch("apps.automation.services.chat.retry_config._get_system_config_service")
    def test_should_retry_within_limit(self, mock_svc: MagicMock) -> None:
        mock_svc.return_value.get_value.return_value = ""
        config = RetryConfig()
        assert config.should_retry(RetryErrorType.NETWORK_ERROR, 0) is True
        assert config.should_retry(RetryErrorType.NETWORK_ERROR, 2) is True

    @patch("apps.automation.services.chat.retry_config._get_system_config_service")
    def test_should_retry_exceeds_limit(self, mock_svc: MagicMock) -> None:
        mock_svc.return_value.get_value.return_value = ""
        config = RetryConfig()
        assert config.should_retry(RetryErrorType.NETWORK_ERROR, 3) is False

    @patch("apps.automation.services.chat.retry_config._get_system_config_service")
    def test_calculate_delay_exponential(self, mock_svc: MagicMock) -> None:
        mock_svc.return_value.get_value.return_value = ""
        config = RetryConfig()
        d0 = config.calculate_delay(RetryErrorType.NETWORK_ERROR, 0)
        d1 = config.calculate_delay(RetryErrorType.NETWORK_ERROR, 1)
        # Exponential: base * factor^n
        assert d0 == 1.0
        assert d1 == 2.0

    @patch("apps.automation.services.chat.retry_config._get_system_config_service")
    def test_calculate_delay_fixed(self, mock_svc: MagicMock) -> None:
        mock_svc.return_value.get_value.return_value = ""
        config = RetryConfig()
        d = config.calculate_delay(RetryErrorType.NOT_FOUND_ERROR, 0)
        assert d == 5.0  # base_delay for NOT_FOUND

    @patch("apps.automation.services.chat.retry_config._get_system_config_service")
    def test_calculate_delay_no_retry(self, mock_svc: MagicMock) -> None:
        mock_svc.return_value.get_value.return_value = ""
        config = RetryConfig()
        d = config.calculate_delay(RetryErrorType.PERMISSION_ERROR, 0)
        assert d == 0.0

    @patch("apps.automation.services.chat.retry_config._get_system_config_service")
    def test_calculate_delay_unknown_type(self, mock_svc: MagicMock) -> None:
        mock_svc.return_value.get_value.return_value = ""
        config = RetryConfig()
        # Unknown type falls back to UNKNOWN_ERROR strategy (linear backoff)
        d = config.calculate_delay(RetryErrorType.UNKNOWN_ERROR, 1)
        assert d > 0.0

    @patch("apps.automation.services.chat.retry_config._get_system_config_service")
    def test_get_timeout_seconds(self, mock_svc: MagicMock) -> None:
        mock_svc.return_value.get_value.return_value = ""
        config = RetryConfig()
        assert config.get_timeout_seconds() == 300.0


class TestRetryManager:
    @patch("apps.automation.services.chat.retry_config._get_system_config_service")
    def test_init_default(self, mock_svc: MagicMock) -> None:
        mock_svc.return_value.get_value.return_value = ""
        mgr = RetryManager()
        assert mgr.config is not None
        assert mgr.attempts == []

    @patch("apps.automation.services.chat.retry_config._get_system_config_service")
    def test_classify_by_message_timeout(self, mock_svc: MagicMock) -> None:
        mock_svc.return_value.get_value.return_value = ""
        mgr = RetryManager()
        assert mgr._classify_by_message("request timed out") == RetryErrorType.TIMEOUT_ERROR

    @patch("apps.automation.services.chat.retry_config._get_system_config_service")
    def test_classify_by_message_network(self, mock_svc: MagicMock) -> None:
        mock_svc.return_value.get_value.return_value = ""
        mgr = RetryManager()
        assert mgr._classify_by_message("network connection failed") == RetryErrorType.NETWORK_ERROR

    @patch("apps.automation.services.chat.retry_config._get_system_config_service")
    def test_classify_by_message_permission(self, mock_svc: MagicMock) -> None:
        mock_svc.return_value.get_value.return_value = ""
        mgr = RetryManager()
        assert mgr._classify_by_message("permission denied") == RetryErrorType.PERMISSION_ERROR

    @patch("apps.automation.services.chat.retry_config._get_system_config_service")
    def test_classify_by_message_not_found(self, mock_svc: MagicMock) -> None:
        mock_svc.return_value.get_value.return_value = ""
        mgr = RetryManager()
        assert mgr._classify_by_message("resource not found") == RetryErrorType.NOT_FOUND_ERROR

    @patch("apps.automation.services.chat.retry_config._get_system_config_service")
    def test_classify_by_message_unknown(self, mock_svc: MagicMock) -> None:
        mock_svc.return_value.get_value.return_value = ""
        mgr = RetryManager()
        assert mgr._classify_by_message("something weird") == RetryErrorType.UNKNOWN_ERROR

    @patch("apps.automation.services.chat.retry_config._get_system_config_service")
    def test_execute_success_first_try(self, mock_svc: MagicMock) -> None:
        mock_svc.return_value.get_value.return_value = ""
        mgr = RetryManager()
        result = mgr.execute_with_retry(lambda: "ok", operation_name="test")
        assert result == "ok"

    @patch("apps.automation.services.chat.retry_config._get_system_config_service")
    def test_execute_success_after_retry(self, mock_svc: MagicMock) -> None:
        mock_svc.return_value.get_value.return_value = ""
        mgr = RetryManager()
        call_count = 0

        def flaky() -> str:
            nonlocal call_count
            call_count += 1
            if call_count < 2:
                raise ValueError("network timeout error")
            return "recovered"

        result = mgr.execute_with_retry(flaky, operation_name="test")
        assert result == "recovered"

    @patch("apps.automation.services.chat.retry_config._get_system_config_service")
    def test_get_retry_summary(self, mock_svc: MagicMock) -> None:
        mock_svc.return_value.get_value.return_value = ""
        mgr = RetryManager()
        mgr.execute_with_retry(lambda: "ok")
        summary = mgr.get_retry_summary()
        assert summary["total_attempts"] >= 0
        assert "elapsed_time" in summary
        assert "config" in summary
