"""Coverage tests for core.exceptions.error_presentation."""

from unittest.mock import MagicMock, patch

import pytest

from apps.core.exceptions.error_presentation import ErrorEnvelope, ExceptionPresenter


class TestErrorEnvelope:
    def test_to_payload_basic(self):
        env = ErrorEnvelope(code="ERR", message="msg", errors={"e": 1})
        p = env.to_payload()
        assert p["code"] == "ERR"
        assert p["message"] == "msg"
        assert p["errors"] == {"e": 1}

    def test_to_payload_with_legacy_error(self):
        env = ErrorEnvelope(code="ERR", message="msg", errors={})
        p = env.to_payload(include_legacy_error=True)
        assert p["error"] == "msg"

    def test_to_payload_without_legacy_error(self):
        env = ErrorEnvelope(code="ERR", message="msg", errors={})
        p = env.to_payload(include_legacy_error=False)
        assert "error" not in p

    def test_to_payload_retryable(self):
        env = ErrorEnvelope(code="ERR", message="msg", errors={}, retryable=True)
        p = env.to_payload()
        assert p["retryable"] is True

    def test_to_payload_channel(self):
        env = ErrorEnvelope(code="ERR", message="msg", errors={}, channel="sse")
        p = env.to_payload()
        assert p["channel"] == "sse"


class TestExceptionPresenter:
    def _make(self):
        return ExceptionPresenter()

    def test_present_generic_exception_debug(self):
        presenter = self._make()
        exc = ValueError("test error")
        envelope, status = presenter.present(exc, channel="http", debug=True)
        assert envelope.code == "INTERNAL_ERROR"
        assert "test error" in envelope.message
        assert status == 500

    def test_present_generic_exception_no_debug(self):
        presenter = self._make()
        exc = ValueError("test error")
        envelope, status = presenter.present(exc, channel="http", debug=False)
        assert envelope.code == "INTERNAL_ERROR"
        assert "系统错误" in envelope.message
        assert status == 500

    def test_present_generic_exception_sse(self):
        presenter = self._make()
        exc = ValueError("test error")
        envelope, status = presenter.present(exc, channel="sse", debug=True)
        assert status is None

    def test_present_validation_exception(self):
        presenter = self._make()
        from apps.core.exceptions import ValidationException

        exc = ValidationException(message="invalid", code="INVALID")
        envelope, status = presenter.present(exc, channel="http")
        assert status == 400

    def test_present_not_found(self):
        presenter = self._make()
        from apps.core.exceptions import NotFoundError

        exc = NotFoundError(message="not found", code="NOT_FOUND")
        envelope, status = presenter.present(exc, channel="http")
        assert status == 404

    def test_present_auth_error(self):
        presenter = self._make()
        from apps.core.exceptions import AuthenticationError

        exc = AuthenticationError(message="auth fail", code="AUTH")
        envelope, status = presenter.present(exc, channel="http")
        assert status == 401

    def test_present_permission_denied(self):
        presenter = self._make()
        from apps.core.exceptions import PermissionDenied

        exc = PermissionDenied(message="denied", code="DENIED")
        envelope, status = presenter.present(exc, channel="http")
        assert status == 403

    def test_present_conflict(self):
        presenter = self._make()
        from apps.core.exceptions import ConflictError

        exc = ConflictError(message="conflict", code="CONFLICT")
        envelope, status = presenter.present(exc, channel="http")
        assert status == 409

    def test_present_rate_limit(self):
        presenter = self._make()
        from apps.core.exceptions import RateLimitError

        exc = RateLimitError(message="rate limited", code="RATE_LIMIT")
        envelope, status = presenter.present(exc, channel="http")
        assert status == 429
        assert envelope.retryable is True

    def test_present_service_unavailable(self):
        presenter = self._make()
        from apps.core.exceptions import ServiceUnavailableError

        exc = ServiceUnavailableError(message="unavail", code="UNAVAIL")
        envelope, status = presenter.present(exc, channel="http")
        assert status == 503
        assert envelope.retryable is True

    def test_present_external_service(self):
        presenter = self._make()
        from apps.core.exceptions import ExternalServiceError

        exc = ExternalServiceError(message="ext fail", code="EXT")
        envelope, status = presenter.present(exc, channel="http")
        assert status == 502
