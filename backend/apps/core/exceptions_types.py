"""
统一异常类型模块
定义业务异常类型(不包含全局异常处理器注册)
"""

import logging
from typing import Any

logger = logging.getLogger("api")


class BusinessException(Exception):
    """
    业务异常基类

    所有自定义业务异常都应该继承此类

    Attributes:
        message: 错误消息(用户可读)
        code: 错误码(用于前端判断)
        errors: 结构化错误详情(字段级别的错误)
    """

    def __init__(self, message: str, code: str | None = None, errors: dict[str, Any] | None = None) -> None:
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
        super().__init__(message)

    def __str__(self) -> str:
        return f"{self.code}: {self.message}"

    def __repr__(self) -> str:
        return f"{self.__class__.__name__}(message={self.message!r}, code={self.code!r}, errors={self.errors!r})"

    def to_dict(self) -> dict[str, Any]:
        message = self.message
        return {
            "success": False,
            "code": self.code,
            "message": message,
            "error": message,
            "errors": self.errors,
        }


class BusinessError(BusinessException):
    def __init__(self, message: str, code: str = "BUSINESS_ERROR", status: int = 400) -> None:
        super().__init__(message, code)
        self.status = status


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
        self, message: str = "数据验证失败", code: str | None = None, errors: dict[str, Any] | None = None
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
        self, message: str = "无权限执行该操作", code: str | None = None, errors: dict[str, Any] | None = None
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
        self, message: str = "资源不存在", code: str | None = None, errors: dict[str, Any] | None = None
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
        self, message: str = "资源冲突", code: str | None = None, errors: dict[str, Any] | None = None
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
        self, message: str = "认证失败", code: str | None = None, errors: dict[str, Any] | None = None
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
        self, message: str = "请求过于频繁", code: str | None = None, errors: dict[str, Any] | None = None
    ) -> None:
        super().__init__(message=message, code=code or "RATE_LIMIT_ERROR", errors=errors)


class ExternalServiceError(BusinessException):
    """
    外部服务错误

    使用场景:
    - 第三方 API 调用失败
    - 外部服务不可用

    HTTP 状态码:502
    """

    def __init__(
        self, message: str = "外部服务错误", code: str | None = None, errors: dict[str, Any] | None = None
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
        message: str = "服务暂时不可用",
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
        message: str = "识别超时",
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
        self, message: str = "Token 错误", code: str | None = None, errors: dict[str, Any] | None = None
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
        self, message: str = "API 调用错误", code: str | None = None, errors: dict[str, Any] | None = None
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
        self, message: str = "网络错误", code: str | None = None, errors: dict[str, Any] | None = None
    ) -> None:
        super().__init__(message=message, code=code or "NETWORK_ERROR", errors=errors)


class ForbiddenError(PermissionDenied):
    def __init__(self, message: str = "无权限访问") -> None:
        super().__init__(message)
        self.status = 403


class UnauthorizedError(AuthenticationError):
    def __init__(self, message: str = "请先登录") -> None:
        super().__init__(message)
        self.status = 401


class ChatProviderException(BusinessException):
    def __init__(
        self,
        message: str,
        code: str | None = None,
        errors: dict[str, Any] | None = None,
        error_code: str | None = None,
        platform: str | None = None,
    ) -> None:
        super().__init__(message=message, code=code or "CHAT_PROVIDER_ERROR", errors=errors)
        self.error_code = error_code
        self.platform = platform


class UnsupportedPlatformException(ChatProviderException):
    def __init__(
        self,
        message: str = "不支持的群聊平台",
        platform: str | None = None,
        code: str | None = None,
        errors: dict[str, Any] | None = None,
    ) -> None:
        super().__init__(message=message, code=code or "UNSUPPORTED_PLATFORM", errors=errors, platform=platform)


class ChatCreationException(ChatProviderException):
    def __init__(
        self,
        message: str = "群聊创建失败",
        code: str | None = None,
        errors: dict[str, Any] | None = None,
        error_code: str | None = None,
        platform: str | None = None,
    ) -> None:
        super().__init__(
            message=message, code=code or "CHAT_CREATION_ERROR", errors=errors, error_code=error_code, platform=platform
        )


class MessageSendException(ChatProviderException):
    def __init__(
        self,
        message: str = "消息发送失败",
        code: str | None = None,
        errors: dict[str, Any] | None = None,
        error_code: str | None = None,
        platform: str | None = None,
        chat_id: str | None = None,
    ) -> None:
        super().__init__(
            message=message, code=code or "MESSAGE_SEND_ERROR", errors=errors, error_code=error_code, platform=platform
        )
        self.chat_id = chat_id


class ConfigurationException(ChatProviderException):
    def __init__(
        self,
        message: str = "群聊平台配置错误",
        code: str | None = None,
        errors: dict[str, Any] | None = None,
        platform: str | None = None,
        missing_config: str | None = None,
    ) -> None:
        super().__init__(message=message, code=code or "CONFIGURATION_ERROR", errors=errors, platform=platform)
        self.missing_config = missing_config


class OwnerSettingException(ChatProviderException):
    """
    群主设置异常（统一基类）

    通过 code 字段区分具体错误类型：
    - OWNER_PERMISSION_ERROR: 群主权限不足
    - OWNER_NOT_FOUND: 群主用户不存在
    - OWNER_VALIDATION_ERROR: 群主验证失败
    - OWNER_RETRY_ERROR: 群主设置重试失败
    - OWNER_TIMEOUT_ERROR: 群主设置操作超时
    - OWNER_NETWORK_ERROR: 群主设置网络错误
    - OWNER_CONFIG_ERROR: 群主配置错误
    """

    def __init__(
        self,
        message: str,
        code: str | None = None,
        errors: dict[str, Any] | None = None,
        error_code: str | None = None,
        platform: str | None = None,
        owner_id: str | None = None,
        chat_id: str | None = None,
        **extra: Any,
    ) -> None:
        super().__init__(
            message=message, code=code or "OWNER_SETTING_ERROR", errors=errors, error_code=error_code, platform=platform
        )
        self.owner_id = owner_id
        self.chat_id = chat_id
        for key, value in extra.items():
            setattr(self, key, value)


# 向后兼容别名
OwnerPermissionException = OwnerSettingException
OwnerNotFoundException = OwnerSettingException
OwnerValidationException = OwnerSettingException
OwnerRetryException = OwnerSettingException
OwnerTimeoutException = OwnerSettingException
OwnerNetworkException = OwnerSettingException
OwnerConfigException = OwnerSettingException
