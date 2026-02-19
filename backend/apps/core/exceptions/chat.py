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
    # 快捷构造函数（替代原子类）
    "owner_permission_error",
    "owner_not_found_error",
    "owner_validation_error",
    "owner_retry_error",
    "owner_timeout_error",
    "owner_network_error",
    "owner_config_error",
    # 向后兼容别名
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


# ── 快捷构造函数（替代原子类）──────────────────────────────────────────────────


def owner_permission_error(message: str = "群主权限不足", **kwargs: Any) -> OwnerSettingException:
    """群主权限不足"""
    return OwnerSettingException(message=message, code="OWNER_PERMISSION_ERROR", **kwargs)


def owner_not_found_error(message: str = "群主用户不存在", **kwargs: Any) -> OwnerSettingException:
    """群主用户不存在"""
    return OwnerSettingException(message=message, code="OWNER_NOT_FOUND", **kwargs)


def owner_validation_error(message: str = "群主验证失败", **kwargs: Any) -> OwnerSettingException:
    """群主验证失败"""
    return OwnerSettingException(message=message, code="OWNER_VALIDATION_ERROR", **kwargs)


def owner_retry_error(message: str = "群主设置重试失败", **kwargs: Any) -> OwnerSettingException:
    """群主设置重试失败"""
    return OwnerSettingException(message=message, code="OWNER_RETRY_ERROR", **kwargs)


def owner_timeout_error(message: str = "群主设置操作超时", **kwargs: Any) -> OwnerSettingException:
    """群主设置操作超时"""
    return OwnerSettingException(message=message, code="OWNER_TIMEOUT_ERROR", **kwargs)


def owner_network_error(message: str = "群主设置网络错误", **kwargs: Any) -> OwnerSettingException:
    """群主设置网络错误"""
    return OwnerSettingException(message=message, code="OWNER_NETWORK_ERROR", **kwargs)


def owner_config_error(message: str = "群主配置错误", **kwargs: Any) -> OwnerSettingException:
    """群主配置错误"""
    return OwnerSettingException(message=message, code="OWNER_CONFIG_ERROR", **kwargs)


# ── 向后兼容别名（保持 isinstance 检查可用）────────────────────────────────────
OwnerPermissionException = OwnerSettingException
OwnerNotFoundException = OwnerSettingException
OwnerValidationException = OwnerSettingException
OwnerRetryException = OwnerSettingException
OwnerTimeoutException = OwnerSettingException
OwnerNetworkException = OwnerSettingException
OwnerConfigException = OwnerSettingException
