"""
外部服务相关异常
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from django.utils.functional import Promise

from .base import BusinessException

__all__: list[str] = [
    "ExternalServiceError",
    "ServiceUnavailableError",
    "RecognitionTimeoutError",
    "TokenError",
    "APIError",
    "NetworkError",
    "AutoTokenAcquisitionError",
    "LoginFailedError",
    "NoAvailableAccountError",
    "TokenAcquisitionTimeoutError",
    "CaptchaRecognitionError",
]


class ExternalServiceError(BusinessException):
    """
    外部服务错误

    使用场景:
    - 第三方 API 调用失败
    - 外部服务不可用

    HTTP 状态码:502
    """

    def __init__(
        self, message: str | Promise = "外部服务错误", code: str | None = None, errors: dict[str, Any] | None = None
    ) -> None:
        super().__init__(message=message, code=code or "EXTERNAL_SERVICE_ERROR", errors=errors)


class ServiceUnavailableError(ExternalServiceError):
    """
    服务不可用异常

    使用场景:
    - AI 服务(如 Ollama)不可用
    - 依赖服务暂时不可用
    - 服务维护中

    HTTP 状态码:503
    """

    def __init__(
        self,
        message: str | Promise = "服务暂时不可用",
        code: str | None = None,
        errors: dict[str, Any] | None = None,
        service_name: str | None = None,
    ) -> None:
        if service_name:
            errors = errors or {}
            errors["service"] = service_name
        super().__init__(message=message, code=code or "SERVICE_UNAVAILABLE", errors=errors)
        self.service_name = service_name


class RecognitionTimeoutError(ExternalServiceError):
    """
    识别超时异常

    使用场景:
    - AI 识别超时
    - OCR 处理超时
    - 文档处理超时

    HTTP 状态码:504
    """

    def __init__(
        self,
        message: str | Promise = "识别超时",
        code: str | None = None,
        errors: dict[str, Any] | None = None,
        timeout_seconds: float | None = None,
    ) -> None:
        if timeout_seconds is not None:
            errors = errors or {}
            errors["timeout_seconds"] = timeout_seconds
        super().__init__(message=message, code=code or "RECOGNITION_TIMEOUT", errors=errors)
        self.timeout_seconds = timeout_seconds


class TokenError(BusinessException):
    """
    Token 错误

    使用场景:
    - Token 不存在
    - Token 已过期
    - Token 无效

    HTTP 状态码:401
    """

    def __init__(
        self, message: str | Promise = "Token 错误", code: str | None = None, errors: dict[str, Any] | None = None
    ) -> None:
        super().__init__(message=message, code=code or "TOKEN_ERROR", errors=errors)


class APIError(ExternalServiceError):
    """
    API 调用错误

    使用场景:
    - API 返回错误状态码
    - API 响应格式错误
    - API 业务逻辑错误

    HTTP 状态码:502
    """

    def __init__(
        self, message: str | Promise = "API 调用错误", code: str | None = None, errors: dict[str, Any] | None = None
    ) -> None:
        super().__init__(message=message, code=code or "API_ERROR", errors=errors)


class NetworkError(ExternalServiceError):
    """
    网络错误

    使用场景:
    - 网络连接失败
    - 请求超时
    - 连接被拒绝

    HTTP 状态码:502
    """

    def __init__(
        self, message: str | Promise = "网络错误", code: str | None = None, errors: dict[str, Any] | None = None
    ) -> None:
        super().__init__(message=message, code=code or "NETWORK_ERROR", errors=errors)


class AutoTokenAcquisitionError(ExternalServiceError):
    """
    自动Token获取基础异常

    使用场景:
    - 自动Token获取流程中的各种错误
    - 作为其他Token获取异常的基类

    HTTP 状态码:502
    """

    def __init__(
        self, message: str | Promise = "自动Token获取失败", code: str | None = None, errors: dict[str, Any] | None = None
    ) -> None:
        super().__init__(message=message, code=code or "AUTO_TOKEN_ACQUISITION_ERROR", errors=errors)


class LoginFailedError(AutoTokenAcquisitionError):
    """
    登录失败异常

    使用场景:
    - 账号密码错误
    - 验证码识别失败
    - 登录流程异常

    HTTP 状态码:502
    """

    def __init__(
        self,
        message: str | Promise = "登录失败",
        code: str | None = None,
        errors: dict[str, Any] | None = None,
        attempts: list[Any] | None = None,
    ) -> None:
        super().__init__(message=message, code=code or "LOGIN_FAILED", errors=errors)
        self.attempts = attempts or []


class NoAvailableAccountError(AutoTokenAcquisitionError):
    """
    无可用账号异常

    使用场景:
    - 没有配置账号凭证
    - 所有账号都已失效
    - 所有账号都在黑名单中

    HTTP 状态码:502
    """

    def __init__(
        self, message: str | Promise = "无可用账号", code: str | None = None, errors: dict[str, Any] | None = None
    ) -> None:
        super().__init__(message=message, code=code or "NO_AVAILABLE_ACCOUNT", errors=errors)


class TokenAcquisitionTimeoutError(AutoTokenAcquisitionError):
    """
    Token获取超时异常

    使用场景:
    - 登录过程超时
    - Token获取流程超时

    HTTP 状态码:502
    """

    def __init__(
        self, message: str | Promise = "Token获取超时", code: str | None = None, errors: dict[str, Any] | None = None
    ) -> None:
        super().__init__(message=message, code=code or "TOKEN_ACQUISITION_TIMEOUT", errors=errors)


class CaptchaRecognitionError(ExternalServiceError):
    """
    验证码识别错误

    使用场景:
    - 验证码识别失败
    - 验证码图片格式不支持
    - 验证码识别服务异常

    HTTP 状态码:502
    """

    def __init__(
        self, message: str | Promise = "验证码识别失败", code: str | None = None, errors: dict[str, Any] | None = None
    ) -> None:
        super().__init__(message=message, code=code or "CAPTCHA_RECOGNITION_ERROR", errors=errors)
