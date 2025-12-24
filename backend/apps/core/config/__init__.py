"""
统一配置管理系统

提供集中化、类型安全、环境感知的配置管理能力
"""

from typing import Any

# 导入新的配置管理组件
from .manager import ConfigManager, ConfigChangeListener
from .schema.field import ConfigField
from .schema.schema import ConfigSchema
from .schema.registry import CONFIG_REGISTRY, get_config_field
from .providers.base import ConfigProvider
from .providers.env import EnvProvider
from .providers.yaml import YamlProvider
from .exceptions import (
    ConfigException, ConfigNotFoundError, ConfigTypeError,
    ConfigValidationError, ConfigFileError, SensitiveConfigError
)
from .utils import (
    get_config_value, get_feishu_config, get_document_processing_config,
    get_case_chat_config, get_court_sms_config, is_config_manager_available,
    register_config_change_listener, migrate_legacy_config_access
)

# 全局配置管理器实例
_global_config_manager = None


def get_config_manager() -> ConfigManager:
    """
    获取全局配置管理器实例
    
    Returns:
        ConfigManager: 全局配置管理器实例
    """
    global _global_config_manager
    if _global_config_manager is None:
        _global_config_manager = ConfigManager()
        # 注册配置模式
        schema = ConfigSchema()
        for key, field in CONFIG_REGISTRY.items():
            schema.register(field)
        _global_config_manager.set_schema(schema)
        # 添加提供者
        _global_config_manager.add_provider(EnvProvider())
        
        # 构建配置文件的绝对路径
        import os
        from pathlib import Path
        
        # 获取当前文件所在目录
        current_dir = Path(__file__).parent
        config_file = current_dir / "config.yaml"
        
        # 如果配置文件不存在，尝试从项目根目录查找
        if not config_file.exists():
            # 尝试从 Django BASE_DIR 查找
            try:
                from django.conf import settings
                base_dir = getattr(settings, 'BASE_DIR', None)
                if base_dir:
                    config_file = Path(base_dir).parent / "apps" / "core" / "config.yaml"
            except ImportError:
                pass
        
        _global_config_manager.add_provider(YamlProvider(str(config_file)))
    return _global_config_manager


def get_config(key: str, default: Any = None) -> Any:
    """
    获取配置项的便捷函数
    
    Args:
        key: 配置键（支持点号路径）
        default: 默认值
        
    Returns:
        Any: 配置值
    """
    return get_config_manager().get(key, default)

# 向后兼容性说明：
# 原有的 business_config, BusinessConfig, CaseTypeCode 已迁移到统一配置管理系统
# 如需使用这些配置，请直接从 apps.core.config 模块导入

__all__ = [
    # 新配置管理系统
    'ConfigManager', 'ConfigChangeListener',
    'ConfigField', 'ConfigSchema', 'CONFIG_REGISTRY', 'get_config_field',
    'ConfigProvider', 'EnvProvider', 'YamlProvider',
    'ConfigException', 'ConfigNotFoundError', 'ConfigTypeError',
    'ConfigValidationError', 'ConfigFileError', 'SensitiveConfigError',
    
    # 全局访问函数
    'get_config_manager', 'get_config',
    
    # 配置工具函数
    'get_config_value', 'get_feishu_config', 'get_document_processing_config',
    'get_case_chat_config', 'get_court_sms_config', 'is_config_manager_available',
    'register_config_change_listener', 'migrate_legacy_config_access',
]