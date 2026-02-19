"""
配置验证器模块

提供配置项的类型验证、范围验证、依赖验证等功能。
"""

from .base import CompositeValidator, ConfigValidator, ValidationContext, ValidationResult, ValidationType
from .dependency_validator import CircularDependencyValidator, DependencyValidator, RequiredGroupValidator
from .range_validator import NumericRangeValidator, RangeValidator, StringLengthValidator
from .type_validator import PatternValidator, TypeValidator

__all__ = [
    # 基础类
    "ConfigValidator",
    "ValidationResult",
    "ValidationType",
    "CompositeValidator",
    "ValidationContext",
    # 类型验证器
    "TypeValidator",
    "PatternValidator",
    # 范围验证器
    "RangeValidator",
    "NumericRangeValidator",
    "StringLengthValidator",
    # 依赖验证器
    "DependencyValidator",
    "CircularDependencyValidator",
    "RequiredGroupValidator",
]
