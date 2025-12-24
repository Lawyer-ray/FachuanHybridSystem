"""
Django Settings 向后兼容接口

提供与现有 Django settings 完全兼容的访问接口，
确保现有代码无需修改即可使用统一配置管理系统。
"""

import os
import sys
from typing import Any, Dict, List, Optional, Union
from django.conf import settings as django_settings
from django.core.exceptions import ImproperlyConfigured

from .manager import ConfigManager
from .exceptions import ConfigNotFoundError


class CompatibleSettings:
    """
    兼容的 Settings 类
    
    提供与 Django settings 相同的接口，但底层使用统一配置管理器。
    """
    
    def __init__(self, config_manager: ConfigManager):
        """
        初始化兼容设置
        
        Args:
            config_manager: 配置管理器实例
        """
        self._config_manager = config_manager
        self._django_to_config_mapping = self._build_django_mapping()
        self._config_to_django_mapping = {v: k for k, v in self._django_to_config_mapping.items()}
        self._fallback_to_django = True
        
        # 缓存 Django 原始设置
        self._django_settings_cache = {}
        self._cache_django_settings()
    
    def _build_django_mapping(self) -> Dict[str, str]:
        """
        构建 Django settings 到统一配置的映射
        
        Returns:
            Dict[str, str]: 映射字典
        """
        return {
            # Django 核心配置
            'SECRET_KEY': 'django.secret_key',
            'DEBUG': 'django.debug',
            'ALLOWED_HOSTS': 'django.allowed_hosts',
            'INSTALLED_APPS': 'django.installed_apps',
            'MIDDLEWARE': 'django.middleware',
            'ROOT_URLCONF': 'django.root_urlconf',
            'TEMPLATES': 'django.templates',
            'WSGI_APPLICATION': 'django.wsgi_application',
            
            # 数据库配置
            'DATABASES': 'database',
            
            # 国际化配置
            'LANGUAGE_CODE': 'django.language_code',
            'TIME_ZONE': 'django.time_zone',
            'USE_I18N': 'django.use_i18n',
            'USE_TZ': 'django.use_tz',
            
            # 静态文件配置
            'STATIC_URL': 'django.static_url',
            'STATIC_ROOT': 'django.static_root',
            'MEDIA_URL': 'django.media_url',
            'MEDIA_ROOT': 'django.media_root',
            
            # 认证配置
            'AUTH_USER_MODEL': 'django.auth_user_model',
            'AUTH_PASSWORD_VALIDATORS': 'django.auth_password_validators',
            
            # CORS 配置
            'CORS_ALLOW_ALL_ORIGINS': 'cors.allow_all_origins',
            'CORS_ALLOWED_ORIGINS': 'cors.allowed_origins',
            'CORS_ALLOW_CREDENTIALS': 'cors.allow_credentials',
            'CORS_ALLOW_HEADERS': 'cors.allow_headers',
            'CSRF_TRUSTED_ORIGINS': 'cors.csrf_trusted_origins',
            
            # 缓存配置
            'CACHES': 'performance.cache',
            
            # 日志配置
            'LOGGING': 'logging',
            
            # 第三方服务配置
            'MOONSHOT_BASE_URL': 'services.moonshot.base_url',
            'MOONSHOT_API_KEY': 'services.moonshot.api_key',
            'OLLAMA': 'services.ollama',
            
            # 群聊平台配置
            'FEISHU': 'chat_platforms.feishu',
            'DINGTALK': 'chat_platforms.dingtalk',
            'WECHAT_WORK': 'chat_platforms.wechat_work',
            'TELEGRAM': 'chat_platforms.telegram',
            'SLACK': 'chat_platforms.slack',
            
            # 业务功能配置
            'CASE_CHAT': 'features.case_chat',
            'COURT_SMS_PROCESSING': 'features.court_sms',
            'DOCUMENT_PROCESSING': 'features.document_processing',
            
            # 性能配置
            'Q_CLUSTER': 'performance.q_cluster',
            'RATE_LIMIT': 'performance.rate_limit',
            
            # 安全配置
            'SCRAPER_ENCRYPTION_KEY': 'security.scraper_encryption_key',
            'PERM_OPEN_ACCESS': 'security.perm_open_access',
            
            # API 配置
            'API_VERSION': 'api.version',
        }
    
    def _cache_django_settings(self) -> None:
        """缓存 Django 原始设置"""
        for attr_name in dir(django_settings):
            if not attr_name.startswith('_') and attr_name.isupper():
                try:
                    self._django_settings_cache[attr_name] = getattr(django_settings, attr_name)
                except Exception:
                    # 忽略无法获取的属性
                    continue
    
    def __getattr__(self, name: str) -> Any:
        """
        获取配置项（兼容 Django settings 访问方式）
        
        Args:
            name: 配置项名称
            
        Returns:
            配置值
            
        Raises:
            AttributeError: 配置项不存在
        """
        # 首先尝试从统一配置获取
        if name in self._django_to_config_mapping:
            config_key = self._django_to_config_mapping[name]
            try:
                return self._config_manager.get(config_key)
            except ConfigNotFoundError:
                pass
        
        # 回退到 Django settings
        if self._fallback_to_django:
            if hasattr(django_settings, name):
                return getattr(django_settings, name)
            
            # 从缓存中获取
            if name in self._django_settings_cache:
                return self._django_settings_cache[name]
        
        # 抛出 AttributeError（与 Django settings 行为一致）
        raise AttributeError(f"'{self.__class__.__name__}' object has no attribute '{name}'")
    
    def __setattr__(self, name: str, value: Any) -> None:
        """
        设置配置项
        
        Args:
            name: 配置项名称
            value: 配置值
        """
        # 内部属性直接设置
        if name.startswith('_') or name in ['_config_manager', '_django_to_config_mapping', 
                                           '_config_to_django_mapping', '_fallback_to_django',
                                           '_django_settings_cache']:
            super().__setattr__(name, value)
            return
        
        # 配置项设置到统一配置管理器
        if name in self._django_to_config_mapping:
            config_key = self._django_to_config_mapping[name]
            self._config_manager.set(config_key, value)
        else:
            # 设置到 Django settings（如果可能）
            if self._fallback_to_django:
                setattr(django_settings, name, value)
    
    def __hasattr__(self, name: str) -> bool:
        """
        检查配置项是否存在
        
        Args:
            name: 配置项名称
            
        Returns:
            bool: 是否存在
        """
        # 检查统一配置
        if name in self._django_to_config_mapping:
            config_key = self._django_to_config_mapping[name]
            if self._config_manager.has(config_key):
                return True
        
        # 检查 Django settings
        if self._fallback_to_django:
            return hasattr(django_settings, name) or name in self._django_settings_cache
        
        return False
    
    def __dir__(self) -> List[str]:
        """
        返回所有可用的配置项名称
        
        Returns:
            List[str]: 配置项名称列表
        """
        attrs = set()
        
        # 添加映射的配置项
        attrs.update(self._django_to_config_mapping.keys())
        
        # 添加 Django settings 中的配置项
        if self._fallback_to_django:
            for attr_name in dir(django_settings):
                if not attr_name.startswith('_') and attr_name.isupper():
                    attrs.add(attr_name)
            
            # 添加缓存中的配置项
            attrs.update(self._django_settings_cache.keys())
        
        return sorted(list(attrs))
    
    def get(self, name: str, default: Any = None) -> Any:
        """
        获取配置项（提供默认值）
        
        Args:
            name: 配置项名称
            default: 默认值
            
        Returns:
            配置值或默认值
        """
        try:
            return getattr(self, name)
        except AttributeError:
            return default
    
    def configure(self, **options) -> None:
        """
        配置设置（兼容 Django settings.configure()）
        
        Args:
            **options: 配置选项
        """
        for name, value in options.items():
            setattr(self, name, value)
    
    def is_overridden(self, setting: str) -> bool:
        """
        检查设置是否被覆盖（兼容 Django）
        
        Args:
            setting: 设置名称
            
        Returns:
            bool: 是否被覆盖
        """
        # 检查是否在统一配置中
        if setting in self._django_to_config_mapping:
            config_key = self._django_to_config_mapping[setting]
            return self._config_manager.has(config_key)
        
        # 回退到 Django settings
        if self._fallback_to_django and hasattr(django_settings, 'is_overridden'):
            return django_settings.is_overridden(setting)
        
        return False
    
    def enable_fallback(self, enabled: bool = True) -> None:
        """
        启用或禁用回退到 Django settings
        
        Args:
            enabled: 是否启用回退
        """
        self._fallback_to_django = enabled
    
    def is_fallback_enabled(self) -> bool:
        """
        检查是否启用回退
        
        Returns:
            bool: 是否启用回退
        """
        return self._fallback_to_django
    
    def get_config_source(self, name: str) -> str:
        """
        获取配置项的来源
        
        Args:
            name: 配置项名称
            
        Returns:
            str: 配置来源 ('unified', 'django', 'not_found')
        """
        # 检查统一配置
        if name in self._django_to_config_mapping:
            config_key = self._django_to_config_mapping[name]
            if self._config_manager.has(config_key):
                return 'unified'
        
        # 检查 Django settings
        if self._fallback_to_django:
            if hasattr(django_settings, name) or name in self._django_settings_cache:
                return 'django'
        
        return 'not_found'
    
    def migrate_to_unified(self, setting_name: str) -> bool:
        """
        将特定设置迁移到统一配置
        
        Args:
            setting_name: 设置名称
            
        Returns:
            bool: 是否成功迁移
        """
        try:
            # 获取当前值
            current_value = getattr(self, setting_name)
            
            # 如果有映射，设置到统一配置
            if setting_name in self._django_to_config_mapping:
                config_key = self._django_to_config_mapping[setting_name]
                self._config_manager.set(config_key, current_value)
                return True
            
            return False
            
        except Exception:
            return False
    
    def get_all_settings(self) -> Dict[str, Any]:
        """
        获取所有设置
        
        Returns:
            Dict[str, Any]: 所有设置的字典
        """
        settings_dict = {}
        
        # 获取统一配置中的设置
        for django_key, config_key in self._django_to_config_mapping.items():
            if self._config_manager.has(config_key):
                settings_dict[django_key] = self._config_manager.get(config_key)
        
        # 获取 Django settings 中的设置
        if self._fallback_to_django:
            for attr_name in dir(django_settings):
                if not attr_name.startswith('_') and attr_name.isupper():
                    if attr_name not in settings_dict:  # 避免重复
                        try:
                            settings_dict[attr_name] = getattr(django_settings, attr_name)
                        except Exception:
                            continue
            
            # 添加缓存中的设置
            for name, value in self._django_settings_cache.items():
                if name not in settings_dict:
                    settings_dict[name] = value
        
        return settings_dict
    
    def reload(self) -> None:
        """重新加载配置"""
        self._config_manager.reload()
        self._cache_django_settings()
    
    def get_migration_status(self) -> Dict[str, str]:
        """
        获取迁移状态
        
        Returns:
            Dict[str, str]: 每个设置的迁移状态
        """
        status = {}
        
        for django_key in self._django_to_config_mapping.keys():
            source = self.get_config_source(django_key)
            if source == 'unified':
                status[django_key] = 'migrated'
            elif source == 'django':
                status[django_key] = 'not_migrated'
            else:
                status[django_key] = 'missing'
        
        return status


