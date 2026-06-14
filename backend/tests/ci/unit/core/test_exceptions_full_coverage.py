"""Tests for core.exceptions: base, common, external, error_presentation."""
from __future__ import annotations

import pytest

from apps.core.exceptions.base import BusinessError, BusinessException
from apps.core.exceptions.common import (
    AuthenticationError,
    ConflictError,
    ForbiddenError,
    NotFoundError,
    PermissionDenied,
    RateLimitError,
    UnauthorizedError,
    ValidationException,
)
from apps.core.exceptions.error_presentation import ErrorEnvelope, ExceptionPresenter
from apps.core.exceptions.external import (
    APIError,
    AutoTokenAcquisitionError,
    BrowserAutomationError,
    CaptchaRecognitionError,
    ExternalServiceError,
    ImapConnectionError,
    LoginFailedError,
    NetworkError,
    NoAvailableAccountError,
    RecognitionTimeoutError,
    ServiceUnavailableError,
    TokenAcquisitionTimeoutError,
    TokenError,
)


# ---------------------------------------------------------------------------
# BusinessException
# ---------------------------------------------------------------------------


class TestBusinessException:
    def test_basic(self) -> None:
        exc = BusinessException("something went wrong")
        assert exc.message == "something went wrong"
        assert exc.code == "BusinessException"
        assert exc.errors == {}

    def test_custom_code(self) -> None:
        exc = BusinessException("err", code="ERR1", errors={"k": "v"})
        assert exc.code == "ERR1"
        assert exc.errors == {"k": "v"}

    def test_str(self) -> None:
        exc = BusinessException("msg", code="C")
        assert str(exc) == "C: msg"

    def test_repr(self) -> None:
        exc = BusinessException("msg", code="C")
        r = repr(exc)
        assert "BusinessException" in r
        assert "msg" in r

    def test_to_dict(self) -> None:
        exc = BusinessException("msg", code="C", errors={"a": 1})
        d = exc.to_dict()
        assert d["success"] is False
        assert d["code"] == "C"
        assert d["message"] == "msg"
        assert d["errors"] == {"a": 1}

    def test_to_dict_no_errors(self) -> None:
        exc = BusinessException("msg")
        d = exc.to_dict()
        assert d["errors"] == {}


# ---------------------------------------------------------------------------
# BusinessError
# ---------------------------------------------------------------------------


class TestBusinessError:
    def test_basic(self) -> None:
        exc = BusinessError("err", status=422)
        assert exc.status == 422
        assert exc.code == "BUSINESS_ERROR"

    def test_custom_code(self) -> None:
        exc = BusinessError("msg", code="CUSTOM_CODE")
        assert exc.code == "CUSTOM_CODE"


# ---------------------------------------------------------------------------
# Common exceptions
# ---------------------------------------------------------------------------


class TestCommonExceptions:
    def test_validation_exception(self) -> None:
        exc = ValidationException("bad input")
        assert exc.code == "VALIDATION_ERROR"

    def test_permission_denied(self) -> None:
        exc = PermissionDenied("no access")
        assert exc.code == "PERMISSION_DENIED"

    def test_not_found(self) -> None:
        exc = NotFoundError("missing")
        assert exc.code == "NOT_FOUND"

    def test_conflict(self) -> None:
        exc = ConflictError("dup")
        assert exc.code == "CONFLICT"

    def test_authentication_error(self) -> None:
        exc = AuthenticationError("not authed")
        assert exc.code == "AUTHENTICATION_ERROR"

    def test_rate_limit(self) -> None:
        exc = RateLimitError("slow down")
        assert exc.code == "RATE_LIMIT_ERROR"

    def test_forbidden_backward_compat(self) -> None:
        exc = ForbiddenError("no access")
        assert exc.status == 403
        assert isinstance(exc, PermissionDenied)

    def test_unauthorized_backward_compat(self) -> None:
        exc = UnauthorizedError("login plz")
        assert exc.status == 401
        assert isinstance(exc, AuthenticationError)


# ---------------------------------------------------------------------------
# External exceptions
# ---------------------------------------------------------------------------


class TestExternalExceptions:
    def test_external_service_error(self) -> None:
        exc = ExternalServiceError("svc err")
        assert exc.code == "EXTERNAL_SERVICE_ERROR"

    def test_service_unavailable(self) -> None:
        exc = ServiceUnavailableError("down", service_name="ollama")
        assert exc.service_name == "ollama"
        assert exc.errors["service"] == "ollama"

    def test_service_unavailable_no_name(self) -> None:
        exc = ServiceUnavailableError()
        assert exc.service_name is None

    def test_recognition_timeout(self) -> None:
        exc = RecognitionTimeoutError("timed out", timeout_seconds=30.0)
        assert exc.timeout_seconds == 30.0
        assert exc.errors["timeout_seconds"] == 30.0

    def test_recognition_timeout_no_seconds(self) -> None:
        exc = RecognitionTimeoutError()
        assert exc.timeout_seconds is None

    def test_token_error(self) -> None:
        exc = TokenError("bad token")
        assert exc.code == "TOKEN_ERROR"

    def test_api_error(self) -> None:
        exc = APIError("api fail")
        assert exc.code == "API_ERROR"

    def test_network_error(self) -> None:
        exc = NetworkError("no network")
        assert exc.code == "NETWORK_ERROR"

    def test_auto_token_acquisition_error(self) -> None:
        exc = AutoTokenAcquisitionError()
        assert exc.code == "AUTO_TOKEN_ACQUISITION_ERROR"

    def test_login_failed(self) -> None:
        exc = LoginFailedError(attempts=[{"user": "admin"}])
        assert exc.attempts == [{"user": "admin"}]

    def test_login_failed_no_attempts(self) -> None:
        exc = LoginFailedError()
        assert exc.attempts == []

    def test_no_available_account(self) -> None:
        exc = NoAvailableAccountError()
        assert exc.code == "NO_AVAILABLE_ACCOUNT"

    def test_token_acquisition_timeout(self) -> None:
        exc = TokenAcquisitionTimeoutError()
        assert exc.code == "TOKEN_ACQUISITION_TIMEOUT"

    def test_captcha_recognition_error(self) -> None:
        exc = CaptchaRecognitionError()
        assert exc.code == "CAPTCHA_RECOGNITION_ERROR"

    def test_browser_automation_error(self) -> None:
        exc = BrowserAutomationError("page fail", url="https://example.com")
        assert exc.url == "https://example.com"
        assert exc.errors["url"] == "https://example.com"

    def test_browser_automation_error_no_url(self) -> None:
        exc = BrowserAutomationError()
        assert exc.url is None

    def test_imap_connection_error(self) -> None:
        exc = ImapConnectionError("conn fail", host="imap.example.com")
        assert exc.host == "imap.example.com"
        assert exc.errors["host"] == "imap.example.com"

    def test_imap_connection_error_no_host(self) -> None:
        exc = ImapConnectionError()
        assert exc.host is None


