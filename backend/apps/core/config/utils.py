"""
配置工具函数

提供便捷的配置访问和迁移辅助函数
"""

import logging
from typing import Any, Optional, Dict
from django.conf import settings

logger = logging.getLogger(__name__)


def get_config_value(key: str, default: Any = None, fallback_settings_key: str = None) -> Any:
    """
    获取配置值的通用函数
    
    优先从统一配置管理器获取，如果不可用则回退到 Django settings
    
    Args:
        key: 统一配置键（点号分隔）
        default: 默认值
        fallback_settings_key: 回退的 Django settings 键
        
    Returns:
        配置值
    """
    # 尝试使用统一配置管理器
    try:
        if getattr(settings, 'CONFIG_MANAGER_AVAILABLE', False):
            get_unified_config = getattr(settings, 'get_unified_config', None)
            if get_unified_config:
                value = get_unified_config(key, default)
                if value is not None:
                    return value
    except Exception as e:
        logger.debug(f"从统一配置获取 {key} 失败: {e}")
    
    # 回退到 Django settings
    if fallback_settings_key:
        return getattr(settings, fallback_settings_key, default)
    
    return default


def get_nested_config_value(config_dict: Dict[str, Any], key: str, default: Any = None) -> Any:
    """
    从嵌套字典中获取配置值
    
    Args:
        config_dict: 配置字典
        key: 配置键
        default: 默认值
        
    Returns:
        配置值
    """
    return config_dict.get(key, default)


def get_feishu_config(key: str, default: Any = None) -> Any:
    """
    获取飞书配置的便捷函数
    
    Args:
        key: 配置键（不包含前缀）
        default: 默认值
        
    Returns:
        配置值
    """
    unified_key = f"chat_platforms.feishu.{key}"
    
    # 尝试统一配置
    try:
        if getattr(settings, 'CONFIG_MANAGER_AVAILABLE', False):
            get_unified_config = getattr(settings, 'get_unified_config', None)
            if get_unified_config:
                value = get_unified_config(unified_key)
                if value is not None:
                    return value
    except Exception as e:
        logger.debug(f"从统一配置获取飞书配置 {key} 失败: {e}")
    
    # 回退到传统配置
    feishu_config = getattr(settings, 'FEISHU', {})
    value = feishu_config.get(key.upper())
    if value is not None:
        return value
    
    # 兼容旧配置
    court_sms_config = getattr(settings, 'COURT_SMS_PROCESSING', {})
    old_key = f"FEISHU_{key.upper()}"
    return court_sms_config.get(old_key, default)


def get_document_processing_config(key: str, default: Any = None) -> Any:
    """
    获取文档处理配置的便捷函数
    
    Args:
        key: 配置键
        default: 默认值
        
    Returns:
        配置值
    """
    unified_key = f"features.document_processing.{key}"
    
    # 尝试统一配置
    try:
        if getattr(settings, 'CONFIG_MANAGER_AVAILABLE', False):
            get_unified_config = getattr(settings, 'get_unified_config', None)
            if get_unified_config:
                value = get_unified_config(unified_key)
                if value is not None:
                    return value
    except Exception as e:
        logger.debug(f"从统一配置获取文档处理配置 {key} 失败: {e}")
    
    # 回退到传统配置
    doc_config = getattr(settings, 'DOCUMENT_PROCESSING', {})
    return doc_config.get(key.upper(), default)


def get_case_chat_config(key: str, default: Any = None) -> Any:
    """
    获取案件群聊配置的便捷函数
    
    Args:
        key: 配置键
        default: 默认值
        
    Returns:
        配置值
    """
    unified_key = f"features.case_chat.{key}"
    
    # 尝试统一配置
    try:
        if getattr(settings, 'CONFIG_MANAGER_AVAILABLE', False):
            get_unified_config = getattr(settings, 'get_unified_config', None)
            if get_unified_config:
                value = get_unified_config(unified_key)
                if value is not None:
                    return value
    except Exception as e:
        logger.debug(f"从统一配置获取案件群聊配置 {key} 失败: {e}")
    
    # 回退到传统配置
    case_chat_config = getattr(settings, 'CASE_CHAT', {})
    return case_chat_config.get(key.upper(), default)


def get_court_sms_config(key: str, default: Any = None) -> Any:
    """
    获取法院短信配置的便捷函数
    
    Args:
        key: 配置键
        default: 默认值
        
    Returns:
        配置值
    """
    unified_key = f"features.court_sms.{key}"
    
    # 尝试统一配置
    try:
        if getattr(settings, 'CONFIG_MANAGER_AVAILABLE', False):
            get_unified_config = getattr(settings, 'get_unified_config', None)
            if get_unified_config:
                value = get_unified_config(unified_key)
                if value is not None:
                    return value
    except Exception as e:
        logger.debug(f"从统一配置获取法院短信配置 {key} 失败: {e}")
    
    # 回退到传统配置
    court_sms_config = getattr(settings, 'COURT_SMS_PROCESSING', {})
    return court_sms_config.get(key.upper(), default)


def is_config_manager_available() -> bool:
    """
    检查统一配置管理器是否可用
    
    Returns:
        bool: 是否可用
    """
    return getattr(settings, 'CONFIG_MANAGER_AVAILABLE', False)


def get_config_manager():
    """
    获取配置管理器实例
    
    Returns:
        ConfigManager 实例或 None
    """
    if is_config_manager_available():
        return getattr(settings, 'UNIFIED_CONFIG_MANAGER', None)
    return None


def register_config_change_listener(listener, key_filter: Optional[str] = None, prefix_filter: Optional[str] = None):
    """
    注册配置变更监听器
    
    Args:
        listener: 监听器实例
        key_filter: 键过滤器
        prefix_filter: 前缀过滤器
    """
    config_manager = get_config_manager()
    if config_manager:
        config_manager.add_listener(listener, key_filter, prefix_filter)
    else:
        logger.warning("配置管理器不可用，无法注册监听器")


def migrate_legacy_config_access(legacy_settings_key: str, unified_config_key: str, default: Any = None) -> Any:
    """
    迁移传统配置访问的辅助函数
    
    Args:
        legacy_settings_key: 传统 Django settings 键
        unified_config_key: 统一配置键
        default: 默认值
        
    Returns:
        配置值
    """
    # 优先使用统一配置
    if is_config_manager_available():
        try:
            get_unified_config = getattr(settings, 'get_unified_config', None)
            if get_unified_config:
                value = get_unified_config(unified_config_key)
                if value is not None:
                    return value
        except Exception as e:
            logger.debug(f"从统一配置获取 {unified_config_key} 失败: {e}")
    
    # 回退到传统配置
    return getattr(settings, legacy_settings_key, default)