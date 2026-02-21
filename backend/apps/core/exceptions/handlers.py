"""
全局异常处理器
"""

from __future__ import annotations

import logging
from collections.abc import Callable
from typing import Any

from django.core.exceptions import ObjectDoesNotExist
from django.core.exceptions import PermissionDenied as DjangoPermissionDenied
from django.http import Http404, HttpRequest, HttpResponse
from ninja import NinjaAPI
from ninja.errors import HttpError
from ninja.errors import ValidationError as NinjaValidationError

from .base import BusinessError, BusinessException
from .common import (
    AuthenticationError,
    ConflictError,
    NotFoundError,
    PermissionDenied,
    RateLimitError,
    ValidationException,
)
from .external import ExternalServiceError, RecognitionTimeoutError, ServiceUnavailableError

logger = logging.getLogger("api")

__all__: list[str] = ["register_exception_handlers"]

# Type alias for the create_response callable used across handler registrations
_CreateResponse = Callable[..., HttpResponse]


# ---------------------------------------------------------------------------
# 辅助函数
# ---------------------------------------------------------------------------


def _get_user_id(request: HttpRequest) -> int | str | None:
    user = getattr(request, "user", None)
    user_id: Any = getattr(user, "id", None) if user is not None else None
    if isinstance(user_id, (int, str)):
        return user_id
    auth = getattr(request, "auth", None)
    auth_id: Any = getattr(auth, "id", None) if auth is not None else None
    if isinstance(auth_id, (int, str)):
        return auth_id
    return None


def _safe_log_value(value: Any, *, depth: int = 0) -> Any:
    if depth >= 4:
        return str(value)[:200]
    if value is None:
        return None
    if isinstance(value, (str, int, float, bool)):
        if isinstance(value, str) and len(value) > 200:
            return value[:200] + "..."
        return value
    if isinstance(value, dict):
        safe: dict[str, Any] = {}
        for k, v in list(value.items())[:50]:
            safe[str(k)[:100]] = _safe_log_value(v, depth=depth + 1)
        return safe
    if isinstance(value, list):
        return [_safe_log_value(v, depth=depth + 1) for v in value[:50]]
    if isinstance(value, tuple):
        return tuple(_safe_log_value(v, depth=depth + 1) for v in value[:50])
    return str(value)[:200]


def _log_extra(request: HttpRequest, **extra: Any) -> dict[str, Any]:
    base: dict[str, Any] = {
        "path": getattr(request, "path", None),
        "method": getattr(request, "method", None),
        "user_id": _get_user_id(request),
    }
    if "errors" in extra:
        extra["errors"] = _safe_log_value(extra.get("errors"))
    base.update(extra)
    return base


def _attach_request_meta(request: HttpRequest, payload: Any) -> Any:
    """Attach request metadata (request_id, trace_id) to response payload."""
    if not isinstance(payload, dict):
        return payload
    request_id = getattr(request, "request_id", None) or getattr(request, "headers", {}).get("X-Request-ID")
    try:
        from apps.core.infrastructure.request_context import get_trace_ids

        trace_id, span_id = get_trace_ids()
    except Exception:
        _meta_logger = logging.getLogger(__name__)
        _meta_logger.exception("Failed to get trace IDs")
        trace_id, span_id = None, None
    payload.setdefault("request_id", request_id)
    payload.setdefault("trace_id", trace_id or request_id)
    if span_id:
        payload.setdefault("span_id", span_id)
    return payload


def _parse_retry_after(raw: Any) -> int | None:
    """Parse retry_after value from RateLimitError errors dict."""
    if isinstance(raw, int):
        return raw
    if raw is not None:
        try:
            return int(raw)
        except (TypeError, ValueError):
            return None
    return None


def _set_retry_after_header(response: HttpResponse, retry_after: int) -> None:
    """Set Retry-After response header."""
    try:
        response.headers["Retry-After"] = str(max(0, retry_after))
    except Exception:
        logger.exception("Failed to set Retry-After header")
        response["Retry-After"] = str(max(0, retry_after))


def _resolve_llm_status_code(upstream: int | None) -> int:
    """Resolve HTTP status code for LLM API errors based on upstream status."""
    upstream_map = {429: 429, 503: 503, 504: 504}
    return upstream_map.get(upstream, 502) if upstream else 502