class SettingsProxy:
    """
    Settings 代理类
    
    可以替换 Django settings 模块，提供完全兼容的接口。
    """
    
    def __init__(self, config_manager: ConfigManager):
        """
        初始化代理
        
        Args:
            config_manager: 配置管理器实例
        """
        self._compatible_settings = CompatibleSettings(config_manager)
        self._original_settings = django_settings
    
    def __getattr__(self, name: str) -> Any:
        """代理属性访问"""
        return getattr(self._compatible_settings, name)
    
    def __setattr__(self, name: str, value: Any) -> None:
        """代理属性设置"""
        if name.startswith('_'):
            super().__setattr__(name, value)
        else:
            setattr(self._compatible_settings, name, value)
    
    def __hasattr__(self, name: str) -> bool:
        """代理属性检查"""
        return hasattr(self._compatible_settings, name)
    
    def __dir__(self) -> List[str]:
        """代理目录列表"""
        return dir(self._compatible_settings)
    
    def configure(self, **options) -> None:
        """代理配置方法"""
        return self._compatible_settings.configure(**options)
    
    def is_overridden(self, setting: str) -> bool:
        """代理覆盖检查"""
        return self._compatible_settings.is_overridden(setting)
    
    @property
    def configured(self) -> bool:
        """检查是否已配置（兼容 Django）"""
        return hasattr(self._original_settings, 'configured') and self._original_settings.configured
    
    def get_compatible_settings(self) -> CompatibleSettings:
        """
        获取兼容设置实例
        
        Returns:
            CompatibleSettings: 兼容设置实例
        """
        return self._compatible_settings
    
    def enable_unified_config(self, enabled: bool = True) -> None:
        """
        启用或禁用统一配置
        
        Args:
            enabled: 是否启用
        """
        self._compatible_settings.enable_fallback(not enabled)
    
    def get_original_settings(self):
        """
        获取原始 Django settings
        
        Returns:
            Django settings 对象
        """
        return self._original_settings


