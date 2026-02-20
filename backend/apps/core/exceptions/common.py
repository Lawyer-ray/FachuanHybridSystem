"""
通用业务异常类
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from django.utils.functional import Promise

from .base import BusinessException

__all__: list[str] = [
    "ValidationException",
    "PermissionDenied",
    "NotFoundError",
    "ConflictError",
    "AuthenticationError",
    "RateLimitError",
    "ForbiddenError",
    "UnauthorizedError",
]


class ValidationException(BusinessException):
    """
    验证异常

    使用场景:
    - 数据格式不正确
    - 业务规则验证失败
    - 字段值不符合要求

    HTTP 状态码:400
    """

    def __init__(
        self, message: str | Promise = "数据验证失败", code: str | None = None, errors: dict[str, Any] | None = None
    ) -> None:
        super().__init__(message=message, code=code or "VALIDATION_ERROR", errors=errors)


class PermissionDenied(BusinessException):
    """
    权限拒绝异常

    使用场景:
    - 用户无权限执行操作
    - 访问被拒绝的资源

    HTTP 状态码:403
    """

    def __init__(
        self, message: str | Promise = "无权限执行该操作", code: str | None = None, errors: dict[str, Any] | None = None
    ) -> None:
        super().__init__(message=message, code=code or "PERMISSION_DENIED", errors=errors)


class NotFoundError(BusinessException):
    """
    资源不存在异常

    使用场景:
    - 查询的资源不存在
    - ID 无效

    HTTP 状态码:404
    """

    def __init__(
        self, message: str | Promise = "资源不存在", code: str | None = None, errors: dict[str, Any] | None = None
    ) -> None:
        super().__init__(message=message, code=code or "NOT_FOUND", errors=errors)


class ConflictError(BusinessException):
    """
    资源冲突异常

    使用场景:
    - 资源已存在(重复创建)
    - 资源状态冲突
    - 并发修改冲突

    HTTP 状态码:409
    """

    def __init__(
        self, message: str | Promise = "资源冲突", code: str | None = None, errors: dict[str, Any] | None = None
    ) -> None:
        super().__init__(message=message, code=code or "CONFLICT", errors=errors)


class AuthenticationError(BusinessException):
    """
    认证失败异常

    使用场景:
    - 登录失败
    - Token 无效
    - 会话过期

    HTTP 状态码:401
    """

    def __init__(
        self, message: str | Promise = "认证失败", code: str | None = None, errors: dict[str, Any] | None = None
    ) -> None:
        super().__init__(message=message, code=code or "AUTHENTICATION_ERROR", errors=errors)


class RateLimitError(BusinessException):
    """
    频率限制异常

    使用场景:
    - 请求过于频繁
    - 超过配额限制

    HTTP 状态码:429
    """

    def __init__(
        self, message: str | Promise = "请求过于频繁", code: str | None = None, errors: dict[str, Any] | None = None
    ) -> None:
        super().__init__(message=message, code=code or "RATE_LIMIT_ERROR", errors=errors)


# 向后兼容的别名
class ForbiddenError(PermissionDenied):
    """无权限访问(向后兼容)"""

    def __init__(self, message: str | Promise = "无权限访问") -> None:
        super().__init__(message)
        self.status = 403


class UnauthorizedError(AuthenticationError):
    """未认证(向后兼容)"""

    def __init__(self, message: str | Promise = "请先登录") -> None:
        super().__init__(message)
        self.status = 401