# ---------------------------------------------------------------------------
# 注册函数
# ---------------------------------------------------------------------------


def register_exception_handlers(api: NinjaAPI) -> None:
    """注册全局异常处理器"""

    def _create_response(request: HttpRequest, payload: Any, *, status: int) -> HttpResponse:
        payload = _attach_request_meta(request, payload)
        return api.create_response(request, payload, status=status)

    _register_business_handlers(api, _create_response)

    try:
        from apps.core.llm.exceptions import LLMAPIError, LLMBackendUnavailableError, LLMTimeoutError

        @api.exception_handler(LLMBackendUnavailableError)
        def handle_llm_backend_unavailable_error(
            request: HttpRequest, exc: LLMBackendUnavailableError
        ) -> HttpResponse:
            logger.error(
                "LLM backend unavailable: %s",
                exc.message,
                extra=_log_extra(request, code=exc.code, errors=exc.errors, service_name="llm"),
            )
            payload = exc.to_dict()
            payload.setdefault("errors", {})
            payload["errors"].setdefault("service", "llm")
            return _create_response(request, payload, status=503)

        @api.exception_handler(LLMTimeoutError)
        def handle_llm_timeout_error(request: HttpRequest, exc: LLMTimeoutError) -> HttpResponse:
            logger.error(
                "LLM request timeout: %s",
                exc.message,
                extra=_log_extra(request, code=exc.code, errors=exc.errors),
            )
            return _create_response(request, exc.to_dict(), status=504)

        @api.exception_handler(LLMAPIError)
        def handle_llm_api_error(request: HttpRequest, exc: LLMAPIError) -> HttpResponse:
            upstream = getattr(exc, "status_code", None)
            status_code = _resolve_llm_status_code(upstream)
            logger.error(
                "LLM API error: %s",
                exc.message,
                extra=_log_extra(request, code=exc.code, errors=exc.errors, status_code=status_code, upstream=upstream),
            )
            return _create_response(request, exc.to_dict(), status=status_code)

    except ImportError:
        pass
    except Exception:
        logger.exception("Failed to register LLM exception handlers")

    _register_django_handlers(api, _create_response)
    _register_jwt_handler(api, _create_response)
    _register_fallback_handler(api, _create_response)


def _register_business_handlers(api: NinjaAPI, create_response: _CreateResponse) -> None:
    """注册业务异常处理器"""
    _register_client_error_handlers(api, create_response)
    _register_server_error_handlers(api, create_response)


def _register_client_error_handlers(api: NinjaAPI, create_response: _CreateResponse) -> None:
    """注册 4xx 业务异常处理器"""

    @api.exception_handler(ValidationException)
    def handle_validation_exception(request: HttpRequest, exc: ValidationException) -> HttpResponse:
        logger.info("Validation failed: %s", exc.message, extra=_log_extra(request, code=exc.code, errors=exc.errors))
        return create_response(request, exc.to_dict(), status=400)

    @api.exception_handler(AuthenticationError)
    def handle_authentication_error(request: HttpRequest, exc: AuthenticationError) -> HttpResponse:
        logger.warning("Authentication failed: %s", exc.message, extra=_log_extra(request, code=exc.code))
        return create_response(request, exc.to_dict(), status=401)

    @api.exception_handler(PermissionDenied)
    def handle_permission_denied_exception(request: HttpRequest, exc: PermissionDenied) -> HttpResponse:
        logger.warning("Permission denied: %s", exc.message, extra=_log_extra(request, code=exc.code))
        return create_response(request, exc.to_dict(), status=403)

    @api.exception_handler(NotFoundError)
    def handle_not_found_exception(request: HttpRequest, exc: NotFoundError) -> HttpResponse:
        logger.info("Not found: %s", exc.message, extra=_log_extra(request, code=exc.code))
        return create_response(request, exc.to_dict(), status=404)

    @api.exception_handler(ConflictError)
    def handle_conflict_exception(request: HttpRequest, exc: ConflictError) -> HttpResponse:
        logger.info("Conflict: %s", exc.message, extra=_log_extra(request, code=exc.code, errors=exc.errors))
        return create_response(request, exc.to_dict(), status=409)

    @api.exception_handler(RateLimitError)
    def handle_rate_limit_exception(request: HttpRequest, exc: RateLimitError) -> HttpResponse:
        logger.warning("Rate limited: %s", exc.message, extra=_log_extra(request, code=exc.code))
        response = create_response(request, exc.to_dict(), status=429)
        retry_after = _parse_retry_after((exc.errors or {}).get("retry_after"))
        if retry_after is not None:
            _set_retry_after_header(response, retry_after)
        return response

    @api.exception_handler(BusinessException)
    def handle_business_exception(request: HttpRequest, exc: BusinessException) -> HttpResponse:
        logger.warning("Business error: %s", exc.message, extra=_log_extra(request, code=exc.code, errors=exc.errors))
        status = int(getattr(exc, "status", 400))
        return create_response(request, exc.to_dict(), status=status)

    @api.exception_handler(BusinessError)
    def handle_business_error(request: HttpRequest, exc: BusinessError) -> HttpResponse:
        logger.warning("BusinessError: %s - %s", exc.code, exc.message, extra=_log_extra(request))
        status = int(getattr(exc, "status", 400))
        return create_response(request, exc.to_dict(), status=status)


