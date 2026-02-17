"""
案件模块异常定义

注意：群聊相关异常类已迁移到 apps.core.exceptions
本文件保留向后兼容的导入，新代码请直接从 apps.core.exceptions 导入
"""

from typing import Optional, Dict, Any

# 向后兼容：从 core.exceptions 重新导出群聊相关异常
from apps.core.exceptions import (
    BusinessException,
    ExternalServiceError,
    # 群聊相关异常（已迁移到 core）
    ChatProviderException,
    UnsupportedPlatformException,
    ChatCreationException,
    MessageSendException,
    ConfigurationException,
    OwnerSettingException,
    OwnerPermissionException,
    OwnerNotFoundException,
    OwnerValidationException,
    OwnerRetryException,
    OwnerTimeoutException,
    OwnerNetworkException,
    OwnerConfigException,
)

__all__ = [
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