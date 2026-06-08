"""Tests for core.llm.exceptions."""
from __future__ import annotations

import pytest

from apps.core.llm.exceptions import (
    LLMAPIError,
    LLMAuthenticationError,
    LLMBackendUnavailableError,
    LLMError,
    LLMNetworkError,
    LLMTimeoutError,
)


class TestLLMError:
    def test_default_message(self) -> None:
        err = LLMError()
        assert err.message == "LLM 服务错误"
        assert err.code == "LLM_ERROR"

    def test_custom_message(self) -> None:
        err = LLMError(message="custom", code="CUSTOM")
        assert err.message == "custom"
        assert err.code == "CUSTOM"

    def test_with_errors(self) -> None:
        err = LLMError(errors={"detail": "test"})
        assert err.errors == {"detail": "test"}


class TestLLMNetworkError:
    def test_default(self) -> None:
        err = LLMNetworkError()
        assert err.code == "LLM_NETWORK_ERROR"
        assert "网络" in err.message

    def test_custom(self) -> None:
        err = LLMNetworkError(message="Connection refused", code="NET_ERR")
        assert err.message == "Connection refused"


class TestLLMAPIError:
    def test_default(self) -> None:
        err = LLMAPIError()
        assert err.code == "LLM_API_ERROR"
        assert err.status_code is None

    def test_with_status_code(self) -> None:
        err = LLMAPIError(status_code=500)
        assert err.status_code == 500
        assert err.errors["status_code"] == 500

    def test_with_existing_errors_and_status(self) -> None:
        err = LLMAPIError(errors={"detail": "test"}, status_code=400)
        assert err.errors["detail"] == "test"
        assert err.errors["status_code"] == 400


class TestLLMAuthenticationError:
    def test_default(self) -> None:
        err = LLMAuthenticationError()
        assert err.code == "LLM_AUTH_ERROR"
        assert "api_key" in err.errors

    def test_custom_message(self) -> None:
        err = LLMAuthenticationError(message="Invalid key")
        assert err.message == "Invalid key"


class TestLLMTimeoutError:
    def test_default(self) -> None:
        err = LLMTimeoutError()
        assert err.code == "LLM_TIMEOUT"
        assert err.timeout_seconds is None

    def test_with_timeout(self) -> None:
        err = LLMTimeoutError(timeout_seconds=30.0)
        assert err.timeout_seconds == 30.0
        assert err.errors["timeout_seconds"] == 30.0


class TestLLMBackendUnavailableError:
    def test_default(self) -> None:
        err = LLMBackendUnavailableError()
        assert err.code == "LLM_ALL_BACKENDS_UNAVAILABLE"
        assert "不可用" in err.message

    def test_inherits_api_error(self) -> None:
        err = LLMBackendUnavailableError()
        assert isinstance(err, LLMAPIError)
