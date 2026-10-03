"""
配置工具函数

提供便捷的配置访问和迁移辅助函数
"""

import logging
from typing import Any

from django.conf import settings

logger = logging.getLogger(__name__)


def get_config_value(key: str, default: Any | None = None, fallback_settings_key: str | None = None) -> Any:
    """
    获取配置值的通用函数

    Args:
        key: 配置键
        default: 默认值
        fallback_settings_key: 回退的 Django settings 键

    Returns:
        配置值
    """
    if fallback_settings_key:
        return getattr(settings, fallback_settings_key, default)

    return default


def get_category_configs(category: str) -> dict[str, Any]:
    """
    批量获取指定分类的 SystemConfig 配置

    Args:
        category: 配置分类（如 feishu、wechat_work、dingtalk、telegram）

    Returns:
        配置字典，key 为 DB 键名（如 FEISHU_APP_ID），value 为配置值
    """
    try:
        from apps.core.services.system_config_service import SystemConfigService

        service = SystemConfigService()
        result: dict[str, Any] = service.get_category_configs(category)
        return result
    except Exception as e:
        logger.debug(f"从 SystemConfig 批量获取 {category} 配置失败: {e}")
        return {}


def get_feishu_category_configs() -> dict[str, Any]:
    """批量获取飞书分类配置"""
    return get_category_configs("feishu")


def get_wechat_work_category_configs() -> dict[str, Any]:
    """批量获取企业微信分类配置"""
    return get_category_configs("wechat_work")


def get_dingtalk_category_configs() -> dict[str, Any]:
    """批量获取钉钉分类配置"""
    return get_category_configs("dingtalk")


def get_telegram_category_configs() -> dict[str, Any]:
    """批量获取 Telegram 分类配置"""
    return get_category_configs("telegram")


def get_system_config_value(key: str, default: Any | None = None) -> Any:
    """
    获取 SystemConfig 单个配置值

    Args:
        key: 配置键
        default: 默认值

    Returns:
        配置值
    """
    try:
        from apps.core.services.system_config_service import SystemConfigService

        service = SystemConfigService()
        return service.get_value(key, default=default if default is not None else "")
    except Exception as e:
        logger.debug(f"从 SystemConfig 获取配置 {key} 失败: {e}")
        return default


def get_feishu_config(key: str, default: Any | None = None) -> Any:
    """
    获取飞书配置的便捷函数

    Args:
        key: 配置键（不包含前缀）
        default: 默认值

    Returns:
        配置值
    """
    feishu_config = getattr(settings, "FEISHU", {})
    value = feishu_config.get(key.upper())
    if value is not None:
        return value

    # 兼容旧配置
    court_sms_config = getattr(settings, "COURT_SMS_PROCESSING", {})
    old_key = f"FEISHU_{key.upper()}"
    return court_sms_config.get(old_key, default)


def get_document_processing_config(key: str, default: Any | None = None) -> Any:
    """
    获取文档处理配置的便捷函数

    Args:
        key: 配置键
        default: 默认值

    Returns:
        配置值
    """
    doc_config = getattr(settings, "DOCUMENT_PROCESSING", {})
    return doc_config.get(key.upper(), default)


def get_case_chat_config(key: str, default: Any | None = None) -> Any:
    """
    获取案件群聊配置的便捷函数

    Args:
        key: 配置键
        default: 默认值

    Returns:
        配置值
    """
    case_chat_config = getattr(settings, "CASE_CHAT", {})
    return case_chat_config.get(key.upper(), default)


def get_court_sms_config(key: str, default: Any | None = None) -> Any:
    """
    获取法院短信配置的便捷函数

    Args:
        key: 配置键
        default: 默认值

    Returns:
        配置值
    """
    court_sms_config = getattr(settings, "COURT_SMS_PROCESSING", {})
    return court_sms_config.get(key.upper(), default)


def is_config_manager_available() -> bool:
    """
    检查统一配置管理器是否可用

    Returns:
        bool: 是否可用
    """
    return getattr(settings, "CONFIG_MANAGER_AVAILABLE", False)
