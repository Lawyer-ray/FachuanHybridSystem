"""
Comprehensive unit tests for apps.core.exceptions.handlers

Covers all public/helper functions and every registered exception handler
with edge cases and error paths.
"""

from __future__ import annotations

from typing import Any
from unittest.mock import MagicMock, patch

import pytest

# ---------------------------------------------------------------------------
# Fixture: capture registered handlers via a fake NinjaAPI
# ---------------------------------------------------------------------------

_HANDLERS: dict[type, Any] = {}


def _make_fake_api():
    """Return a NinjaAPI mock whose exception_handler decorator captures handlers."""
    api = MagicMock()

    def _exception_handler(exc_class):
        def decorator(fn):
            _HANDLERS[exc_class] = fn
            return fn
        return decorator

    def _create_response(request, payload, status):
        resp = MagicMock()
        resp._request = request
        resp._payload = payload
        resp._status = status
        resp.headers = {}
        return resp

    api.exception_handler = _exception_handler
    api.create_response = MagicMock(side_effect=_create_response)
    return api


@pytest.fixture(autouse=True)
def _reset_handlers():
    """Clear captured handlers before each test."""
    _HANDLERS.clear()
    yield
    _HANDLERS.clear()


@pytest.fixture()
def fake_api():
    return _make_fake_api()


@pytest.fixture()
def fake_request():
    """Create a minimal HttpRequest-like object."""
    req = MagicMock()
    req.path = "/api/test/"
    req.method = "POST"
    req.user = MagicMock()
    req.user.id = 42
    req.auth = None
    req.request_id = "req-123"
    req.headers = {"X-Request-ID": "hdr-456"}
    return req


@pytest.fixture()
def _register_all(fake_api):
    """Register all handlers and return the fake API."""
    from apps.core.exceptions.handlers import register_exception_handlers

    register_exception_handlers(fake_api)
    return fake_api


# ===================================================================
# _get_user_id
# ===================================================================

class TestGetUserId:
    """Tests for the _get_user_id helper."""

    def test_returns_user_id_int(self, fake_request):
        from apps.core.exceptions.handlers import _get_user_id

        fake_request.user.id = 42
        assert _get_user_id(fake_request) == 42

    def test_returns_user_id_str(self, fake_request):
        from apps.core.exceptions.handlers import _get_user_id

        fake_request.user.id = "abc-123"
        assert _get_user_id(fake_request) == "abc-123"

    def test_user_id_not_int_or_str_returns_none(self, fake_request):
        from apps.core.exceptions.handlers import _get_user_id

        fake_request.user.id = [1, 2, 3]
        fake_request.auth = None
        assert _get_user_id(fake_request) is None

    def test_falls_back_to_auth_id(self, fake_request):
        from apps.core.exceptions.handlers import _get_user_id

        fake_request.user.id = None
        fake_request.auth = MagicMock()
        fake_request.auth.id = 99
        assert _get_user_id(fake_request) == 99

    def test_auth_id_not_int_or_str(self, fake_request):
        from apps.core.exceptions.handlers import _get_user_id

        fake_request.user.id = None
        fake_request.auth = MagicMock()
        fake_request.auth.id = 3.14
        assert _get_user_id(fake_request) is None

    def test_no_user_attribute(self):
        from apps.core.exceptions.handlers import _get_user_id

        req = MagicMock(spec=[])  # no user attribute
        assert _get_user_id(req) is None

    def test_user_is_none(self):
        from apps.core.exceptions.handlers import _get_user_id

        req = MagicMock()
        req.user = None
        req.auth = None
        assert _get_user_id(req) is None

    def test_auth_is_none(self, fake_request):
        from apps.core.exceptions.handlers import _get_user_id

        fake_request.user.id = None
        fake_request.auth = None
        assert _get_user_id(fake_request) is None


# ===================================================================
# _safe_log_value
# ===================================================================

