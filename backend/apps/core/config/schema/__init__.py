"""
配置模式定义模块

提供配置字段定义和模式验证功能
"""
from .field import ConfigField
from .schema import ConfigSchema

__all__ = ['ConfigField', 'ConfigSchema']