def create_compatible_settings(config_manager: ConfigManager) -> CompatibleSettings:
    """
    创建兼容设置实例
    
    Args:
        config_manager: 配置管理器实例
        
    Returns:
        CompatibleSettings: 兼容设置实例
    """
    return CompatibleSettings(config_manager)


def create_settings_proxy(config_manager: ConfigManager) -> SettingsProxy:
    """
    创建设置代理实例
    
    Args:
        config_manager: 配置管理器实例
        
    Returns:
        SettingsProxy: 设置代理实例
    """
    return SettingsProxy(config_manager)


def patch_django_settings(config_manager: ConfigManager) -> SettingsProxy:
    """
    修补 Django settings 模块
    
    Args:
        config_manager: 配置管理器实例
        
    Returns:
        SettingsProxy: 新的设置代理
        
    Warning:
        这会修改全局的 Django settings，请谨慎使用
    """
    # 创建代理
    proxy = create_settings_proxy(config_manager)
    
    # 替换模块中的 settings
    import django.conf
    django.conf.settings = proxy
    
    # 也替换 sys.modules 中的引用
    for module_name, module in sys.modules.items():
        if hasattr(module, 'settings') and module.settings is django_settings:
            module.settings = proxy
    
    return proxy


def unpatch_django_settings() -> None:
    """
    恢复原始的 Django settings
    
    Warning:
        这会恢复全局的 Django settings
    """
    import django.conf
    from django.conf import settings as original_settings
    
    # 恢复模块中的 settings
    django.conf.settings = original_settings
    
    # 恢复 sys.modules 中的引用
    for module_name, module in sys.modules.items():
        if hasattr(module, 'settings') and isinstance(module.settings, SettingsProxy):
            module.settings = module.settings.get_original_settings()


