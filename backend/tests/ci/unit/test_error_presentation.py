"""Tests for apps.core.exceptions.error_presentation."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from apps.core.exceptions import (
    AuthenticationError,
    BusinessException,
    ConflictError,
    ExternalServiceError,
    NotFoundError,
    PermissionDenied,
    RateLimitError,
    RecognitionTimeoutError,
    ServiceUnavailableError,
    ValidationException,
)
from apps.core.exceptions.error_presentation import ErrorEnvelope, ExceptionPresenter


class TestErrorEnvelope:
    def test_to_payload_full(self):
        env = ErrorEnvelope(code="TEST", message="msg", errors={"k": "v"}, retryable=True, channel="ws")
        payload = env.to_payload()
        assert payload["code"] == "TEST"
        assert payload["message"] == "msg"
        assert payload["errors"] == {"k": "v"}
        assert payload["retryable"] is True
        assert payload["channel"] == "ws"
        assert payload["error"] == "msg"

    def test_to_payload_no_legacy(self):
        env = ErrorEnvelope(code="C", message="m", errors={})
        payload = env.to_payload(include_legacy_error=False)
        assert "error" not in payload

    def test_to_payload_empty_channel(self):
        env = ErrorEnvelope(code="C", message="m", errors={}, channel="")
        payload = env.to_payload()
        assert "channel" not in payload

    def test_to_payload_empty_errors_becomes_dict(self):
        env = ErrorEnvelope(code="C", message="m", errors=None)
        payload = env.to_payload()
        assert payload["errors"] == {}


class TestExceptionPresenter:
    def setup_method(self):
        self.presenter = ExceptionPresenter()

    def test_business_exception_validation(self):
        exc = ValidationException("bad")
        envelope, status = self.presenter.present(exc, channel="http")
        assert envelope.code == exc.code
        assert status == 400

    def test_business_exception_auth(self):
        exc = AuthenticationError(message="unauth")
        _, status = self.presenter.present(exc, channel="http")
        assert status == 401

    def test_business_exception_permission(self):
        exc = PermissionDenied(message="no")
        _, status = self.presenter.present(exc, channel="http")
        assert status == 403

    def test_business_exception_not_found(self):
        exc = NotFoundError(message="nf")
        _, status = self.presenter.present(exc, channel="http")
        assert status == 404

    def test_business_exception_conflict(self):
        exc = ConflictError(message="cf")
        _, status = self.presenter.present(exc, channel="http")
        assert status == 409

    def test_business_exception_rate_limit(self):
        exc = RateLimitError(message="rl")
        envelope, status = self.presenter.present(exc, channel="http")
        assert status == 429
        assert envelope.retryable is True

    def test_business_exception_service_unavailable(self):
        exc = ServiceUnavailableError(message="su")
        envelope, status = self.presenter.present(exc, channel="http")
        assert status == 503
        assert envelope.retryable is True

    def test_business_exception_recognition_timeout(self):
        exc = RecognitionTimeoutError(message="rt")
        envelope, status = self.presenter.present(exc, channel="http")
        assert status == 504
        assert envelope.retryable is True

    def test_business_exception_external_service(self):
        exc = ExternalServiceError(message="es")
        envelope, status = self.presenter.present(exc, channel="http")
        assert status == 502
        assert envelope.retryable is True

    def test_business_exception_fallback_status(self):
        # A generic BusinessException with no matching subclass
        exc = BusinessException(message="gen", code="GEN")
        _, status = self.presenter.present(exc, channel="http")
        assert status == 400

    def test_business_exception_custom_status(self):
        exc = BusinessException(message="custom", code="C")
        # Manually set status attribute to test the status check branch
        exc.status = 418  # type: ignore[attr-defined]
        _, status = self.presenter.present(exc, channel="http")
        assert status == 418

    def test_generic_exception_debug(self):
        exc = RuntimeError("something broke")
        envelope, status = self.presenter.present(exc, channel="http", debug=True)
        assert envelope.code == "INTERNAL_ERROR"
        assert "something broke" in envelope.message
        assert status == 500

    def test_generic_exception_no_debug(self):
        exc = RuntimeError("something broke")
        envelope, status = self.presenter.present(exc, channel="http", debug=False)
        assert envelope.message == "系统错误,请稍后重试"

    def test_ws_channel_no_status(self):
        exc = RuntimeError("err")
        _, status = self.presenter.present(exc, channel="ws")
        assert status is None

    def test_retryable_non_retryable(self):
        exc = ValidationException("bad")
        envelope, _ = self.presenter.present(exc, channel="http")
        assert envelope.retryable is False

    def test_llm_exceptions_mapping(self):
        """Test LLM exception types if importable."""
        try:
            from apps.core.llm.exceptions import LLMAuthenticationError, LLMBackendUnavailableError, LLMTimeoutError
        except ImportError:
            pytest.skip("LLM exceptions not importable")

        exc = LLMAuthenticationError(message="auth fail")
        envelope, status = self.presenter.present(exc, channel="http")
        assert status == 401

        exc = LLMBackendUnavailableError(message="unavail")
        envelope, status = self.presenter.present(exc, channel="http")
        # Maps to either ServiceUnavailableError (503) or ExternalServiceError (502)
        assert status in (502, 503)

        exc = LLMTimeoutError(message="timeout")
        envelope, status = self.presenter.present(exc, channel="http")
        # Maps to either RecognitionTimeoutError (504) or ExternalServiceError (502)
        assert status in (502, 504)