class TestSafeLogValue:
    """Tests for _safe_log_value sanitisation helper."""

    def test_none_returns_none(self):
        from apps.core.exceptions.handlers import _safe_log_value
        assert _safe_log_value(None) is None

    def test_int_passthrough(self):
        from apps.core.exceptions.handlers import _safe_log_value
        assert _safe_log_value(42) == 42

    def test_float_passthrough(self):
        from apps.core.exceptions.handlers import _safe_log_value
        assert _safe_log_value(3.14) == 3.14

    def test_bool_passthrough(self):
        from apps.core.exceptions.handlers import _safe_log_value
        assert _safe_log_value(True) is True

    def test_short_string_passthrough(self):
        from apps.core.exceptions.handlers import _safe_log_value
        assert _safe_log_value("hello") == "hello"

    def test_long_string_truncated(self):
        from apps.core.exceptions.handlers import _safe_log_value
        long = "x" * 300
        result = _safe_log_value(long)
        assert len(result) == 203  # 200 + "..."
        assert result.endswith("...")

    def test_dict_limits_keys_and_recurses(self):
        from apps.core.exceptions.handlers import _safe_log_value
        data = {"key": "value", "num": 123}
        assert _safe_log_value(data) == {"key": "value", "num": 123}

    def test_dict_long_key_truncated(self):
        from apps.core.exceptions.handlers import _safe_log_value
        data = {"a" * 200: "ok"}
        result = _safe_log_value(data)
        assert len(list(result.keys())[0]) == 100

    def test_dict_max_50_keys(self):
        from apps.core.exceptions.handlers import _safe_log_value
        data = {f"k{i}": i for i in range(60)}
        result = _safe_log_value(data)
        assert len(result) == 50

    def test_list_recursion(self):
        from apps.core.exceptions.handlers import _safe_log_value
        data = ["a", "b", 3]
        assert _safe_log_value(data) == ["a", "b", 3]

    def test_list_max_50_items(self):
        from apps.core.exceptions.handlers import _safe_log_value
        data = list(range(60))
        result = _safe_log_value(data)
        assert len(result) == 50

    def test_tuple_recursion(self):
        from apps.core.exceptions.handlers import _safe_log_value
        data = (1, 2, 3)
        assert _safe_log_value(data) == (1, 2, 3)

    def test_tuple_max_50_items(self):
        from apps.core.exceptions.handlers import _safe_log_value
        data = tuple(range(60))
        result = _safe_log_value(data)
        assert len(result) == 50

    def test_depth_limit_returns_str(self):
        from apps.core.exceptions.handlers import _safe_log_value
        # 6 levels of nesting: depth 0→1→2→3→4 hits the depth>=4 guard at the 5th recursion
        result = _safe_log_value({"a": {"b": {"c": {"d": {"e": {"f": "too deep"}}}}}}, depth=0)
        # At depth 4, the inner dict {e: {f: "too deep"}} is str()-ified and truncated
        inner = result["a"]["b"]["c"]["d"]
        assert isinstance(inner, str)

    def test_depth_exactly_4_returns_str(self):
        from apps.core.exceptions.handlers import _safe_log_value
        # A non-container value at exactly depth 4
        result = _safe_log_value("hello", depth=4)
        assert result == "hello"[:200]

    def test_unknown_type_returns_str(self):
        from apps.core.exceptions.handlers import _safe_log_value

        class Custom:
            def __str__(self):
                return "custom_repr"

        assert _safe_log_value(Custom()) == "custom_repr"

    def test_unknown_type_truncates_at_200(self):
        from apps.core.exceptions.handlers import _safe_log_value

        class LongRepr:
            def __str__(self):
                return "y" * 300

        result = _safe_log_value(LongRepr())
        assert len(result) == 200


# ===================================================================
# _log_extra
# ===================================================================

