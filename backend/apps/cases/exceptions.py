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


# ==================== 以下类保留用于向后兼容，但已废弃 ====================
# 新代码请直接使用 from apps.core.exceptions import XxxException


class ChatProviderException(BusinessException):
    """群聊提供者异常基类
    
    所有群聊提供者相关的异常都应该继承此类。
    用于统一处理群聊操作中的各种错误情况。
    
    使用场景：
    - 群聊API调用失败
    - 平台特定的错误
    - 群聊操作通用错误
    
    HTTP 状态码：400
    """
    
    def __init__(
        self,
        message: str,
        code: Optional[str] = None,
        errors: Optional[Dict[str, Any]] = None,
        error_code: Optional[str] = None,
        platform: Optional[str] = None
    ):
        """初始化群聊提供者异常
        
        Args:
            message: 错误消息
            code: 错误码
            errors: 结构化错误详情
            error_code: 平台特定的错误代码
            platform: 发生错误的平台名称
        """
        super().__init__(
            message=message,
            code=code or "CHAT_PROVIDER_ERROR",
            errors=errors
        )
        self.error_code = error_code
        self.platform = platform
    
    def to_dict(self) -> Dict[str, Any]:
        """转换为字典，包含平台特定信息"""
        result = super().to_dict()
        if self.error_code:
            result["error_code"] = self.error_code
        if self.platform:
            result["platform"] = self.platform
        return result


class UnsupportedPlatformException(ChatProviderException):
    """不支持的平台异常
    
    使用场景：
    - 请求的群聊平台未实现
    - 平台提供者未注册
    - 平台功能不可用
    
    HTTP 状态码：400
    """
    
    def __init__(
        self,
        message: str = "不支持的群聊平台",
        platform: Optional[str] = None,
        code: Optional[str] = None,
        errors: Optional[Dict[str, Any]] = None
    ):
        super().__init__(
            message=message,
            code=code or "UNSUPPORTED_PLATFORM",
            errors=errors,
            platform=platform
        )


class ChatCreationException(ChatProviderException):
    """群聊创建失败异常
    
    使用场景：
    - 群聊创建API调用失败
    - 群聊名称不符合平台要求
    - 权限不足无法创建群聊
    - 平台服务异常
    
    HTTP 状态码：400
    """
    
    def __init__(
        self,
        message: str = "群聊创建失败",
        code: Optional[str] = None,
        errors: Optional[Dict[str, Any]] = None,
        error_code: Optional[str] = None,
        platform: Optional[str] = None
    ):
        super().__init__(
            message=message,
            code=code or "CHAT_CREATION_ERROR",
            errors=errors,
            error_code=error_code,
            platform=platform
        )


class MessageSendException(ChatProviderException):
    """消息发送失败异常
    
    使用场景：
    - 消息发送API调用失败
    - 群聊不存在或已解散
    - 机器人无权限发送消息
    - 消息内容不符合平台要求
    - 文件上传失败
    
    HTTP 状态码：400
    """
    
    def __init__(
        self,
        message: str = "消息发送失败",
        code: Optional[str] = None,
        errors: Optional[Dict[str, Any]] = None,
        error_code: Optional[str] = None,
        platform: Optional[str] = None,
        chat_id: Optional[str] = None
    ):
        super().__init__(
            message=message,
            code=code or "MESSAGE_SEND_ERROR",
            errors=errors,
            error_code=error_code,
            platform=platform
        )
        self.chat_id = chat_id
    
    def to_dict(self) -> Dict[str, Any]:
        """转换为字典，包含群聊ID信息"""
        result = super().to_dict()
        if self.chat_id:
            result["chat_id"] = self.chat_id
        return result


class ConfigurationException(ChatProviderException):
    """配置错误异常
    
    使用场景：
    - 平台配置缺失或不完整
    - API密钥无效
    - 配置格式错误
    - 必要参数未设置
    
    HTTP 状态码：500
    """
    
    def __init__(
        self,
        message: str = "群聊平台配置错误",
        code: Optional[str] = None,
        errors: Optional[Dict[str, Any]] = None,
        platform: Optional[str] = None,
        missing_config: Optional[str] = None
    ):
        super().__init__(
            message=message,
            code=code or "CONFIGURATION_ERROR",
            errors=errors,
            platform=platform
        )
        self.missing_config = missing_config
    
    def to_dict(self) -> Dict[str, Any]:
        """转换为字典，包含缺失配置信息"""
        result = super().to_dict()
        if self.missing_config:
            result["missing_config"] = self.missing_config
        return result