# 全局兼容设置实例（可选）
_global_compatible_settings: Optional[CompatibleSettings] = None
_global_settings_proxy: Optional[SettingsProxy] = None


def get_global_compatible_settings() -> Optional[CompatibleSettings]:
    """
    获取全局兼容设置实例
    
    Returns:
        Optional[CompatibleSettings]: 全局兼容设置实例
    """
    return _global_compatible_settings


def set_global_compatible_settings(config_manager: ConfigManager) -> CompatibleSettings:
    """
    设置全局兼容设置实例
    
    Args:
        config_manager: 配置管理器实例
        
    Returns:
        CompatibleSettings: 兼容设置实例
    """
    global _global_compatible_settings
    _global_compatible_settings = create_compatible_settings(config_manager)
    return _global_compatible_settings


def get_global_settings_proxy() -> Optional[SettingsProxy]:
    """
    获取全局设置代理实例
    
    Returns:
        Optional[SettingsProxy]: 全局设置代理实例
    """
    return _global_settings_proxy


def set_global_settings_proxy(config_manager: ConfigManager) -> SettingsProxy:
    """
    设置全局设置代理实例
    
    Args:
        config_manager: 配置管理器实例
        
    Returns:
        SettingsProxy: 设置代理实例
    """
    global _global_settings_proxy
    _global_settings_proxy = create_settings_proxy(config_manager)
    return _global_settings_proxy