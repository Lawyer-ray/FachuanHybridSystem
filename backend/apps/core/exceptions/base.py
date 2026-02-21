"""
业务异常基类模块
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from django.utils.functional import Promise

__all__: list[str] = [
    "BusinessException",
    "BusinessError",
]


class BusinessException(Exception):
    """
    业务异常基类

    所有自定义业务异常都应该继承此类

    Attributes:
        message: 错误消息(用户可读)
        code: 错误码(用于前端判断)
        errors: 结构化错误详情(字段级别的错误)
    """

    def __init__(self, message: str | Promise, code: str | None = None, errors: dict[str, Any] | None = None) -> None:
        """
        初始化业务异常

        Args:
            message: 错误消息(用户可读)
            code: 错误码(用于前端判断),默认使用类名
            errors: 结构化错误详情(字段级别的错误)
        """
        self.message = message
        self.code = code or self.__class__.__name__
        self.errors = errors or {}
        super().__init__(str(message))

    def __str__(self) -> str:
        """返回字符串表示"""
        return f"{self.code}: {self.message}"

    def __repr__(self) -> str:
        """返回详细的字符串表示"""
        return f"{self.__class__.__name__}(message={self.message!r}, code={self.code!r}, errors={self.errors!r})"

    def to_dict(self) -> dict[str, Any]:
        """
        转换为字典(用于 API 响应)

        Returns:
            包含 success、code、message、error、errors 字段的字典
        """
        return {
            "success": False,
            "code": self.code,
            "message": str(self.message),
            "error": self.message,
            "errors": self.errors,
        }


class BusinessError(BusinessException):
    """业务逻辑异常基类(向后兼容)"""

    def __init__(self, message: str | Promise, code: str = "BUSINESS_ERROR", status: int = 400) -> None:
        super().__init__(message, code)
        self.status = status
