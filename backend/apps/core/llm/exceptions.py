"""
LLM 专用异常模块

定义 LLM 模块特有的异常类型,继承自 apps.core.exceptions.

Requirements: 1.3, 1.4, 1.5, 1.6
"""

from typing import Any

from apps.core.exceptions import APIError, AuthenticationError, ExternalServiceError, NetworkError


class LLMError(ExternalServiceError):
    """
    LLM 错误基类

    所有 LLM 相关异常的基类.

    HTTP 状态码:502
    """

    def __init__(
        self, message: str = "LLM 服务错误", code: str | None = None, errors: dict[str, Any] | None = None
    ) -> None:
        super().__init__(message=message, code=code or "LLM_ERROR", errors=errors)


class LLMNetworkError(LLMError, NetworkError):
    """
    LLM 网络错误

    使用场景:
    - 网络连接失败
    - 连接被拒绝
    - DNS 解析失败

    HTTP 状态码:502
    """

    def __init__(
        self, message: str = "LLM 网络连接失败", code: str | None = None, errors: dict[str, Any] | None = None
    ) -> None:
        super().__init__(message=message, code=code or "LLM_NETWORK_ERROR", errors=errors)


class LLMAPIError(LLMError, APIError):
    """
    LLM API 错误

    使用场景:
    - API 返回错误状态码
    - API 响应格式错误
    - API 业务逻辑错误

    HTTP 状态码:502
    """

    def __init__(
        self,
        message: str = "LLM API 调用错误",
        code: str | None = None,
        errors: dict[str, Any] | None = None,
        status_code: int | None = None,
    ) -> None:
        if status_code is not None:
            errors = errors or {}
            errors["status_code"] = status_code
        super().__init__(message=message, code=code or "LLM_API_ERROR", errors=errors)
        self.status_code = status_code


class LLMAuthenticationError(LLMError, AuthenticationError):
    """
    LLM 认证错误

    使用场景:
    - API Key 无效
    - API Key 缺失
    - API Key 过期

    HTTP 状态码:401
    """

    def __init__(
        self,
        message: str = "SiliconFlow API Key 无效或缺失",
        code: str | None = None,
        errors: dict[str, Any] | None = None,
    ) -> None:
        super().__init__(
            message=message,
            code=code or "LLM_AUTH_ERROR",
            errors=errors or {"api_key": "请检查 SILICONFLOW.API_KEY 配置"},
        )


class LLMBackendUnavailableError(LLMAPIError):
    def __init__(self, message: str = "所有 LLM 后端均不可用", errors: dict[str, Any] | None = None) -> None:
        super().__init__(message=message, code="LLM_ALL_BACKENDS_UNAVAILABLE", errors=errors)


class LLMTimeoutError(LLMError):
    """
    LLM 超时错误

    使用场景:
    - 请求超时
    - 响应超时

    HTTP 状态码:504
    """

    def __init__(
        self,
        message: str = "LLM 请求超时",
        code: str | None = None,
        errors: dict[str, Any] | None = None,
        timeout_seconds: float | None = None,
    ) -> None:
        if timeout_seconds is not None:
            errors = errors or {}
            errors["timeout_seconds"] = timeout_seconds
        super().__init__(message=message, code=code or "LLM_TIMEOUT", errors=errors)
        self.timeout_seconds = timeout_seconds