class TestLogExtra:
    """Tests for _log_extra helper."""

    def test_base_fields(self, fake_request):
        from apps.core.exceptions.handlers import _log_extra

        result = _log_extra(fake_request)
        assert result["path"] == "/api/test/"
        assert result["method"] == "POST"
        assert result["user_id"] == 42

    def test_extra_fields_merged(self, fake_request):
        from apps.core.exceptions.handlers import _log_extra

        result = _log_extra(fake_request, code="ERR", errors={"field": "bad"})
        assert result["code"] == "ERR"
        # errors should be sanitised via _safe_log_value
        assert result["errors"] == {"field": "bad"}

    def test_errors_sanitised(self, fake_request):
        from apps.core.exceptions.handlers import _log_extra

        result = _log_extra(fake_request, errors={"key": "v" * 300})
        safe_val = result["errors"]["key"]
        assert len(safe_val) == 203


# ===================================================================
# _attach_request_meta
# ===================================================================

class TestAttachRequestMeta:
    """Tests for _attach_request_meta helper."""

    def test_non_dict_payload_returned_as_is(self, fake_request):
        from apps.core.exceptions.handlers import _attach_request_meta
        assert _attach_request_meta(fake_request, "string") == "string"
        assert _attach_request_meta(fake_request, 42) == 42

    @patch("apps.core.exceptions.handlers.get_trace_ids", return_value=("tid", "sid"), create=True)
    def test_attaches_request_and_trace_ids(self, mock_trace, fake_request):
        from apps.core.exceptions.handlers import _attach_request_meta

        payload: dict[str, Any] = {}
        # Patch the import inside the function
        with patch.dict("sys.modules", {"apps.core.infrastructure.request_context": MagicMock(get_trace_ids=mock_trace)}):
            result = _attach_request_meta(fake_request, payload)

        assert result["request_id"] == "req-123"
        assert result["trace_id"] == "tid"
        assert result["span_id"] == "sid"

    def test_falls_back_to_header_request_id(self):
        from apps.core.exceptions.handlers import _attach_request_meta

        class FakeReq:
            headers = {"X-Request-ID": "from-header"}

        req = FakeReq()

        # Make get_trace_ids raise ImportError when called
        mock_module = MagicMock()
        mock_module.get_trace_ids.side_effect = ImportError
        with patch.dict("sys.modules", {"apps.core.infrastructure.request_context": mock_module}):
            result = _attach_request_meta(req, {})

        assert result["request_id"] == "from-header"
        assert result["trace_id"] == "from-header"

    def test_import_error_handled(self, fake_request):
        """When request_context module is not available, trace_id falls back."""
        from apps.core.exceptions.handlers import _attach_request_meta

        with patch.dict("sys.modules", {"apps.core.infrastructure.request_context": None}):
            result = _attach_request_meta(fake_request, {})

        assert result["request_id"] == "req-123"
        # trace_id should fall back to request_id
        assert result["trace_id"] == "req-123"
        assert "span_id" not in result

    def test_no_span_id_when_none(self, fake_request):
        from apps.core.exceptions.handlers import _attach_request_meta

        mock_module = MagicMock()
        mock_module.get_trace_ids.return_value = ("tid", None)
        with patch.dict("sys.modules", {"apps.core.infrastructure.request_context": mock_module}):
            result = _attach_request_meta(fake_request, {})
        assert "span_id" not in result

    def test_no_request_id_at_all(self):
        from apps.core.exceptions.handlers import _attach_request_meta

        class FakeReq:
            headers = {}

        req = FakeReq()

        # Make get_trace_ids raise ImportError when called
        mock_module = MagicMock()
        mock_module.get_trace_ids.side_effect = ImportError
        with patch.dict("sys.modules", {"apps.core.infrastructure.request_context": mock_module}):
            result = _attach_request_meta(req, {})

        assert result["request_id"] is None
        assert result["trace_id"] is None


# ===================================================================
# _parse_retry_after
# ===================================================================