def _register_server_error_handlers(api: NinjaAPI, create_response: _CreateResponse) -> None:
    """注册 5xx 业务异常处理器"""

    @api.exception_handler(ServiceUnavailableError)
    def handle_service_unavailable_error(request: HttpRequest, exc: ServiceUnavailableError) -> HttpResponse:
        logger.error(
            "Service unavailable: %s",
            exc.message,
            extra=_log_extra(
                request, code=exc.code, errors=exc.errors,
                service_name=getattr(exc, "service_name", None),
            ),
        )
        return create_response(request, exc.to_dict(), status=503)

    @api.exception_handler(RecognitionTimeoutError)
    def handle_recognition_timeout_error(request: HttpRequest, exc: RecognitionTimeoutError) -> HttpResponse:
        logger.error(
            "Recognition timeout: %s",
            exc.message,
            extra=_log_extra(
                request, code=exc.code, errors=exc.errors,
                timeout_seconds=getattr(exc, "timeout_seconds", None),
            ),
        )
        return create_response(request, exc.to_dict(), status=504)

    @api.exception_handler(ExternalServiceError)
    def handle_external_service_error(request: HttpRequest, exc: ExternalServiceError) -> HttpResponse:
        logger.error(
            "External service error: %s",
            exc.message,
            extra=_log_extra(request, code=exc.code, errors=exc.errors),
        )
        return create_response(request, exc.to_dict(), status=502)


def _register_llm_handlers(api: NinjaAPI, create_response: _CreateResponse) -> None:
    """注册 LLM 相关异常处理器（可选依赖，ImportError 时静默跳过）"""
    try:
        from apps.core.llm.exceptions import LLMAPIError, LLMBackendUnavailableError, LLMTimeoutError

        @api.exception_handler(LLMBackendUnavailableError)
        def handle_llm_backend_unavailable_error(
            request: HttpRequest, exc: LLMBackendUnavailableError
        ) -> HttpResponse:
            logger.error(
                "LLM backend unavailable: %s",
                exc.message,
                extra=_log_extra(request, code=exc.code, errors=exc.errors, service_name="llm"),
            )
            payload = exc.to_dict()
            payload.setdefault("errors", {})
            payload["errors"].setdefault("service", "llm")
            return create_response(request, payload, status=503)

        @api.exception_handler(LLMTimeoutError)
        def handle_llm_timeout_error(request: HttpRequest, exc: LLMTimeoutError) -> HttpResponse:
            logger.error(
                "LLM request timeout: %s",
                exc.message,
                extra=_log_extra(request, code=exc.code, errors=exc.errors),
            )
            return create_response(request, exc.to_dict(), status=504)

        @api.exception_handler(LLMAPIError)
        def handle_llm_api_error(request: HttpRequest, exc: LLMAPIError) -> HttpResponse:
            upstream = getattr(exc, "status_code", None)
            status_code = _resolve_llm_status_code(upstream)
            logger.error(
                "LLM API error: %s",
                exc.message,
                extra=_log_extra(request, code=exc.code, errors=exc.errors, status_code=status_code, upstream=upstream),
            )
            return create_response(request, exc.to_dict(), status=status_code)

    except ImportError:
        pass
    except Exception:
        logger.exception("Failed to register LLM exception handlers")