# ==================== 群主设置增强功能专用异常 ====================

class OwnerSettingException(ChatProviderException):
    """群主设置异常基类
    
    所有群主设置相关的异常都应该继承此类。
    用于统一处理群主设置过程中的各种错误情况。
    
    使用场景：
    - 群主设置失败
    - 群主验证失败
    - 群主配置错误
    
    HTTP 状态码：400
    """
    
    def __init__(
        self,
        message: str,
        code: Optional[str] = None,
        errors: Optional[Dict[str, Any]] = None,
        error_code: Optional[str] = None,
        platform: Optional[str] = None,
        owner_id: Optional[str] = None,
        chat_id: Optional[str] = None
    ):
        """初始化群主设置异常
        
        Args:
            message: 错误消息
            code: 错误码
            errors: 结构化错误详情
            error_code: 平台特定的错误代码
            platform: 发生错误的平台名称
            owner_id: 相关的群主ID
            chat_id: 相关的群聊ID
        """
        super().__init__(
            message=message,
            code=code or "OWNER_SETTING_ERROR",
            errors=errors,
            error_code=error_code,
            platform=platform
        )
        self.owner_id = owner_id
        self.chat_id = chat_id
    
    def to_dict(self) -> Dict[str, Any]:
        """转换为字典，包含群主和群聊信息"""
        result = super().to_dict()
        if self.owner_id:
            result["owner_id"] = self.owner_id
        if self.chat_id:
            result["chat_id"] = self.chat_id
        return result


class OwnerPermissionException(OwnerSettingException):
    """群主权限异常
    
    使用场景：
    - 指定的用户无权限成为群主
    - 当前用户无权限设置群主
    - 飞书API返回权限相关错误
    
    HTTP 状态码：403
    
    Requirements: 3.1
    """
    
    def __init__(
        self,
        message: str = "群主权限不足",
        code: Optional[str] = None,
        errors: Optional[Dict[str, Any]] = None,
        error_code: Optional[str] = None,
        platform: Optional[str] = None,
        owner_id: Optional[str] = None,
        chat_id: Optional[str] = None,
        permission_type: Optional[str] = None
    ):
        super().__init__(
            message=message,
            code=code or "OWNER_PERMISSION_ERROR",
            errors=errors,
            error_code=error_code,
            platform=platform,
            owner_id=owner_id,
            chat_id=chat_id
        )
        self.permission_type = permission_type
    
    def to_dict(self) -> Dict[str, Any]:
        """转换为字典，包含权限类型信息"""
        result = super().to_dict()
        if self.permission_type:
            result["permission_type"] = self.permission_type
        return result


class OwnerNotFoundException(OwnerSettingException):
    """群主用户不存在异常
    
    使用场景：
    - 指定的群主用户ID不存在
    - 群主用户已被删除或禁用
    - 群主用户不在当前企业中
    
    HTTP 状态码：404
    
    Requirements: 3.2
    """
    
    def __init__(
        self,
        message: str = "群主用户不存在",
        code: Optional[str] = None,
        errors: Optional[Dict[str, Any]] = None,
        error_code: Optional[str] = None,
        platform: Optional[str] = None,
        owner_id: Optional[str] = None,
        chat_id: Optional[str] = None
    ):
        super().__init__(
            message=message,
            code=code or "OWNER_NOT_FOUND",
            errors=errors,
            error_code=error_code,
            platform=platform,
            owner_id=owner_id,
            chat_id=chat_id
        )


class OwnerValidationException(OwnerSettingException):
    """群主验证异常
    
    使用场景：
    - 群主ID格式不正确
    - 群主ID验证失败
    - 群主设置后验证不通过
    
    HTTP 状态码：400
    
    Requirements: 2.3
    """
    
    def __init__(
        self,
        message: str = "群主验证失败",
        code: Optional[str] = None,
        errors: Optional[Dict[str, Any]] = None,
        error_code: Optional[str] = None,
        platform: Optional[str] = None,
        owner_id: Optional[str] = None,
        chat_id: Optional[str] = None,
        validation_type: Optional[str] = None
    ):
        super().__init__(
            message=message,
            code=code or "OWNER_VALIDATION_ERROR",
            errors=errors,
            error_code=error_code,
            platform=platform,
            owner_id=owner_id,
            chat_id=chat_id
        )
        self.validation_type = validation_type
    
    def to_dict(self) -> Dict[str, Any]:
        """转换为字典，包含验证类型信息"""
        result = super().to_dict()
        if self.validation_type:
            result["validation_type"] = self.validation_type
        return result