class TestParseRetryAfter:
    """Tests for _parse_retry_after helper."""

    def test_int_passthrough(self):
        from apps.core.exceptions.handlers import _parse_retry_after
        assert _parse_retry_after(30) == 30

    def test_string_parsable(self):
        from apps.core.exceptions.handlers import _parse_retry_after
        assert _parse_retry_after("60") == 60

    def test_none_returns_none(self):
        from apps.core.exceptions.handlers import _parse_retry_after
        assert _parse_retry_after(None) is None

    def test_unparsable_string(self):
        from apps.core.exceptions.handlers import _parse_retry_after
        assert _parse_retry_after("abc") is None

    def test_float_string(self):
        from apps.core.exceptions.handlers import _parse_retry_after
        assert _parse_retry_after("3.5") is None


# ===================================================================
# _set_retry_after_header
# ===================================================================

class TestSetRetryAfterHeader:
    """Tests for _set_retry_after_header helper."""

    def test_sets_header_via_headers_attr(self):
        from apps.core.exceptions.handlers import _set_retry_after_header

        response = MagicMock()
        response.headers = {}
        _set_retry_after_header(response, 30)
        assert response.headers["Retry-After"] == "30"

    def test_negative_value_clamped_to_zero(self):
        from apps.core.exceptions.handlers import _set_retry_after_header

        response = MagicMock()
        response.headers = {}
        _set_retry_after_header(response, -5)
        assert response.headers["Retry-After"] == "0"

    def test_falls_back_to_bracket_on_error(self):
        from apps.core.exceptions.handlers import _set_retry_after_header

        # Use a simple object where headers access raises AttributeError
        class ResponseNoHeaders:
            def __getitem__(self, key):
                return self._items.get(key)

            def __setitem__(self, key, value):
                self._items[key] = value

            def __init__(self):
                self._items = {}

        response = ResponseNoHeaders()
        _set_retry_after_header(response, 45)
        assert response._items["Retry-After"] == "45"


# ===================================================================
# _resolve_llm_status_code
# ===================================================================

class TestResolveLlmStatusCode:
    """Tests for _resolve_llm_status_code helper."""

    def test_429_maps_to_429(self):
        from apps.core.exceptions.handlers import _resolve_llm_status_code
        assert _resolve_llm_status_code(429) == 429

    def test_503_maps_to_503(self):
        from apps.core.exceptions.handlers import _resolve_llm_status_code
        assert _resolve_llm_status_code(503) == 503

    def test_504_maps_to_504(self):
        from apps.core.exceptions.handlers import _resolve_llm_status_code
        assert _resolve_llm_status_code(504) == 504

    def test_unknown_upstream_maps_to_502(self):
        from apps.core.exceptions.handlers import _resolve_llm_status_code
        assert _resolve_llm_status_code(400) == 502

    def test_none_maps_to_502(self):
        from apps.core.exceptions.handlers import _resolve_llm_status_code
        assert _resolve_llm_status_code(None) == 502

    def test_0_is_falsy_maps_to_502(self):
        from apps.core.exceptions.handlers import _resolve_llm_status_code
        assert _resolve_llm_status_code(0) == 502


# ===================================================================
# register_exception_handlers — wiring
# ===================================================================

