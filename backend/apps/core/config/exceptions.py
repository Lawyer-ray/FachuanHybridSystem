"""
配置管理异常模块

定义配置管理系统中使用的所有异常类型
"""
from typing import List, Optional, Any


class ConfigException(Exception):
    """
    配置异常基类
    
    所有配置相关的异常都应该继承此类
    """
    
    def __init__(self, message: str, code: Optional[str] = None):
        """
        初始化配置异常
        
        Args:
            message: 错误消息
            code: 错误代码，默认使用类名
        """
        self.message = message
        self.code = code or self.__class__.__name__
        super().__init__(message)
    
    def __str__(self) -> str:
        return f"{self.code}: {self.message}"
    
    def __repr__(self) -> str:
        return f"{self.__class__.__name__}(message={self.message!r}, code={self.code!r})"


class ConfigNotFoundError(ConfigException):
    """
    配置项不存在异常
    
    使用场景：
    - 请求的配置项不存在
    - 配置路径无效
    """
    
    def __init__(self, key: str, suggestions: Optional[List[str]] = None):
        """
        初始化配置不存在异常
        
        Args:
            key: 配置项键名
            suggestions: 建议的配置项列表
        """
        self.key = key
        self.suggestions = suggestions or []
        
        message = f"配置项 '{key}' 不存在"
        if suggestions:
            message += f"，您是否想要: {', '.join(suggestions)}"
        
        super().__init__(message, "CONFIG_NOT_FOUND")


class ConfigTypeError(ConfigException):
    """
    配置类型错误异常
    
    使用场景：
    - 配置值类型与期望类型不匹配
    - 类型转换失败
    """
    
    def __init__(self, key: str, expected_type: type, actual_type: type, value: Any = None):
        """
        初始化配置类型错误异常
        
        Args:
            key: 配置项键名
            expected_type: 期望的类型
            actual_type: 实际的类型
            value: 实际的值（可选）
        """
        self.key = key
        self.expected_type = expected_type
        self.actual_type = actual_type
        self.value = value
        
        message = f"配置项 '{key}' 类型错误: 期望 {expected_type.__name__}, 实际 {actual_type.__name__}"
        if value is not None:
            message += f", 值: {value!r}"
        
        super().__init__(message, "CONFIG_TYPE_ERROR")


class ConfigValidationError(ConfigException):
    """
    配置验证错误异常
    
    使用场景：
    - 配置值不符合验证规则
    - 配置项依赖关系验证失败
    - 配置范围验证失败
    """
    
    def __init__(self, errors: List[str], key: Optional[str] = None):
        """
        初始化配置验证错误异常
        
        Args:
            errors: 验证错误列表
            key: 相关的配置项键名（可选）
        """
        self.errors = errors
        self.key = key
        
        if key:
            message = f"配置项 '{key}' 验证失败: {'; '.join(errors)}"
        else:
            message = f"配置验证失败: {'; '.join(errors)}"
        
        super().__init__(message, "CONFIG_VALIDATION_ERROR")


class ConfigFileError(ConfigException):
    """
    配置文件错误异常
    
    使用场景：
    - 配置文件不存在
    - 配置文件格式错误
    - 配置文件读取失败
    """
    
    def __init__(self, path: str, line: Optional[int] = None, message: Optional[str] = None, 
                 original_error: Optional[Exception] = None):
        """
        初始化配置文件错误异常
        
        Args:
            path: 配置文件路径
            line: 错误行号（可选）
            message: 详细错误信息（可选）
            original_error: 原始异常（可选）
        """
        self.path = path
        self.line = line
        self.original_error = original_error
        
        location = f" (行 {line})" if line else ""
        error_msg = f"配置文件错误 '{path}'{location}"
        if message:
            error_msg += f": {message}"
        if original_error:
            error_msg += f" (原因: {original_error})"
        
        super().__init__(error_msg, "CONFIG_FILE_ERROR")


class SensitiveConfigError(ConfigException):
    """
    敏感配置错误异常
    
    使用场景：
    - 生产环境敏感配置未通过环境变量设置
    - 敏感配置泄露风险
    """
    
    def __init__(self, key: str, environment: Optional[str] = None):
        """
        初始化敏感配置错误异常
        
        Args:
            key: 敏感配置项键名
            environment: 当前环境（可选）
        """
        self.key = key
        self.environment = environment
        
        if environment:
            message = f"敏感配置项 '{key}' 在 {environment} 环境必须通过环境变量设置"
        else:
            message = f"敏感配置项 '{key}' 必须通过环境变量设置"
        
        super().__init__(message, "SENSITIVE_CONFIG_ERROR")