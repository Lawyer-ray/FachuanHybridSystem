"""
统一异常处理模块
定义业务异常和全局异常处理器
"""

from __future__ import annotations

from typing import Any

# Automation 异常工厂
from .automation_factory import AutomationExceptions

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


# 异常处理器 - 延迟导入避免 Django 配置问题
def register_exception_handlers(*args, **kwargs: Any) -> None:  # type: ignore[no-untyped-def]
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
    # Automation 异常工厂
    "AutomationExceptions",
    # 异常处理器
    "register_exception_handlers",
]