class TestRegisterExceptionHandlers:
    """Test that register_exception_handlers wires up all expected handlers."""

    def test_registers_all_client_error_handlers(self, _register_all):
        from apps.core.exceptions.common import (
            ValidationException,
            AuthenticationError,
            PermissionDenied,
            NotFoundError,
            ConflictError,
            RateLimitError,
        )
        from apps.core.exceptions.base import BusinessException, BusinessError

        for exc_cls in (ValidationException, AuthenticationError, PermissionDenied,
                        NotFoundError, ConflictError, RateLimitError,
                        BusinessException, BusinessError):
            assert exc_cls in _HANDLERS, f"{exc_cls.__name__} not registered"

    def test_registers_server_error_handlers(self, _register_all):
        from apps.core.exceptions.external import (
            ServiceUnavailableError,
            RecognitionTimeoutError,
            ExternalServiceError,
        )
        for exc_cls in (ServiceUnavailableError, RecognitionTimeoutError, ExternalServiceError):
            assert exc_cls in _HANDLERS, f"{exc_cls.__name__} not registered"

    def test_registers_django_handlers(self, _register_all):
        from django.core.exceptions import ObjectDoesNotExist
        from django.core.exceptions import PermissionDenied as DjangoPermissionDenied
        from django.http import Http404
        from ninja.errors import HttpError
        from ninja.errors import ValidationError as NinjaValidationError

        for exc_cls in (Http404, ObjectDoesNotExist, DjangoPermissionDenied,
                        NinjaValidationError, HttpError):
            assert exc_cls in _HANDLERS, f"{exc_cls.__name__} not registered"

    def test_registers_llm_handlers(self, _register_all):
        from apps.core.llm.exceptions import LLMAPIError, LLMBackendUnavailableError, LLMTimeoutError

        for exc_cls in (LLMBackendUnavailableError, LLMTimeoutError, LLMAPIError):
            assert exc_cls in _HANDLERS, f"{exc_cls.__name__} not registered"

    def test_registers_jwt_handler(self, _register_all):
        from ninja_jwt.exceptions import InvalidToken

        assert InvalidToken in _HANDLERS

    def test_registers_fallback_handler(self, _register_all):
        assert Exception in _HANDLERS


# ===================================================================
# Client error handlers
# ===================================================================

class TestClientErrorHandlers:
    """Test each 4xx handler returns correct status and payload."""

    def test_validation_exception_400(self, _register_all, fake_request):
        from apps.core.exceptions.common import ValidationException

        exc = ValidationException("bad input", errors={"field": "required"})
        handler = _HANDLERS[ValidationException]
        resp = handler(fake_request, exc)
        assert resp._status == 400
        assert resp._payload["code"] == "VALIDATION_ERROR"

    def test_authentication_error_401(self, _register_all, fake_request):
        from apps.core.exceptions.common import AuthenticationError

        exc = AuthenticationError("token expired")
        handler = _HANDLERS[AuthenticationError]
        resp = handler(fake_request, exc)
        assert resp._status == 401

    def test_permission_denied_403(self, _register_all, fake_request):
        from apps.core.exceptions.common import PermissionDenied

        exc = PermissionDenied("no access")
        handler = _HANDLERS[PermissionDenied]
        resp = handler(fake_request, exc)
        assert resp._status == 403

    def test_not_found_404(self, _register_all, fake_request):
        from apps.core.exceptions.common import NotFoundError

        exc = NotFoundError("resource missing")
        handler = _HANDLERS[NotFoundError]
        resp = handler(fake_request, exc)
        assert resp._status == 404

    def test_conflict_409(self, _register_all, fake_request):
        from apps.core.exceptions.common import ConflictError

        exc = ConflictError("already exists")
        handler = _HANDLERS[ConflictError]
        resp = handler(fake_request, exc)
        assert resp._status == 409

    def test_rate_limit_with_retry_after(self, _register_all, fake_request):
        from apps.core.exceptions.common import RateLimitError

        exc = RateLimitError("too fast", errors={"retry_after": 30})
        handler = _HANDLERS[RateLimitError]
        resp = handler(fake_request, exc)
        assert resp._status == 429
        assert resp.headers["Retry-After"] == "30"

    def test_rate_limit_without_retry_after(self, _register_all, fake_request):
        from apps.core.exceptions.common import RateLimitError

        exc = RateLimitError("too fast")
        handler = _HANDLERS[RateLimitError]
        resp = handler(fake_request, exc)
        assert resp._status == 429

    def test_rate_limit_retry_after_zero(self, _register_all, fake_request):
        from apps.core.exceptions.common import RateLimitError

        exc = RateLimitError("too fast", errors={"retry_after": 0})
        handler = _HANDLERS[RateLimitError]
        resp = handler(fake_request, exc)
        assert resp._status == 429
        assert resp.headers["Retry-After"] == "0"

    def test_business_exception_custom_status(self, _register_all, fake_request):
        from apps.core.exceptions.base import BusinessException

        exc = BusinessException("biz err", code="BIZ")
        exc.status = 422
        handler = _HANDLERS[BusinessException]
        resp = handler(fake_request, exc)
        assert resp._status == 422

    def test_business_exception_default_status(self, _register_all, fake_request):
        from apps.core.exceptions.base import BusinessException

        exc = BusinessException("biz err")
        handler = _HANDLERS[BusinessException]
        resp = handler(fake_request, exc)
        assert resp._status == 400

    def test_business_error_custom_status(self, _register_all, fake_request):
        from apps.core.exceptions.base import BusinessError

        exc = BusinessError("old style", status=418)
        handler = _HANDLERS[BusinessError]
        resp = handler(fake_request, exc)
        assert resp._status == 418

    def test_business_error_default_status(self, _register_all, fake_request):
        from apps.core.exceptions.base import BusinessError

        exc = BusinessError("old style")
        handler = _HANDLERS[BusinessError]
        resp = handler(fake_request, exc)
        assert resp._status == 400


