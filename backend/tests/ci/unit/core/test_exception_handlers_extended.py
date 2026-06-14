"""
Extended unit tests for core/exceptions/handlers.py

Covers:
  - _get_user_id: from request.user, from request.auth, no user
  - _safe_log_value: primitives, string truncation, dict, list, tuple, nested, depth limit
  - _log_extra: with/without errors
  - _attach_request_meta: with request_id, trace_id, span_id
  - _parse_retry_after: int, string, None, invalid
  - _set_retry_after_header
  - _resolve_llm_status_code: known codes, unknown, None
  - register_exception_handlers: all handler types
  - Individual handlers: ValidationException, AuthenticationError, PermissionDenied,
    NotFoundError, ConflictError, RateLimitError, BusinessException, BusinessError,
    ServiceUnavailableError, RecognitionTimeoutError, ExternalServiceError,
    Http404, ObjectDoesNotExist, DjangoPermissionDenied, NinjaValidationError,
    HttpError (429 and other), fallback Exception
"""

from __future__ import annotations

from typing import Any
from unittest.mock import MagicMock, PropertyMock, patch

import pytest
from django.http import Http404, HttpRequest, HttpResponse
from ninja import NinjaAPI
from ninja.errors import HttpError, ValidationError as NinjaValidationError

from apps.core.exceptions.handlers import (
    _attach_request_meta,
    _get_user_id,
    _log_extra,
    _parse_retry_after,
    _resolve_llm_status_code,
    _safe_log_value,
    register_exception_handlers,
)
from apps.core.exceptions.base import BusinessException, BusinessError
from apps.core.exceptions.common import (
    AuthenticationError,
    ConflictError,
    NotFoundError,
    PermissionDenied,
    RateLimitError,
    ValidationException,
)
from apps.core.exceptions.external import (
    ExternalServiceError,
    RecognitionTimeoutError,
    ServiceUnavailableError,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _mock_request(user_id=None, auth_id=None, path="/test", method="GET"):
    request = MagicMock(spec=HttpRequest)
    request.path = path
    request.method = method
    if user_id is not None:
        user = MagicMock()
        user.id = user_id
        request.user = user
    else:
        request.user = None
    if auth_id is not None:
        auth = MagicMock()
        auth.id = auth_id
        request.auth = auth
    else:
        request.auth = None
    request.headers = {}
    request.request_id = None
    return request


def _make_api():
    """Create a NinjaAPI with exception handlers registered."""
    api = NinjaAPI()
    register_exception_handlers(api)
    return api


# ===========================================================================
# _get_user_id
# ===========================================================================


class TestGetUserId:
    def test_from_user(self) -> None:
        req = _mock_request(user_id=42)
        assert _get_user_id(req) == 42

    def test_from_auth(self) -> None:
        req = _mock_request(auth_id="token-123")
        assert _get_user_id(req) == "token-123"

    def test_no_user(self) -> None:
        req = _mock_request()
        assert _get_user_id(req) is None

    def test_user_id_none(self) -> None:
        req = _mock_request()
        req.user = MagicMock()
        req.user.id = None
        assert _get_user_id(req) is None


# ===========================================================================
# _safe_log_value
# ===========================================================================


class TestSafeLogValue:
    def test_primitives(self) -> None:
        assert _safe_log_value(42) == 42
        assert _safe_log_value(3.14) == 3.14
        assert _safe_log_value(True) is True
        assert _safe_log_value(None) is None

    def test_short_string(self) -> None:
        assert _safe_log_value("hello") == "hello"

    def test_long_string_truncated(self) -> None:
        long = "a" * 300
        result = _safe_log_value(long)
        assert len(result) < 300
        assert result.endswith("...")

    def test_dict(self) -> None:
        result = _safe_log_value({"key": "value"})
        assert result == {"key": "value"}

    def test_dict_truncated_keys(self) -> None:
        d = {f"k{i}": i for i in range(100)}
        result = _safe_log_value(d)
        assert len(result) <= 50

    def test_list(self) -> None:
        result = _safe_log_value([1, 2, 3])
        assert result == [1, 2, 3]

    def test_list_truncated(self) -> None:
        l = list(range(100))
        result = _safe_log_value(l)
        assert len(result) <= 50

    def test_tuple(self) -> None:
        result = _safe_log_value((1, 2))
        assert isinstance(result, tuple)
        assert result == (1, 2)

    def test_nested_depth_limit(self) -> None:
        obj = {"a": {"b": {"c": {"d": {"e": "too deep"}}}}}
        result = _safe_log_value(obj)
        # Should not raise
        assert isinstance(result, dict)

    def test_unknown_type(self) -> None:
        class Custom:
            def __str__(self):
                return "custom"
        result = _safe_log_value(Custom())
        assert result == "custom"

    def test_long_string_value_in_dict(self) -> None:
        d = {"key": "a" * 300}
        result = _safe_log_value(d)
        assert result["key"].endswith("...")


# ===========================================================================
# _log_extra
# ===========================================================================


class TestLogExtra:
    def test_basic(self) -> None:
        req = _mock_request(user_id=1)
        result = _log_extra(req)
        assert result["path"] == "/test"
        assert result["method"] == "GET"
        assert result["user_id"] == 1

    def test_with_extra(self) -> None:
        req = _mock_request()
        result = _log_extra(req, code="ERR", detail="something")
        assert result["code"] == "ERR"
        assert result["detail"] == "something"

    def test_errors_sanitized(self) -> None:
        req = _mock_request()
        result = _log_extra(req, errors={"field": "a" * 300})
        assert isinstance(result["errors"], dict)


# ===========================================================================
# _attach_request_meta
# ===========================================================================


class TestAttachRequestMeta:
    def test_adds_request_id(self) -> None:
        req = MagicMock()
        req.request_id = "req-123"
        req.headers = {}
        payload: dict[str, Any] = {"code": "ERR"}
        with patch("apps.core.infrastructure.request_context.get_trace_ids", return_value=(None, None)):
            result = _attach_request_meta(req, payload)
        assert result["request_id"] == "req-123"
        assert result["trace_id"] == "req-123"

    def test_with_trace_ids(self) -> None:
        req = MagicMock()
        req.request_id = "req-123"
        req.headers = {}
        payload: dict[str, Any] = {"code": "ERR"}
        with patch("apps.core.infrastructure.request_context.get_trace_ids", return_value=("trace-abc", "span-def")):
            result = _attach_request_meta(req, payload)
        assert result["trace_id"] == "trace-abc"
        assert result["span_id"] == "span-def"

    def test_non_dict_payload(self) -> None:
        req = MagicMock()
        result = _attach_request_meta(req, "not a dict")
        assert result == "not a dict"

    def test_import_error_fallback(self) -> None:
        req = MagicMock()
        req.request_id = None
        req.headers = {"X-Request-ID": "hdr-id"}
        payload: dict[str, Any] = {}
        with patch.dict("sys.modules", {"apps.core.infrastructure.request_context": None}):
            result = _attach_request_meta(req, payload)
        assert result["request_id"] == "hdr-id"


# ===========================================================================
# _parse_retry_after
# ===========================================================================


class TestParseRetryAfter:
    def test_int(self) -> None:
        assert _parse_retry_after(30) == 30

    def test_string_int(self) -> None:
        assert _parse_retry_after("60") == 60

    def test_none(self) -> None:
        assert _parse_retry_after(None) is None

    def test_invalid_string(self) -> None:
        assert _parse_retry_after("abc") is None

    def test_zero(self) -> None:
        assert _parse_retry_after(0) == 0


# ===========================================================================
# _resolve_llm_status_code
# ===========================================================================


class TestResolveLlmStatusCode:
    def test_429(self) -> None:
        assert _resolve_llm_status_code(429) == 429

    def test_503(self) -> None:
        assert _resolve_llm_status_code(503) == 503

    def test_504(self) -> None:
        assert _resolve_llm_status_code(504) == 504

    def test_unknown_code(self) -> None:
        assert _resolve_llm_status_code(500) == 502

    def test_none(self) -> None:
        assert _resolve_llm_status_code(None) == 502


# ===========================================================================
# register_exception_handlers
# ===========================================================================


class TestRegisterExceptionHandlers:
    def test_registers_without_error(self) -> None:
        api = NinjaAPI()
        register_exception_handlers(api)  # should not raise

    def test_handlers_count(self) -> None:
        api = _make_api()
        # The handlers are registered via api.exception_handler decorator
        # We verify by triggering exceptions


# ===========================================================================
# Handler tests
# ===========================================================================


class TestValidationExceptionHandler:
    def test_returns_400(self) -> None:
        api = _make_api()
        req = _mock_request()
        exc = ValidationException("bad data", errors={"field": "required"})
        response = api._exception_handlers[type(exc)](req, exc)
        assert response.status_code == 400


class TestAuthenticationExceptionHandler:
    def test_returns_401(self) -> None:
        api = _make_api()
        req = _mock_request()
        exc = AuthenticationError("not authenticated")
        response = api._exception_handlers[type(exc)](req, exc)
        assert response.status_code == 401


class TestPermissionDeniedExceptionHandler:
    def test_returns_403(self) -> None:
        api = _make_api()
        req = _mock_request()
        exc = PermissionDenied("forbidden")
        response = api._exception_handlers[type(exc)](req, exc)
        assert response.status_code == 403


class TestNotFoundExceptionHandler:
    def test_returns_404(self) -> None:
        api = _make_api()
        req = _mock_request()
        exc = NotFoundError("not found")
        response = api._exception_handlers[type(exc)](req, exc)
        assert response.status_code == 404


class TestConflictExceptionHandler:
    def test_returns_409(self) -> None:
        api = _make_api()
        req = _mock_request()
        exc = ConflictError("conflict")
        response = api._exception_handlers[type(exc)](req, exc)
        assert response.status_code == 409


class TestRateLimitExceptionHandler:
    def test_returns_429_with_retry_after(self) -> None:
        api = _make_api()
        req = _mock_request()
        exc = RateLimitError("too many", errors={"retry_after": 30})
        response = api._exception_handlers[type(exc)](req, exc)
        assert response.status_code == 429
        assert response.headers.get("Retry-After") == "30"

    def test_returns_429_without_retry_after(self) -> None:
        api = _make_api()
        req = _mock_request()
        exc = RateLimitError("too many")
        response = api._exception_handlers[type(exc)](req, exc)
        assert response.status_code == 429


class TestBusinessExceptionHandler:
    def test_returns_custom_status(self) -> None:
        api = _make_api()
        req = _mock_request()
        exc = BusinessException("business error")
        exc.status = 422
        response = api._exception_handlers[type(exc)](req, exc)
        assert response.status_code == 422


class TestBusinessErrorHandler:
    def test_returns_custom_status(self) -> None:
        api = _make_api()
        req = _mock_request()
        exc = BusinessError("biz error", status=451)
        response = api._exception_handlers[type(exc)](req, exc)
        assert response.status_code == 451


class TestServiceUnavailableExceptionHandler:
    def test_returns_503(self) -> None:
        api = _make_api()
        req = _mock_request()
        exc = ServiceUnavailableError("service down")
        response = api._exception_handlers[type(exc)](req, exc)
        assert response.status_code == 503


class TestRecognitionTimeoutExceptionHandler:
    def test_returns_504(self) -> None:
        api = _make_api()
        req = _mock_request()
        exc = RecognitionTimeoutError("timeout")
        response = api._exception_handlers[type(exc)](req, exc)
        assert response.status_code == 504


class TestExternalServiceExceptionHandler:
    def test_returns_502(self) -> None:
        api = _make_api()
        req = _mock_request()
        exc = ExternalServiceError("external fail")
        response = api._exception_handlers[type(exc)](req, exc)
        assert response.status_code == 502


class TestHttp404Handler:
    def test_returns_404(self) -> None:
        api = _make_api()
        req = _mock_request(path="/not-found")
        exc = Http404("page not found")
        response = api._exception_handlers[Http404](req, exc)
        assert response.status_code == 404


class TestObjectDoesNotExistHandler:
    def test_returns_404(self) -> None:
        api = _make_api()
        req = _mock_request()
        from django.core.exceptions import ObjectDoesNotExist
        exc = ObjectDoesNotExist("object not found")
        response = api._exception_handlers[ObjectDoesNotExist](req, exc)
        assert response.status_code == 404


class TestDjangoPermissionDeniedHandler:
    def test_returns_403(self) -> None:
        api = _make_api()
        req = _mock_request()
        from django.core.exceptions import PermissionDenied as DjangoPermissionDenied
        exc = DjangoPermissionDenied("no access")
        response = api._exception_handlers[DjangoPermissionDenied](req, exc)
        assert response.status_code == 403


class TestNinjaValidationErrorHandler:
    def test_returns_422(self) -> None:
        api = _make_api()
        req = _mock_request()
        exc = MagicMock(spec=NinjaValidationError)
        exc.errors = [{"msg": "invalid"}]
        exc.__class__ = NinjaValidationError
        # Use the registered handler directly
        response = api._exception_handlers[NinjaValidationError](req, exc)
        assert response.status_code == 422


class TestHttpErrorHandler:
    def test_returns_status_code(self) -> None:
        api = _make_api()
        req = _mock_request()
        exc = HttpError(403, "forbidden")
        response = api._exception_handlers[HttpError](req, exc)
        assert response.status_code == 403

    def test_returns_429_rate_limit(self) -> None:
        api = _make_api()
        req = _mock_request()
        exc = HttpError(429, "rate limited")
        response = api._exception_handlers[HttpError](req, exc)
        assert response.status_code == 429


class TestFallbackExceptionHandler:
    def test_returns_500(self) -> None:
        api = _make_api()
        req = _mock_request()
        exc = RuntimeError("unexpected")
        response = api._exception_handlers[Exception](req, exc)
        assert response.status_code == 500


class TestLLMExceptionHandlers:
    """Test LLM-specific exception handlers if importable."""

    def test_llm_api_error_handler(self) -> None:
        try:
            from apps.core.llm.exceptions import LLMAPIError, LLMBackendUnavailableError, LLMTimeoutError
        except ImportError:
            pytest.skip("LLM exceptions not importable")

        api = _make_api()
        req = _mock_request()

        # LLMAPIError with known upstream
        exc = LLMAPIError("api error", status_code=429)
        response = api._exception_handlers[LLMAPIError](req, exc)
        assert response.status_code == 429

        # LLMAPIError with unknown upstream
        exc2 = LLMAPIError("api error")
        response2 = api._exception_handlers[LLMAPIError](req, exc2)
        assert response2.status_code == 502

        # LLMBackendUnavailableError
        exc3 = LLMBackendUnavailableError("unavailable")
        response3 = api._exception_handlers[LLMBackendUnavailableError](req, exc3)
        assert response3.status_code == 503

        # LLMTimeoutError
        exc4 = LLMTimeoutError("timeout")
        response4 = api._exception_handlers[LLMTimeoutError](req, exc4)
        assert response4.status_code == 504
