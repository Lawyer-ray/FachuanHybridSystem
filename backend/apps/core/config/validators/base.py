"""
配置验证器基类

提供配置验证的基础接口和通用功能。
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional, Union


class ValidationType(Enum):
    """验证类型枚举"""
    TYPE = "type"
    RANGE = "range"
    PATTERN = "pattern"
    DEPENDENCY = "dependency"
    CUSTOM = "custom"


@dataclass
class ValidationResult:
    """验证结果"""
    is_valid: bool
    errors: List[str] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)
    
    def add_error(self, message: str) -> None:
        """添加错误信息"""
        self.errors.append(message)
        self.is_valid = False
    
    def add_warning(self, message: str) -> None:
        """添加警告信息"""
        self.warnings.append(message)
    
    def merge(self, other: 'ValidationResult') -> None:
        """合并另一个验证结果"""
        self.errors.extend(other.errors)
        self.warnings.extend(other.warnings)
        if not other.is_valid:
            self.is_valid = False


class ConfigValidator(ABC):
    """配置验证器基类"""
    
    @property
    @abstractmethod
    def validation_type(self) -> ValidationType:
        """验证器类型"""
        pass
    
    @abstractmethod
    def validate(self, key: str, value: Any, field_def: Any = None, config: Dict[str, Any] = None) -> ValidationResult:
        """
        验证配置项
        
        Args:
            key: 配置项键名
            value: 配置项值
            field_def: 字段定义（ConfigField对象）
            config: 完整配置字典（用于依赖验证）
            
        Returns:
            ValidationResult: 验证结果
        """
        pass
    
    def can_validate(self, field_def: Any) -> bool:
        """
        检查是否可以验证指定字段
        
        Args:
            field_def: 字段定义
            
        Returns:
            bool: 是否可以验证
        """
        return True


class CompositeValidator(ConfigValidator):
    """复合验证器，组合多个验证器"""
    
    def __init__(self, validators: List[ConfigValidator]):
        self.validators = validators
    
    @property
    def validation_type(self) -> ValidationType:
        return ValidationType.CUSTOM
    
    def validate(self, key: str, value: Any, field_def: Any = None, config: Dict[str, Any] = None) -> ValidationResult:
        """执行所有验证器的验证"""
        result = ValidationResult(is_valid=True)
        
        for validator in self.validators:
            if validator.can_validate(field_def):
                validator_result = validator.validate(key, value, field_def, config)
                result.merge(validator_result)
        
        return result
    
    def add_validator(self, validator: ConfigValidator) -> None:
        """添加验证器"""
        self.validators.append(validator)
    
    def remove_validator(self, validation_type: ValidationType) -> None:
        """移除指定类型的验证器"""
        self.validators = [v for v in self.validators if v.validation_type != validation_type]


class ValidationContext:
    """验证上下文，提供验证过程中的辅助信息"""
    
    def __init__(self, config: Dict[str, Any], schema: Any = None):
        self.config = config
        self.schema = schema
        self.validation_path: List[str] = []
    
    def push_path(self, key: str) -> None:
        """推入路径"""
        self.validation_path.append(key)
    
    def pop_path(self) -> str:
        """弹出路径"""
        return self.validation_path.pop() if self.validation_path else ""
    
    def get_current_path(self) -> str:
        """获取当前路径"""
        return ".".join(self.validation_path)
    
    def get_nested_value(self, key: str) -> Any:
        """获取嵌套配置值"""
        keys = key.split('.')
        value = self.config
        
        try:
            for k in keys:
                if isinstance(value, dict):
                    value = value[k]
                else:
                    return None
            return value
        except (KeyError, TypeError):
            return None