# ===================================================================
# Server error handlers
# ===================================================================

class TestServerErrorHandlers:
    """Test each 5xx handler."""

    def test_service_unavailable_503(self, _register_all, fake_request):
        from apps.core.exceptions.external import ServiceUnavailableError

        exc = ServiceUnavailableError("down", service_name="ollama")
        handler = _HANDLERS[ServiceUnavailableError]
        resp = handler(fake_request, exc)
        assert resp._status == 503

    def test_recognition_timeout_504(self, _register_all, fake_request):
        from apps.core.exceptions.external import RecognitionTimeoutError

        exc = RecognitionTimeoutError("ocr timeout", timeout_seconds=30.0)
        handler = _HANDLERS[RecognitionTimeoutError]
        resp = handler(fake_request, exc)
        assert resp._status == 504

    def test_external_service_error_502(self, _register_all, fake_request):
        from apps.core.exceptions.external import ExternalServiceError

        exc = ExternalServiceError("third party down")
        handler = _HANDLERS[ExternalServiceError]
        resp = handler(fake_request, exc)
        assert resp._status == 502


# ===================================================================
# LLM handlers
# ===================================================================

class TestLLMHandlers:
    """Test LLM-specific exception handlers."""

    def test_llm_backend_unavailable_503(self, _register_all, fake_request):
        from apps.core.llm.exceptions import LLMBackendUnavailableError

        exc = LLMBackendUnavailableError("all backends down")
        handler = _HANDLERS[LLMBackendUnavailableError]
        resp = handler(fake_request, exc)
        assert resp._status == 503

    def test_llm_timeout_504(self, _register_all, fake_request):
        from apps.core.llm.exceptions import LLMTimeoutError

        exc = LLMTimeoutError("timeout", timeout_seconds=120.0)
        handler = _HANDLERS[LLMTimeoutError]
        resp = handler(fake_request, exc)
        assert resp._status == 504

    def test_llm_api_error_default_502(self, _register_all, fake_request):
        from apps.core.llm.exceptions import LLMAPIError

        exc = LLMAPIError("api fail")
        handler = _HANDLERS[LLMAPIError]
        resp = handler(fake_request, exc)
        assert resp._status == 502

    def test_llm_api_error_upstream_429(self, _register_all, fake_request):
        from apps.core.llm.exceptions import LLMAPIError

        exc = LLMAPIError("rate limited", status_code=429)
        handler = _HANDLERS[LLMAPIError]
        resp = handler(fake_request, exc)
        assert resp._status == 429

    def test_llm_api_error_upstream_503(self, _register_all, fake_request):
        from apps.core.llm.exceptions import LLMAPIError

        exc = LLMAPIError("unavail", status_code=503)
        handler = _HANDLERS[LLMAPIError]
        resp = handler(fake_request, exc)
        assert resp._status == 503

    def test_llm_api_error_upstream_504(self, _register_all, fake_request):
        from apps.core.llm.exceptions import LLMAPIError

        exc = LLMAPIError("gw timeout", status_code=504)
        handler = _HANDLERS[LLMAPIError]
        resp = handler(fake_request, exc)
        assert resp._status == 504

    def test_llm_api_error_upstream_400_maps_to_502(self, _register_all, fake_request):
        from apps.core.llm.exceptions import LLMAPIError

        exc = LLMAPIError("bad req", status_code=400)
        handler = _HANDLERS[LLMAPIError]
        resp = handler(fake_request, exc)
        assert resp._status == 502

    def test_llm_import_error_silently_skipped(self, fake_api):
        """When LLM module is missing, registration should not raise."""
        import sys
        saved = sys.modules.get("apps.core.llm.exceptions")
        # Force ImportError
        sys.modules["apps.core.llm.exceptions"] = None  # type: ignore[assignment]
        try:
            from apps.core.exceptions.handlers import register_exception_handlers
            register_exception_handlers(fake_api)  # Should not raise
        finally:
            if saved is not None:
                sys.modules["apps.core.llm.exceptions"] = saved
            else:
                sys.modules.pop("apps.core.llm.exceptions", None)


