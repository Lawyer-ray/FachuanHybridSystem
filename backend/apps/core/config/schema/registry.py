"""
配置模式注册表

定义系统中所有配置项的模式，包括 Django 核心、第三方服务、群聊平台、业务功能配置
"""

from ._registry_chat import register_chat_configs
from ._registry_django import register_django_configs
from ._registry_features import register_feature_configs
from ._registry_performance import register_performance_configs
from ._registry_services import register_service_configs
from .field import ConfigField


def create_config_registry() -> dict[str, ConfigField]:
    """
    创建完整的配置模式注册表

    Returns:
        Dict[str, ConfigField]: 配置字段注册表，键为配置路径，值为字段定义
    """
    registry: dict[str, ConfigField] = {}
    register_django_configs(registry)
    register_service_configs(registry)
    register_chat_configs(registry)
    register_performance_configs(registry)
    register_feature_configs(registry)
    return registry


# 全局配置注册表实例
CONFIG_REGISTRY = create_config_registry()


def get_config_field(key: str) -> ConfigField:
    """获取配置字段定义"""
    if key not in CONFIG_REGISTRY:
        raise KeyError(f"配置字段 '{key}' 不存在")
    return CONFIG_REGISTRY[key]


def get_all_config_fields() -> dict[str, ConfigField]:
    """获取所有配置字段定义"""
    return CONFIG_REGISTRY.copy()


def get_config_fields_by_category(category: str) -> dict[str, ConfigField]:
    """按类别获取配置字段定义"""
    return {key: field for key, field in CONFIG_REGISTRY.items() if key.startswith(f"{category}.")}


def get_sensitive_config_fields() -> dict[str, ConfigField]:
    """获取所有敏感配置字段定义"""
    return {key: field for key, field in CONFIG_REGISTRY.items() if field.sensitive}


def get_required_config_fields() -> dict[str, ConfigField]:
    """获取所有必需配置字段定义"""
    return {key: field for key, field in CONFIG_REGISTRY.items() if field.required}


def validate_registry_consistency() -> None:
    """
    验证配置注册表的一致性

    Raises:
        ValueError: 配置注册表不一致
    """
    env_vars: dict[str, str] = {}
    errors: list[str] = []

    for key, field in CONFIG_REGISTRY.items():
        if field.env_var:
            if field.env_var in env_vars:
                errors.append(f"环境变量 '{field.env_var}' 被多个配置项使用: '{env_vars[field.env_var]}' 和 '{key}'")
            else:
                env_vars[field.env_var] = key

        if field.depends_on:
            for dep in field.depends_on:
                if dep not in CONFIG_REGISTRY:
                    errors.append(f"配置项 '{key}' 依赖的配置项 '{dep}' 不存在")

    if errors:
        raise ValueError("配置注册表不一致:\n" + "\n".join(errors))


# 在模块加载时验证注册表一致性
validate_registry_consistency()
