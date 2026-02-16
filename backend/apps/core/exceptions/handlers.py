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

    # 1. 验证异常 - 400
    @api.exception_handler(ValidationException)
    def handle_validation_exception(request: Any, exc: ValidationException) -> Any:
        """处理验证异常"""
        logger.info(f"验证失败: {exc.message}", extra={"code": exc.code, "errors": exc.errors, "path": request.path})
        return api.create_response(request, exc.to_dict(), status=400)

    # 2. 认证失败 - 401
    @api.exception_handler(AuthenticationError)
    def handle_authentication_error(request: Any, exc: AuthenticationError) -> Any:
        """处理认证失败"""
        logger.warning(f"认证失败: {exc.message}", extra={"code": exc.code, "path": request.path})
        return api.create_response(request, exc.to_dict(), status=401)

    # 3. 权限拒绝 - 403
    @api.exception_handler(PermissionDenied)
    def handle_permission_denied_exception(request: Any, exc: PermissionDenied) -> Any:
        """处理权限拒绝"""
        logger.warning(
            f"权限拒绝: {exc.message}",
            extra={
                "code": exc.code,
                "path": request.path,
                "user_id": getattr(request.auth, "id", None) if hasattr(request, "auth") else None,
            },
        )
        return api.create_response(request, exc.to_dict(), status=403)

    # 4. 资源不存在 - 404
    @api.exception_handler(NotFoundError)
    def handle_not_found_exception(request: Any, exc: NotFoundError) -> Any:
        """处理资源不存在"""
        logger.info(f"资源不存在: {exc.message}", extra={"code": exc.code, "path": request.path})
        return api.create_response(request, exc.to_dict(), status=404)

    # 5. 资源冲突 - 409
    @api.exception_handler(ConflictError)
    def handle_conflict_exception(request: Any, exc: ConflictError) -> Any:
        """处理资源冲突"""
        logger.info(f"资源冲突: {exc.message}", extra={"code": exc.code, "errors": exc.errors, "path": request.path})
        return api.create_response(request, exc.to_dict(), status=409)

    # 6. 频率限制 - 429
    @api.exception_handler(RateLimitError)
    def handle_rate_limit_exception(request: Any, exc: RateLimitError) -> Any:
        """处理频率限制"""
        logger.warning(
            f"频率限制: {exc.message}",
            extra={
                "code": exc.code,
                "path": request.path,
                "user_id": getattr(request.auth, "id", None) if hasattr(request, "auth") else None,
            },
        )
        return api.create_response(request, exc.to_dict(), status=429)

    # 7. 服务不可用 - 503
    @api.exception_handler(ServiceUnavailableError)
    def handle_service_unavailable_error(request: Any, exc: ServiceUnavailableError) -> Any:
        """处理服务不可用错误"""
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

    # 8. 识别超时 - 504
    @api.exception_handler(RecognitionTimeoutError)
    def handle_recognition_timeout_error(request: Any, exc: RecognitionTimeoutError) -> Any:
        """处理识别超时错误"""
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

    # 9. 外部服务错误 - 502
    @api.exception_handler(ExternalServiceError)
    def handle_external_service_error(request: Any, exc: ExternalServiceError) -> Any:
        """处理外部服务错误"""
        logger.error(
            f"外部服务错误: {exc.message}", extra={"code": exc.code, "errors": exc.errors, "path": request.path}
        )
        return api.create_response(request, exc.to_dict(), status=502)

    # 10. 通用业务异常 - 400
    @api.exception_handler(BusinessException)
    def handle_business_exception(request: Any, exc: BusinessException) -> Any:
        """处理通用业务异常"""
        logger.warning(f"业务异常: {exc.message}", extra={"code": exc.code, "errors": exc.errors, "path": request.path})
        return api.create_response(request, exc.to_dict(), status=400)

    # 向后兼容:处理旧的 BusinessError
    @api.exception_handler(BusinessError)
    def handle_business_error(request: Any, exc: BusinessError) -> Any:
        logger.warning(
            f"BusinessError: {exc.code} - {exc.message}", extra={"path": request.path, "method": request.method}
        )
        response = {"success": False, "code": exc.code, "message": exc.message}
        if hasattr(exc, "errors") and exc.errors:
            response["errors"] = exc.errors
        status = getattr(exc, "status", 400)
        return api.create_response(request, response, status=status)

    # Django 内置异常处理
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

    # 11. 未预期的异常 - 500
    @api.exception_handler(Exception)
    def handle_unexpected_exception(request: Any, exc: Exception) -> Any:
        """处理未预期的异常"""
        logger.error(
            f"未预期的异常: {exc}",
            exc_info=True,
            extra={
                "path": request.path,
                "method": request.method,
                "user_id": getattr(request.auth, "id", None) if hasattr(request, "auth") else None,
            },
        )
        # 生产环境不暴露详细错误信息
        from django.conf import settings

        message = str(exc) if settings.DEBUG else "系统错误,请稍后重试"
        return api.create_response(request, {"error": message, "code": "INTERNAL_ERROR", "errors": {}}, status=500)