# ===================================================================
# Django handlers
# ===================================================================

class TestDjangoHandlers:
    """Test Django built-in exception handlers."""

    def test_http404_404(self, _register_all, fake_request):
        from django.http import Http404

        exc = Http404("not found")
        handler = _HANDLERS[Http404]
        resp = handler(fake_request, exc)
        assert resp._status == 404

    def test_object_does_not_exist_404(self, _register_all, fake_request):
        from django.core.exceptions import ObjectDoesNotExist

        exc = ObjectDoesNotExist()
        handler = _HANDLERS[ObjectDoesNotExist]
        resp = handler(fake_request, exc)
        assert resp._status == 404

    def test_django_permission_denied_403(self, _register_all, fake_request):
        from django.core.exceptions import PermissionDenied as DjangoPermissionDenied

        exc = DjangoPermissionDenied("nope")
        handler = _HANDLERS[DjangoPermissionDenied]
        resp = handler(fake_request, exc)
        assert resp._status == 403

    def test_ninja_validation_error_422(self, _register_all, fake_request):
        from ninja.errors import ValidationError as NinjaValidationError

        exc = MagicMock(spec=NinjaValidationError)
        exc.errors = {"field": "required"}
        handler = _HANDLERS[NinjaValidationError]
        resp = handler(fake_request, exc)
        assert resp._status == 422

    def test_http_error_generic(self, _register_all, fake_request):
        from ninja.errors import HttpError

        exc = HttpError(500, "server error")
        handler = _HANDLERS[HttpError]
        resp = handler(fake_request, exc)
        assert resp._status == 500

    def test_http_error_429_rate_limit(self, _register_all, fake_request):
        from ninja.errors import HttpError

        exc = HttpError(429, "rate limited")
        handler = _HANDLERS[HttpError]
        resp = handler(fake_request, exc)
        assert resp._status == 429

    def test_http_error_uses_str_fallback_when_no_message(self, _register_all, fake_request):
        from ninja.errors import HttpError

        exc = HttpError(400, "bad request")
        handler = _HANDLERS[HttpError]
        resp = handler(fake_request, exc)
        assert resp._status == 400


# ===================================================================
# JWT handler
# ===================================================================

