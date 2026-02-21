"""
兼容层 - 已废弃，请使用 apps.core.exceptions

Deprecated: This module is a compatibility shim.
Use `from apps.core.exceptions import XxxError` instead.
"""

# DEPRECATED: This file is a compatibility shim for backward compatibility.
# All exception types have been migrated to apps.core.exceptions package.
# This file will be removed in a future version.

from apps.core.exceptions import (
    APIError,
    AuthenticationError,
    BusinessError,
    BusinessException,
    ChatCreationException,
    ChatProviderException,
    ConfigurationException,
    ConflictError,
    ExternalServiceError,
    ForbiddenError,
    MessageSendException,
    NetworkError,
    NotFoundError,
    OwnerConfigException,
    OwnerNetworkException,
    OwnerNotFoundException,
    OwnerPermissionException,
    OwnerRetryException,
    OwnerSettingException,
    OwnerTimeoutException,
    OwnerValidationException,
    PermissionDenied,
    RateLimitError,
    RecognitionTimeoutError,
    ServiceUnavailableError,
    TokenError,
    UnauthorizedError,
    UnsupportedPlatformException,
    ValidationException,
)

# 向后兼容别名（与旧版保持一致）
OwnerPermissionException = OwnerSettingException
OwnerNotFoundException = OwnerSettingException
OwnerValidationException = OwnerSettingException
OwnerRetryException = OwnerSettingException
OwnerTimeoutException = OwnerSettingException
OwnerNetworkException = OwnerSettingException
OwnerConfigException = OwnerSettingException

__all__ = [
    "BusinessException",
    "BusinessError",
    "ValidationException",
    "PermissionDenied",
    "NotFoundError",
    "ConflictError",
    "AuthenticationError",
    "RateLimitError",
    "ForbiddenError",
    "UnauthorizedError",
    "ExternalServiceError",
    "ServiceUnavailableError",
    "RecognitionTimeoutError",
    "TokenError",
    "APIError",
    "NetworkError",
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
]