# ---------------------------------------------------------------------------
# ErrorEnvelope
# ---------------------------------------------------------------------------


class TestErrorEnvelope:
    def test_to_payload(self) -> None:
        env = ErrorEnvelope(code="ERR", message="err msg", errors={"k": "v"}, retryable=True, channel="http")
        p = env.to_payload()
        assert p["code"] == "ERR"
        assert p["message"] == "err msg"
        assert p["errors"] == {"k": "v"}
        assert p["retryable"] is True
        assert p["channel"] == "http"
        assert p["error"] == "err msg"

    def test_to_payload_no_legacy_error(self) -> None:
        env = ErrorEnvelope(code="E", message="m", errors={})
        p = env.to_payload(include_legacy_error=False)
        assert "error" not in p

    def test_defaults(self) -> None:
        env = ErrorEnvelope(code="E", message="m", errors={})
        assert env.retryable is False
        assert env.channel == "http"


# ---------------------------------------------------------------------------
# ExceptionPresenter
# ---------------------------------------------------------------------------


class TestExceptionPresenter:
    def setup_method(self) -> None:
        self.presenter = ExceptionPresenter()

    def test_business_exception_validation(self) -> None:
        exc = ValidationException("bad")
        envelope, status = self.presenter.present(exc, channel="http")
        assert status == 400
        assert envelope.code == "VALIDATION_ERROR"

    def test_business_exception_not_found(self) -> None:
        exc = NotFoundError("gone")
        _, status = self.presenter.present(exc, channel="http")
        assert status == 404

    def test_business_exception_permission(self) -> None:
        exc = PermissionDenied("no")
        _, status = self.presenter.present(exc, channel="http")
        assert status == 403

    def test_business_exception_auth(self) -> None:
        exc = AuthenticationError("unauthed")
        _, status = self.presenter.present(exc, channel="http")
        assert status == 401

    def test_business_exception_conflict(self) -> None:
        exc = ConflictError("dup")
        _, status = self.presenter.present(exc, channel="http")
        assert status == 409

    def test_business_exception_rate_limit(self) -> None:
        exc = RateLimitError("slow")
        envelope, status = self.presenter.present(exc, channel="http")
        assert status == 429
        assert envelope.retryable is True

    def test_business_exception_service_unavailable(self) -> None:
        exc = ServiceUnavailableError("down")
        envelope, status = self.presenter.present(exc, channel="http")
        assert status == 503
        assert envelope.retryable is True

    def test_business_exception_recognition_timeout(self) -> None:
        exc = RecognitionTimeoutError("timeout")
        envelope, status = self.presenter.present(exc, channel="http")
        assert status == 504
        assert envelope.retryable is True

    def test_business_exception_external(self) -> None:
        exc = ExternalServiceError("ext err")
        envelope, status = self.presenter.present(exc, channel="http")
        assert status == 502
        assert envelope.retryable is True

    def test_unknown_exception_http(self) -> None:
        exc = RuntimeError("oops")
        envelope, status = self.presenter.present(exc, channel="http", debug=False)
        assert status == 500
        assert envelope.code == "INTERNAL_ERROR"
        assert "系统错误" in envelope.message

    def test_unknown_exception_debug(self) -> None:
        exc = RuntimeError("oops detail")
        envelope, status = self.presenter.present(exc, channel="http", debug=True)
        assert "oops detail" in envelope.message

    def test_unknown_exception_websocket(self) -> None:
        exc = RuntimeError("oops")
        _, status = self.presenter.present(exc, channel="websocket")
        assert status is None

    def test_business_exception_with_explicit_status(self) -> None:
        class CustomExc(BusinessException):
            status = 422
        exc = CustomExc("custom")
        _, status = self.presenter.present(exc, channel="http")
        assert status == 422

    def test_llm_exception_mapping(self) -> None:
        """Test that LLM exceptions are correctly mapped."""
        try:
            from apps.core.llm.exceptions import LLMAuthenticationError

            exc = LLMAuthenticationError("llm auth fail")
            envelope, status = self.presenter.present(exc, channel="http")
            assert status == 401
        except ImportError:
            pytest.skip("LLM exceptions not available")
