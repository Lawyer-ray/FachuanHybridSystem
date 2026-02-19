"""
全局异常处理器
"""

from __future__ import annotations

import logging
from typing import Any

from django.core.exceptions import ObjectDoesNotExist
from django.core.exceptions import PermissionDenied as DjangoPermissionDenied
from django.http import Http404
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


def register_exception_handlers(api: NinjaAPI) -> None:
    """注册全局异常处理器"""
    _register_business_handlers(api)
    _register_django_handlers(api)
    _register_fallback_handler(api)


def _register_business_handlers(api: NinjaAPI) -> None:
    """注册业务异常处理器"""
    _register_client_error_handlers(api)
    _register_server_error_handlers(api)


def _register_client_error_handlers(api: NinjaAPI) -> None:
    """注册 4xx 业务异常处理器"""

    @api.exception_handler(ValidationException)
    def handle_validation_exception(request: Any, exc: ValidationException) -> Any:
        logger.info(f"验证失败: {exc.message}", extra={"code": exc.code, "errors": exc.errors, "path": request.path})
        return api.create_response(request, exc.to_dict(), status=400)

    @api.exception_handler(AuthenticationError)
    def handle_authentication_error(request: Any, exc: AuthenticationError) -> Any:
        logger.warning(f"认证失败: {exc.message}", extra={"code": exc.code, "path": request.path})
        return api.create_response(request, exc.to_dict(), status=401)

    @api.exception_handler(PermissionDenied)
    def handle_permission_denied_exception(request: Any, exc: PermissionDenied) -> Any:
        logger.warning(
            f"权限拒绝: {exc.message}",
            extra={
                "code": exc.code,
                "path": request.path,
                "user_id": getattr(request.auth, "id", None) if hasattr(request, "auth") else None,
            },
        )
        return api.create_response(request, exc.to_dict(), status=403)

    @api.exception_handler(NotFoundError)
    def handle_not_found_exception(request: Any, exc: NotFoundError) -> Any:
        logger.info(f"资源不存在: {exc.message}", extra={"code": exc.code, "path": request.path})
        return api.create_response(request, exc.to_dict(), status=404)

    @api.exception_handler(ConflictError)
    def handle_conflict_exception(request: Any, exc: ConflictError) -> Any:
        logger.info(f"资源冲突: {exc.message}", extra={"code": exc.code, "errors": exc.errors, "path": request.path})
        return api.create_response(request, exc.to_dict(), status=409)

    @api.exception_handler(RateLimitError)
    def handle_rate_limit_exception(request: Any, exc: RateLimitError) -> Any:
        logger.warning(
            f"频率限制: {exc.message}",
            extra={
                "code": exc.code,
                "path": request.path,
                "user_id": getattr(request.auth, "id", None) if hasattr(request, "auth") else None,
            },
        )
        return api.create_response(request, exc.to_dict(), status=429)

    @api.exception_handler(BusinessException)
    def handle_business_exception(request: Any, exc: BusinessException) -> Any:
        logger.warning(f"业务异常: {exc.message}", extra={"code": exc.code, "errors": exc.errors, "path": request.path})
        return api.create_response(request, exc.to_dict(), status=400)

    @api.exception_handler(BusinessError)
    def handle_business_error(request: Any, exc: BusinessError) -> Any:
        logger.warning(
            f"BusinessError: {exc.code} - {exc.message}", extra={"path": request.path, "method": request.method}
        )
        response: dict[str, Any] = {"success": False, "code": exc.code, "message": exc.message}
        if hasattr(exc, "errors") and exc.errors:
            response["errors"] = exc.errors
        status = getattr(exc, "status", 400)
        return api.create_response(request, response, status=status)


def _register_server_error_handlers(api: NinjaAPI) -> None:
    """注册 5xx 业务异常处理器"""

    @api.exception_handler(ServiceUnavailableError)
    def handle_service_unavailable_error(request: Any, exc: ServiceUnavailableError) -> Any:
        logger.error(
            f"服务不可用: {exc.message}",
            extra={
                "code": exc.code,
                "errors": exc.errors,
                "path": request.path,
                "service_name": getattr(exc, "service_name", None),
            },
        )
        return api.create_response(request, exc.to_dict(), status=503)

    @api.exception_handler(RecognitionTimeoutError)
    def handle_recognition_timeout_error(request: Any, exc: RecognitionTimeoutError) -> Any:
        logger.error(
            f"识别超时: {exc.message}",
            extra={
                "code": exc.code,
                "errors": exc.errors,
                "path": request.path,
                "timeout_seconds": getattr(exc, "timeout_seconds", None),
            },
        )
        return api.create_response(request, exc.to_dict(), status=504)

    @api.exception_handler(ExternalServiceError)
    def handle_external_service_error(request: Any, exc: ExternalServiceError) -> Any:
        logger.error(
            f"外部服务错误: {exc.message}", extra={"code": exc.code, "errors": exc.errors, "path": request.path}
        )
        return api.create_response(request, exc.to_dict(), status=502)


def _register_django_handlers(api: NinjaAPI) -> None:
    """注册 Django 内置异常处理器"""

    @api.exception_handler(Http404)
    def handle_404(request: Any, exc: Http404) -> Any:
        logger.info(f"404 Not Found: {request.path}")
        return api.create_response(request, {"error": "资源不存在", "code": "NOT_FOUND", "errors": {}}, status=404)

    @api.exception_handler(ObjectDoesNotExist)
    def handle_object_not_exist(request: Any, exc: ObjectDoesNotExist) -> Any:
        logger.info(f"Object not found: {request.path}")
        return api.create_response(request, {"error": "资源不存在", "code": "NOT_FOUND", "errors": {}}, status=404)

    @api.exception_handler(DjangoPermissionDenied)
    def handle_django_permission_denied(request: Any, exc: DjangoPermissionDenied) -> Any:
        logger.warning(f"Permission denied: {request.path}", extra={"user": getattr(request, "user", None)})
        return api.create_response(
            request, {"error": "无权限访问", "code": "PERMISSION_DENIED", "errors": {}}, status=403
        )

    @api.exception_handler(NinjaValidationError)
    def handle_ninja_validation_error(request: Any, exc: NinjaValidationError) -> Any:
        logger.info(f"Validation error: {request.path}", extra={"errors": exc.errors})
        return api.create_response(
            request, {"error": "数据校验失败", "code": "VALIDATION_ERROR", "errors": exc.errors}, status=422
        )

    @api.exception_handler(HttpError)
    def handle_http_error(request: Any, exc: HttpError) -> Any:
        logger.warning(f"HTTP Error {exc.status_code}: {request.path}")
        return api.create_response(
            request, {"error": str(exc.message), "code": "HTTP_ERROR", "errors": {}}, status=exc.status_code
        )


def _register_fallback_handler(api: NinjaAPI) -> None:
    """注册兜底异常处理器"""

    @api.exception_handler(Exception)
    def handle_unexpected_exception(request: Any, exc: Exception) -> Any:
        logger.error(
            f"未预期的异常: {exc}",
            exc_info=True,
            extra={
                "path": request.path,
                "method": request.method,
                "user_id": getattr(request.auth, "id", None) if hasattr(request, "auth") else None,
            },
        )
        from django.conf import settings

        message = str(exc) if settings.DEBUG else "系统错误,请稍后重试"
        return api.create_response(request, {"error": message, "code": "INTERNAL_ERROR", "errors": {}}, status=500)
