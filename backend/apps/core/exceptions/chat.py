"""
群聊相关异常
"""

from __future__ import annotations

from typing import Any

from .base import BusinessException

__all__: list[str] = [
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


class ChatProviderException(BusinessException):
    """群聊提供者异常基类"""

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
    """不支持的平台异常"""

    def __init__(
        self,
        message: str = "不支持的群聊平台",
        platform: str | None = None,
        code: str | None = None,
        errors: dict[str, Any] | None = None,
    ) -> None:
        super().__init__(message=message, code=code or "UNSUPPORTED_PLATFORM", errors=errors, platform=platform)


class ChatCreationException(ChatProviderException):
    """群聊创建失败异常"""

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
    """消息发送失败异常"""

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
    """配置错误异常"""

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
    """群主设置异常基类"""

    def __init__(
        self,
        message: str,
        code: str | None = None,
        errors: dict[str, Any] | None = None,
        error_code: str | None = None,
        platform: str | None = None,
        owner_id: str | None = None,
        chat_id: str | None = None,
    ) -> None:
        super().__init__(
            message=message, code=code or "OWNER_SETTING_ERROR", errors=errors, error_code=error_code, platform=platform
        )
        self.owner_id = owner_id
        self.chat_id = chat_id


class OwnerPermissionException(OwnerSettingException):
    """群主权限异常"""

    def __init__(self, message: str = "群主权限不足", **kwargs: Any) -> None:
        super().__init__(message=message, code=kwargs.pop("code", "OWNER_PERMISSION_ERROR"), **kwargs)


class OwnerNotFoundException(OwnerSettingException):
    """群主用户不存在异常"""

    def __init__(self, message: str = "群主用户不存在", **kwargs: Any) -> None:
        super().__init__(message=message, code=kwargs.pop("code", "OWNER_NOT_FOUND"), **kwargs)


class OwnerValidationException(OwnerSettingException):
    """群主验证异常"""

    def __init__(self, message: str = "群主验证失败", **kwargs: Any) -> None:
        super().__init__(message=message, code=kwargs.pop("code", "OWNER_VALIDATION_ERROR"), **kwargs)


class OwnerRetryException(OwnerSettingException):
    """群主设置重试异常"""

    def __init__(
        self,
        message: str = "群主设置重试失败",
        retry_count: int | None = None,
        max_retries: int | None = None,
        **kwargs: Any,
    ) -> None:
        super().__init__(message=message, code=kwargs.pop("code", "OWNER_RETRY_ERROR"), **kwargs)
        self.retry_count = retry_count
        self.max_retries = max_retries


class OwnerTimeoutException(OwnerSettingException):
    """群主设置超时异常"""

    def __init__(self, message: str = "群主设置操作超时", timeout_seconds: float | None = None, **kwargs: Any) -> None:
        super().__init__(message=message, code=kwargs.pop("code", "OWNER_TIMEOUT_ERROR"), **kwargs)
        self.timeout_seconds = timeout_seconds


class OwnerNetworkException(OwnerSettingException):
    """群主设置网络异常"""

    def __init__(self, message: str = "群主设置网络错误", network_error: str | None = None, **kwargs: Any) -> None:
        super().__init__(message=message, code=kwargs.pop("code", "OWNER_NETWORK_ERROR"), **kwargs)
        self.network_error = network_error


class OwnerConfigException(OwnerSettingException):
    """群主配置异常"""

    def __init__(self, message: str = "群主配置错误", config_key: str | None = None, **kwargs: Any) -> None:
        super().__init__(message=message, code=kwargs.pop("code", "OWNER_CONFIG_ERROR"), **kwargs)
        self.config_key = config_key