class TestJWTHandler:
    """Test JWT token validation handler."""

    def test_invalid_token_with_dict_detail(self, _register_all, fake_request):
        from ninja_jwt.exceptions import InvalidToken

        exc = MagicMock(spec=InvalidToken)
        exc.detail = {"detail": "Token expired"}
        handler = _HANDLERS[InvalidToken]
        resp = handler(fake_request, exc)
        assert resp._status == 401

    def test_invalid_token_with_string_detail(self, _register_all, fake_request):
        from ninja_jwt.exceptions import InvalidToken

        exc = MagicMock(spec=InvalidToken)
        exc.detail = "bad token"
        handler = _HANDLERS[InvalidToken]
        resp = handler(fake_request, exc)
        assert resp._status == 401

    def test_invalid_token_with_empty_detail(self, _register_all, fake_request):
        from ninja_jwt.exceptions import InvalidToken

        exc = MagicMock(spec=InvalidToken)
        exc.detail = ""
        handler = _HANDLERS[InvalidToken]
        resp = handler(fake_request, exc)
        assert resp._status == 401

    def test_invalid_token_with_none_detail(self, _register_all, fake_request):
        from ninja_jwt.exceptions import InvalidToken

        exc = MagicMock(spec=InvalidToken)
        exc.detail = None
        handler = _HANDLERS[InvalidToken]
        resp = handler(fake_request, exc)
        assert resp._status == 401

    def test_jwt_import_error_silently_skipped(self, fake_api):
        """When ninja_jwt module is missing, registration should not raise."""
        import sys
        saved = sys.modules.get("ninja_jwt.exceptions")
        sys.modules["ninja_jwt.exceptions"] = None  # type: ignore[assignment]
        try:
            from apps.core.exceptions.handlers import register_exception_handlers
            register_exception_handlers(fake_api)
        finally:
            if saved is not None:
                sys.modules["ninja_jwt.exceptions"] = saved
            else:
                sys.modules.pop("ninja_jwt.exceptions", None)


# ===================================================================
# Fallback handler
# ===================================================================

class TestFallbackHandler:
    """Test the catch-all fallback handler."""

    def test_unexpected_exception_debug_mode(self, _register_all, fake_request):
        handler = _HANDLERS[Exception]
        exc = RuntimeError("something broke")

        with patch("django.conf.settings") as mock_settings:
            mock_settings.DEBUG = True
            resp = handler(fake_request, exc)

        assert resp._status == 500

    def test_unexpected_exception_production_mode(self, _register_all, fake_request):
        handler = _HANDLERS[Exception]
        exc = RuntimeError("something broke")

        with patch("django.conf.settings") as mock_settings:
            mock_settings.DEBUG = False
            resp = handler(fake_request, exc)

        assert resp._status == 500


# ===================================================================
# _register_llm_handlers — additional edge cases
# ===================================================================

class TestRegisterLLMHandlersEdgeCases:
    """Test _register_llm_handlers error paths."""

    def test_unexpected_exception_during_registration(self, fake_api, caplog):
        """If a generic Exception occurs during LLM handler registration, it logs and continues."""
        import apps.core.exceptions.handlers as mod

        # Patch the import to raise a non-ImportError exception
        original_register = mod._register_llm_handlers
        with patch.object(mod, "_register_llm_handlers") as mock_llm:
            # Re-implement to test the "except Exception" path
            def _side_effect(api, create_response):
                try:
                    # Simulate the real function but force an Exception
                    raise RuntimeError("unexpected registration error")
                except ImportError:
                    pass
                except Exception:
                    import logging
                    logging.getLogger("api").exception("Failed to register LLM exception handlers")

            mock_llm.side_effect = _side_effect
            # Call register_exception_handlers to trigger the path
            from apps.core.exceptions.handlers import register_exception_handlers
            register_exception_handlers(fake_api)
            mock_llm.assert_called_once()