def _register_django_handlers(api: NinjaAPI, create_response: _CreateResponse) -> None:
    """注册 Django 内置异常处理器"""

    @api.exception_handler(Http404)
    def handle_404(request: HttpRequest, exc: Http404) -> HttpResponse:
        logger.info("404 Not Found: %s", request.path)
        return create_response(
            request,
            {"code": "NOT_FOUND", "message": "资源不存在", "error": "资源不存在", "errors": {}},
            status=404,
        )

    @api.exception_handler(ObjectDoesNotExist)
    def handle_object_not_exist(request: HttpRequest, exc: ObjectDoesNotExist) -> HttpResponse:
        logger.info("Object not found: %s", request.path)
        return create_response(
            request,
            {"code": "NOT_FOUND", "message": "资源不存在", "error": "资源不存在", "errors": {}},
            status=404,
        )

    @api.exception_handler(DjangoPermissionDenied)
    def handle_django_permission_denied(request: HttpRequest, exc: DjangoPermissionDenied) -> HttpResponse:
        logger.warning("Permission denied: %s", request.path, extra=_log_extra(request))
        return create_response(
            request,
            {"code": "PERMISSION_DENIED", "message": "无权限访问", "error": "无权限访问", "errors": {}},
            status=403,
        )

    @api.exception_handler(NinjaValidationError)
    def handle_ninja_validation_error(request: HttpRequest, exc: NinjaValidationError) -> HttpResponse:
        logger.info("Validation error: %s", request.path, extra=_log_extra(request, errors=exc.errors))
        return create_response(
            request,
            {"code": "VALIDATION_ERROR", "message": "数据校验失败", "error": "数据校验失败", "errors": exc.errors},
            status=422,
        )

    @api.exception_handler(HttpError)
    def handle_http_error(request: HttpRequest, exc: HttpError) -> HttpResponse:
        logger.warning("HTTP Error %s: %s", exc.status_code, request.path)
        error_message = getattr(exc, "message", None) or str(exc)
        if int(exc.status_code) == 429:
            return create_response(
                request,
                {"code": "RATE_LIMIT_ERROR", "message": error_message, "error": error_message, "errors": {}},
                status=429,
            )
        return create_response(
            request,
            {"code": "HTTP_ERROR", "message": error_message, "error": error_message, "errors": {}},
            status=int(exc.status_code),
        )


def _register_jwt_handler(api: NinjaAPI, create_response: _CreateResponse) -> None:
    """注册 JWT 异常处理器（可选依赖，ImportError 时静默跳过）"""
    try:
        from ninja_jwt.exceptions import InvalidToken

        @api.exception_handler(InvalidToken)
        def handle_invalid_token(request: HttpRequest, exc: InvalidToken) -> HttpResponse:
            logger.info("Invalid token: %s", request.path)
            detail = getattr(exc, "detail", {})
            if isinstance(detail, dict):
                error_msg = str(detail.get("detail", "令牌无效或已过期"))
            else:
                error_msg = str(detail) if detail else "令牌无效或已过期"
            return create_response(
                request,
                {"code": "INVALID_TOKEN", "message": error_msg, "error": error_msg, "errors": {}},
                status=401,
            )

    except ImportError:
        pass


def _register_fallback_handler(api: NinjaAPI, create_response: _CreateResponse) -> None:
    """注册兜底异常处理器"""

    @api.exception_handler(Exception)
    def handle_unexpected_exception(request: HttpRequest, exc: Exception) -> HttpResponse:
        logger.error(
            "Unexpected error: %s",
            exc,
            exc_info=True,
            extra=_log_extra(request),
        )
        from django.conf import settings

        message = str(exc) if settings.DEBUG else "系统错误,请稍后重试"
        return create_response(
            request,
            {"code": "INTERNAL_ERROR", "message": message, "error": message, "errors": {}},
            status=500,
        )
