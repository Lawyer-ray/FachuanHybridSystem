"""
统一异常处理模块
定义业务异常和全局异常处理器
"""

from __future__ import annotations

from typing import Any

# 基础异常
from .base import BusinessError, BusinessException

# 群聊异常
from .chat import (
    ChatCreationException,
    ChatProviderException,
    ConfigurationException,
    MessageSendException,
    OwnerConfigException,
    OwnerNetworkException,
    OwnerNotFoundException,
    OwnerPermissionException,
    OwnerRetryException,
    OwnerSettingException,
    OwnerTimeoutException,
    OwnerValidationException,
    UnsupportedPlatformException,
    owner_config_error,
    owner_network_error,
    owner_not_found_error,
    owner_permission_error,
    owner_retry_error,
    owner_timeout_error,
    owner_validation_error,
)

# 通用异常
from .common import (
    AuthenticationError,
    ConflictError,
    ForbiddenError,
    NotFoundError,
    PermissionDenied,
    RateLimitError,
    UnauthorizedError,
    ValidationException,
)

# 外部服务异常
from .external import (
    APIError,
    AutoTokenAcquisitionError,
    CaptchaRecognitionError,
    ExternalServiceError,
    LoginFailedError,
    NetworkError,
    NoAvailableAccountError,
    RecognitionTimeoutError,
    ServiceUnavailableError,
    TokenAcquisitionTimeoutError,
    TokenError,
)


def __getattr__(name: str) -> object:
    if name == "AutomationExceptions":
        import warnings

        warnings.warn(
            "AutomationExceptions is deprecated, use direct exception instantiation",
            DeprecationWarning,
            stacklevel=2,
        )
        from .automation_factory import AutomationExceptions as _AutomationExceptions

        return _AutomationExceptions
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")


# 异常处理器 - 延迟导入避免 Django 配置问题
def register_exception_handlers(*args: Any, **kwargs: Any) -> None:
    """延迟导入异常处理器"""
    from .handlers import register_exception_handlers as _register

    return _register(*args, **kwargs)


__all__ = [
    # 基础异常
    "BusinessException",
    "BusinessError",
    # 通用异常
    "ValidationException",
    "PermissionDenied",
    "NotFoundError",
    "ConflictError",
    "AuthenticationError",
    "RateLimitError",
    "ForbiddenError",
    "UnauthorizedError",
    # 外部服务异常
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
    # 群聊异常
    "ChatProviderException",
    "UnsupportedPlatformException",
    "ChatCreationException",
    "MessageSendException",
    "ConfigurationException",
    "OwnerSettingException",
    "OwnerPermissionException",
    "OwnerNotFoundException",
    "OwnerValidationException",
    "OwnerRetryException",
    "OwnerTimeoutException",
    "OwnerNetworkException",
    "OwnerConfigException",
    # 快捷构造函数
    "owner_permission_error",
    "owner_not_found_error",
    "owner_validation_error",
    "owner_retry_error",
    "owner_timeout_error",
    "owner_network_error",
    "owner_config_error",
    # Automation 异常工厂
    "AutomationExceptions",
    # 异常处理器
    "register_exception_handlers",
]