class OwnerRetryException(OwnerSettingException):
    """群主设置重试异常
    
    使用场景：
    - 群主设置重试次数超限
    - 重试过程中发生错误
    - 重试机制配置错误
    
    HTTP 状态码：500
    
    Requirements: 3.3, 3.4
    """
    
    def __init__(
        self,
        message: str = "群主设置重试失败",
        code: Optional[str] = None,
        errors: Optional[Dict[str, Any]] = None,
        error_code: Optional[str] = None,
        platform: Optional[str] = None,
        owner_id: Optional[str] = None,
        chat_id: Optional[str] = None,
        retry_count: Optional[int] = None,
        max_retries: Optional[int] = None
    ):
        super().__init__(
            message=message,
            code=code or "OWNER_RETRY_ERROR",
            errors=errors,
            error_code=error_code,
            platform=platform,
            owner_id=owner_id,
            chat_id=chat_id
        )
        self.retry_count = retry_count
        self.max_retries = max_retries
    
    def to_dict(self) -> Dict[str, Any]:
        """转换为字典，包含重试信息"""
        result = super().to_dict()
        if self.retry_count is not None:
            result["retry_count"] = self.retry_count
        if self.max_retries is not None:
            result["max_retries"] = self.max_retries
        return result


class OwnerTimeoutException(OwnerSettingException):
    """群主设置超时异常
    
    使用场景：
    - 群主设置操作超时
    - 群主验证超时
    - 网络请求超时
    
    HTTP 状态码：408
    
    Requirements: 3.4
    """
    
    def __init__(
        self,
        message: str = "群主设置操作超时",
        code: Optional[str] = None,
        errors: Optional[Dict[str, Any]] = None,
        error_code: Optional[str] = None,
        platform: Optional[str] = None,
        owner_id: Optional[str] = None,
        chat_id: Optional[str] = None,
        timeout_seconds: Optional[float] = None
    ):
        super().__init__(
            message=message,
            code=code or "OWNER_TIMEOUT_ERROR",
            errors=errors,
            error_code=error_code,
            platform=platform,
            owner_id=owner_id,
            chat_id=chat_id
        )
        self.timeout_seconds = timeout_seconds
    
    def to_dict(self) -> Dict[str, Any]:
        """转换为字典，包含超时信息"""
        result = super().to_dict()
        if self.timeout_seconds is not None:
            result["timeout_seconds"] = self.timeout_seconds
        return result


class OwnerNetworkException(OwnerSettingException):
    """群主设置网络异常
    
    使用场景：
    - 网络连接失败
    - API请求失败
    - 网络超时
    
    HTTP 状态码：502
    
    Requirements: 3.3
    """
    
    def __init__(
        self,
        message: str = "群主设置网络错误",
        code: Optional[str] = None,
        errors: Optional[Dict[str, Any]] = None,
        error_code: Optional[str] = None,
        platform: Optional[str] = None,
        owner_id: Optional[str] = None,
        chat_id: Optional[str] = None,
        network_error: Optional[str] = None
    ):
        super().__init__(
            message=message,
            code=code or "OWNER_NETWORK_ERROR",
            errors=errors,
            error_code=error_code,
            platform=platform,
            owner_id=owner_id,
            chat_id=chat_id
        )
        self.network_error = network_error
    
    def to_dict(self) -> Dict[str, Any]:
        """转换为字典，包含网络错误信息"""
        result = super().to_dict()
        if self.network_error:
            result["network_error"] = self.network_error
        return result


class OwnerConfigException(OwnerSettingException):
    """群主配置异常
    
    使用场景：
    - 群主配置缺失或无效
    - 默认群主配置错误
    - 环境变量配置问题
    
    HTTP 状态码：500
    
    Requirements: 2.1, 2.4
    """
    
    def __init__(
        self,
        message: str = "群主配置错误",
        code: Optional[str] = None,
        errors: Optional[Dict[str, Any]] = None,
        error_code: Optional[str] = None,
        platform: Optional[str] = None,
        owner_id: Optional[str] = None,
        chat_id: Optional[str] = None,
        config_key: Optional[str] = None
    ):
        super().__init__(
            message=message,
            code=code or "OWNER_CONFIG_ERROR",
            errors=errors,
            error_code=error_code,
            platform=platform,
            owner_id=owner_id,
            chat_id=chat_id
        )
        self.config_key = config_key
    
    def to_dict(self) -> Dict[str, Any]:
        """转换为字典，包含配置键信息"""
        result = super().to_dict()
        if self.config_key:
            result["config_key"] = self.config_key
        return result