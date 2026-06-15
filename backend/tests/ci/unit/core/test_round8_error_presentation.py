"""Tests for error_presentation (ExceptionPresenter and ErrorEnvelope)."""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from apps.core.exceptions.error_presentation import ErrorEnvelope, ExceptionPresenter
from apps.core.exceptions import (
    BusinessException,
    ValidationException,
    AuthenticationError,
    PermissionDenied,
    NotFoundError,
    ConflictError,
    RateLimitError,
    ServiceUnavailableError,
    RecognitionTimeoutError,
    ExternalServiceError,
)


# ---------------------------------------------------------------------------
# ErrorEnvelope
# ---------------------------------------------------------------------------


class TestErrorEnvelope:
    def test_basic(self):
        env = ErrorEnvelope(code="TEST", message="msg", errors={"k": "v"})
        payload = env.to_payload()
        assert payload["code"] == "TEST"
        assert payload["message"] == "msg"
        assert payload["errors"] == {"k": "v"}
        assert payload["retryable"] is False
        assert payload["channel"] == "http"

    def test_no_legacy_error(self):
        env = ErrorEnvelope(code="TEST", message="msg", errors={})
        payload = env.to_payload(include_legacy_error=False)
        assert "error" not in payload

    def test_with_legacy_error(self):
        env = ErrorEnvelope(code="TEST", message="msg", errors={})
        payload = env.to_payload(include_legacy_error=True)
        assert payload["error"] == "msg"

    def test_retryable(self):
        env = ErrorEnvelope(code="TEST", message="msg", errors={}, retryable=True)
        payload = env.to_payload()
        assert payload["retryable"] is True

    def test_no_channel(self):
        env = ErrorEnvelope(code="TEST", message="msg", errors={}, channel="")
        payload = env.to_payload()
        assert "channel" not in payload


# ---------------------------------------------------------------------------
# ExceptionPresenter
# ---------------------------------------------------------------------------


class TestExceptionPresenter:
    def setup_method(self):
        self.presenter = ExceptionPresenter()

    def test_business_exception(self):
        exc = BusinessException(message="test error", code="TEST_ERR")
        envelope, status = self.presenter.present(exc, channel="http")
        assert envelope.code == "TEST_ERR"
        assert status == 400

    def test_validation_exception(self):
        exc = ValidationException(message="invalid")
        envelope, status = self.presenter.present(exc, channel="http")
        assert status == 400

    def test_auth_exception(self):
        exc = AuthenticationError(message="unauthorized")
        envelope, status = self.presenter.present(exc, channel="http")
        assert status == 401

    def test_permission_denied(self):
        exc = PermissionDenied(message="denied")
        envelope, status = self.presenter.present(exc, channel="http")
        assert status == 403

    def test_not_found(self):
        exc = NotFoundError(message="missing")
        envelope, status = self.presenter.present(exc, channel="http")
        assert status == 404

    def test_conflict(self):
        exc = ConflictError(message="conflict")
        envelope, status = self.presenter.present(exc, channel="http")
        assert status == 409

    def test_rate_limit(self):
        exc = RateLimitError(message="slow down")
        envelope, status = self.presenter.present(exc, channel="http")
        assert status == 429

    def test_service_unavailable(self):
        exc = ServiceUnavailableError(message="down")
        envelope, status = self.presenter.present(exc, channel="http")
        assert status == 503

    def test_recognition_timeout(self):
        exc = RecognitionTimeoutError(message="timeout")
        envelope, status = self.presenter.present(exc, channel="http")
        assert status == 504

    def test_external_service(self):
        exc = ExternalServiceError(message="ext error")
        envelope, status = self.presenter.present(exc, channel="http")
        assert status == 502

    def test_generic_exception_http(self):
        exc = ValueError("something broke")
        envelope, status = self.presenter.present(exc, channel="http")
        assert envelope.code == "INTERNAL_ERROR"
        assert status == 500
        assert envelope.message == "系统错误,请稍后重试"

    def test_generic_exception_debug(self):
        exc = ValueError("something broke")
        envelope, status = self.presenter.present(exc, channel="http", debug=True)
        assert "something broke" in envelope.message

    def test_generic_exception_non_http(self):
        exc = ValueError("something broke")
        envelope, status = self.presenter.present(exc, channel="websocket")
        assert status is None

    def test_business_exception_retryable(self):
        exc = RateLimitError(message="slow down")
        envelope, _ = self.presenter.present(exc, channel="http")
        assert envelope.retryable is True

    def test_business_exception_not_retryable(self):
        exc = ValidationException(message="invalid")
        envelope, _ = self.presenter.present(exc, channel="http")
        assert envelope.retryable is False

    def test_business_exception_custom_status(self):
        class CustomBizError(BusinessException):
            status = 418

        exc = CustomBizError(message="teapot")
        _, status = self.presenter.present(exc, channel="http")
        assert status == 418
