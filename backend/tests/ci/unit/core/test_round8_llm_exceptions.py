"""Tests for LLM exceptions and LLM service facade."""

from __future__ import annotations

import pytest

from apps.core.llm.exceptions import (
    LLMError,
    LLMNetworkError,
    LLMAPIError,
    LLMAuthenticationError,
    LLMBackendUnavailableError,
    LLMTimeoutError,
)


# ---------------------------------------------------------------------------
# LLM Exception hierarchy
# ---------------------------------------------------------------------------


class TestLLMExceptions:
    def test_llm_error_defaults(self):
        exc = LLMError()
        assert exc.code == "LLM_ERROR"
        assert "LLM 服务错误" in str(exc.message)

    def test_llm_error_custom(self):
        exc = LLMError(message="custom", code="CUSTOM")
        assert exc.code == "CUSTOM"

    def test_llm_network_error(self):
        exc = LLMNetworkError()
        assert exc.code == "LLM_NETWORK_ERROR"

    def test_llm_api_error(self):
        exc = LLMAPIError()
        assert exc.code == "LLM_API_ERROR"

    def test_llm_api_error_with_status_code(self):
        exc = LLMAPIError(status_code=429)
        assert exc.status_code == 429
        assert exc.errors["status_code"] == 429

    def test_llm_auth_error(self):
        exc = LLMAuthenticationError()
        assert exc.code == "LLM_AUTH_ERROR"
        assert "api_key" in exc.errors

    def test_llm_auth_error_custom(self):
        exc = LLMAuthenticationError(message="custom auth error")
        assert exc.message == "custom auth error"

    def test_llm_backend_unavailable(self):
        exc = LLMBackendUnavailableError()
        assert exc.code == "LLM_ALL_BACKENDS_UNAVAILABLE"

    def test_llm_timeout_error(self):
        exc = LLMTimeoutError()
        assert exc.code == "LLM_TIMEOUT"
        assert exc.timeout_seconds is None

    def test_llm_timeout_error_with_seconds(self):
        exc = LLMTimeoutError(timeout_seconds=30.0)
        assert exc.timeout_seconds == 30.0
        assert exc.errors["timeout_seconds"] == 30.0

    def test_llm_api_error_no_status_code(self):
        exc = LLMAPIError(message="test", status_code=None)
        assert exc.errors is None or "status_code" not in (exc.errors or {})

    def test_llm_timeout_with_errors_dict(self):
        exc = LLMTimeoutError(errors={"key": "val"}, timeout_seconds=10.0)
        assert exc.errors["key"] == "val"
        assert exc.errors["timeout_seconds"] == 10.0
