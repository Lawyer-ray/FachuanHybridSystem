"""Tests for apps.core.exceptions.error_presentation."""
from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from apps.core.exceptions import (
    AuthenticationError,
    ConflictError,
    ExternalServiceError,
    NotFoundError,
    PermissionDenied,
    RateLimitError,
    RecognitionTimeoutError,
    ServiceUnavailableError,
    ValidationException,
)
from apps.core.exceptions.base import BusinessException
from apps.core.exceptions.error_presentation import ErrorEnvelope, ExceptionPresenter


# ============================================================
# ErrorEnvelope
# ============================================================


class TestErrorEnvelope:
    def test_to_payload_full(self) -> None:
        env = ErrorEnvelope(code="C", message="m", errors={"k": "v"}, retryable=True, channel="ws")
        payload = env.to_payload()
        assert payload["code"] == "C"
        assert payload["message"] == "m"
        assert payload["errors"] == {"k": "v"}
        assert payload["retryable"] is True
        assert payload["channel"] == "ws"
        assert payload["error"] == "m"

    def test_to_payload_no_legacy(self) -> None:
        env = ErrorEnvelope(code="C", message="m", errors={})
        payload = env.to_payload(include_legacy_error=False)
        assert "error" not in payload

    def test_to_payload_defaults(self) -> None:
        env = ErrorEnvelope(code="X", message="y", errors={})
        assert env.retryable is False
        assert env.channel == "http"


# ============================================================
# ExceptionPresenter
# ============================================================


class TestExceptionPresenterBusinessExceptions:
    """Present business exceptions and verify status mapping."""

    def setup_method(self) -> None:
        self.presenter = ExceptionPresenter()

    def test_validation_exception(self) -> None:
        exc = ValidationException(message="bad data", errors={"field": "required"})
        envelope, status = self.presenter.present(exc, channel="http")
        assert envelope.code == "VALIDATION_ERROR"
        assert status == 400
        assert envelope.retryable is False

    def test_auth_error(self) -> None:
        envelope, status = self.presenter.present(AuthenticationError("no token"), channel="http")
        assert envelope.code == "AUTHENTICATION_ERROR"
        assert status == 401

    def test_permission_denied(self) -> None:
        envelope, status = self.presenter.present(PermissionDenied("no"), channel="http")
        assert status == 403

    def test_not_found(self) -> None:
        envelope, status = self.presenter.present(NotFoundError("missing"), channel="http")
        assert status == 404

    def test_conflict(self) -> None:
        envelope, status = self.presenter.present(ConflictError("dup"), channel="http")
        assert status == 409

    def test_rate_limit(self) -> None:
        envelope, status = self.presenter.present(RateLimitError("slow down"), channel="http")
        assert status == 429
        assert envelope.retryable is True

    def test_service_unavailable(self) -> None:
        envelope, status = self.presenter.present(ServiceUnavailableError("down"), channel="http")
        assert status == 503
        assert envelope.retryable is True

    def test_recognition_timeout(self) -> None:
        envelope, status = self.presenter.present(RecognitionTimeoutError("slow"), channel="http")
        assert status == 504
        assert envelope.retryable is True

    def test_external_service_error(self) -> None:
        envelope, status = self.presenter.present(ExternalServiceError("bad"), channel="http")
        assert status == 502
        assert envelope.retryable is True

    def test_unknown_business_exception_fallback_400(self) -> None:
        exc = BusinessException("custom", code="CUSTOM_CODE")
        envelope, status = self.presenter.present(exc, channel="http")
        assert status == 400

    def test_business_exception_with_explicit_status(self) -> None:
        exc = BusinessException("custom", code="CUSTOM_CODE")
        exc.status = 418  # type: ignore[attr-defined]
        envelope, status = self.presenter.present(exc, channel="http")
        assert status == 418

    def test_ws_channel_status_still_returned_for_business_exc(self) -> None:
        # Business exceptions still map to HTTP status even on ws channel
        envelope, status = self.presenter.present(
            ExternalServiceError("bad"), channel="ws"
        )
        assert status == 502

    def test_generic_exception_ws_no_status(self) -> None:
        envelope, status = self.presenter.present(
            ValueError("oops"), channel="ws", debug=False
        )
        assert status is None

    def test_generic_exception_debug(self) -> None:
        envelope, status = self.presenter.present(
            ValueError("oops"), channel="http", debug=True
        )
        assert envelope.code == "INTERNAL_ERROR"
        assert envelope.message == "oops"
        assert status == 500

    def test_generic_exception_no_debug(self) -> None:
        envelope, status = self.presenter.present(
            ValueError("oops"), channel="http", debug=False
        )
        assert envelope.message == "系统错误,请稍后重试"


# ============================================================
# Retryable mapping for _retryable_for_business_exception
# ============================================================


class TestRetryableMapping:
    def setup_method(self) -> None:
        self.presenter = ExceptionPresenter()

    @pytest.mark.parametrize(
        "exc_cls",
        [RateLimitError, ServiceUnavailableError, RecognitionTimeoutError, ExternalServiceError],
    )
    def test_retryable(self, exc_cls: type) -> None:
        envelope, _ = self.presenter.present(exc_cls("test"), channel="http")
        assert envelope.retryable is True

    @pytest.mark.parametrize(
        "exc_cls",
        [ValidationException, AuthenticationError, NotFoundError, PermissionDenied, ConflictError],
    )
    def test_not_retryable(self, exc_cls: type) -> None:
        envelope, _ = self.presenter.present(exc_cls("test"), channel="http")
        assert envelope.retryable is False
