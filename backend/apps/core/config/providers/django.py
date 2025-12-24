"""
Django Settings 配置提供者

从 Django settings 加载配置，提供向后兼容性。
"""

from typing import Any, Dict, Set
from django.conf import settings
from .base import ConfigProvider
from ..exceptions import ConfigException


class DjangoProvider(ConfigProvider):
    """Django Settings 配置提供者"""
    
    def __init__(self, include_all: bool = False):
        """
        初始化 Django 提供者
        
        Args:
            include_all: 是否包含所有 Django settings，默认只包含预定义的配置项
        """
        self.include_all = include_all
        
        # 预定义的配置项映射
        self._config_mapping = {
            # Django 核心配置
            'SECRET_KEY': 'django.secret_key',
            'DEBUG': 'django.debug',
            'ALLOWED_HOSTS': 'django.allowed_hosts',
            'USE_TZ': 'django.use_tz',
            'TIME_ZONE': 'django.time_zone',
            'LANGUAGE_CODE': 'django.language_code',
            
            # 数据库配置
            'DATABASES': 'database',
            
            # 静态文件配置
            'STATIC_URL': 'django.static_url',
            'STATIC_ROOT': 'django.static_root',
            'MEDIA_URL': 'django.media_url',
            'MEDIA_ROOT': 'django.media_root',
            
            # 安全配置
            'CORS_ALLOWED_ORIGINS': 'security.cors_allowed_origins',
            'CSRF_TRUSTED_ORIGINS': 'security.csrf_trusted_origins',
            'SECURE_SSL_REDIRECT': 'security.ssl_redirect',
            'SECURE_HSTS_SECONDS': 'security.hsts_seconds',
            
            # 缓存配置
            'CACHES': 'cache',
            
            # 日志配置
            'LOGGING': 'logging',
            
            # 第三方服务配置
            'MOONSHOT_BASE_URL': 'services.moonshot.base_url',
            'MOONSHOT_API_KEY': 'services.moonshot.api_key',
            'OLLAMA_MODEL': 'services.ollama.model',
            'OLLAMA_BASE_URL': 'services.ollama.base_url',
            
            # 群聊平台配置
            'FEISHU_APP_ID': 'chat_platforms.feishu.app_id',
            'FEISHU_APP_SECRET': 'chat_platforms.feishu.app_secret',
            'FEISHU_WEBHOOK_URL': 'chat_platforms.feishu.webhook_url',
            'FEISHU_TIMEOUT': 'chat_platforms.feishu.timeout',
            'FEISHU_DEFAULT_OWNER_ID': 'chat_platforms.feishu.default_owner_id',
            
            'DINGTALK_APP_KEY': 'chat_platforms.dingtalk.app_key',
            'DINGTALK_APP_SECRET': 'chat_platforms.dingtalk.app_secret',
            'DINGTALK_AGENT_ID': 'chat_platforms.dingtalk.agent_id',
            'DINGTALK_TIMEOUT': 'chat_platforms.dingtalk.timeout',
            
            # 业务功能配置
            'CASE_CHAT_DEFAULT_PLATFORM': 'features.case_chat.default_platform',
            'CASE_CHAT_AUTO_CREATE_ON_PUSH': 'features.case_chat.auto_create_on_push',
            'CASE_CHAT_DEFAULT_OWNER_ID': 'features.case_chat.default_owner_id',
            
            'COURT_SMS_MAX_RETRIES': 'features.court_sms.max_retries',
            'COURT_SMS_RETRY_DELAY': 'features.court_sms.retry_delay',
            'COURT_SMS_AUTO_RECOVERY': 'features.court_sms.auto_recovery',
            
            'DOCUMENT_PROCESSING_DEFAULT_TEXT_LIMIT': 'features.document_processing.default_text_limit',
            'DOCUMENT_PROCESSING_MAX_TEXT_LIMIT': 'features.document_processing.max_text_limit',
            'DOCUMENT_PROCESSING_DEFAULT_PREVIEW_PAGE': 'features.document_processing.default_preview_page',
            'DOCUMENT_PROCESSING_MAX_PREVIEW_PAGES': 'features.document_processing.max_preview_pages',
            
            # 性能配置
            'RATE_LIMIT_DEFAULT_REQUESTS': 'performance.rate_limit.default_requests',
            'RATE_LIMIT_DEFAULT_WINDOW': 'performance.rate_limit.default_window',
            'RATE_LIMIT_AUTH_REQUESTS': 'performance.rate_limit.auth_requests',
            'RATE_LIMIT_AUTH_WINDOW': 'performance.rate_limit.auth_window',
            
            # Q_CLUSTER 配置
            'Q_CLUSTER': 'performance.q_cluster',
        }
        
        # 需要忽略的 Django 内部配置
        self._ignored_settings: Set[str] = {
            'INSTALLED_APPS', 'MIDDLEWARE', 'ROOT_URLCONF', 'WSGI_APPLICATION',
            'AUTH_PASSWORD_VALIDATORS', 'TEMPLATES', 'DATABASES_ROUTERS',
            'DEFAULT_AUTO_FIELD', 'USE_I18N', 'USE_L10N'
        }
    
    @property
    def priority(self) -> int:
        """Django Settings 具有最低优先级（向后兼容）"""
        return 10
    
    def supports_reload(self) -> bool:
        """Django Settings 不支持热重载"""
        return False
    
    def load(self) -> Dict[str, Any]:
        """
        从 Django settings 加载配置
        
        Returns:
            Dict[str, Any]: 配置字典
            
        Raises:
            ConfigException: 配置加载失败
        """
        try:
            config = {}
            
            if self.include_all:
                # 包含所有 settings
                config.update(self._load_all_settings())
            else:
                # 只包含预定义的配置项
                config.update(self._load_mapped_settings())
            
            return config
            
        except Exception as e:
            raise ConfigException(f"加载 Django settings 失败: {e}")
    
    def _load_mapped_settings(self) -> Dict[str, Any]:
        """
        加载映射的配置项
        
        Returns:
            Dict[str, Any]: 映射后的配置字典
        """
        config = {}
        
        for django_key, config_key in self._config_mapping.items():
            if hasattr(settings, django_key):
                value = getattr(settings, django_key)
                
                # 特殊处理某些配置项
                if django_key == 'DATABASES':
                    config.update(self._process_database_config(value))
                elif django_key == 'CACHES':
                    config.update(self._process_cache_config(value))
                elif django_key == 'Q_CLUSTER':
                    config.update(self._process_q_cluster_config(value))
                else:
                    config[config_key] = value
        
        return config
    
    def _load_all_settings(self) -> Dict[str, Any]:
        """
        加载所有 Django settings
        
        Returns:
            Dict[str, Any]: 所有配置字典
        """
        config = {}
        
        for key in dir(settings):
            # 跳过私有属性和方法
            if key.startswith('_'):
                continue
            
            # 跳过忽略的配置
            if key in self._ignored_settings:
                continue
            
            try:
                value = getattr(settings, key)
                
                # 跳过可调用对象
                if callable(value):
                    continue
                
                # 转换键名为小写点号格式
                config_key = self._normalize_django_key(key)
                config[config_key] = value
                
            except Exception:
                # 忽略无法访问的配置项
                continue
        
        return config
    
    def _normalize_django_key(self, key: str) -> str:
        """
        标准化 Django 配置键名
        
        Args:
            key: Django 配置键名
            
        Returns:
            str: 标准化后的键名
        """
        # 检查是否有预定义映射
        if key in self._config_mapping:
            return self._config_mapping[key]
        
        # 默认转换：转小写，下划线转点号，添加 django 前缀
        return f"django.{key.lower().replace('_', '.')}"
    
    def _process_database_config(self, databases: Dict[str, Any]) -> Dict[str, Any]:
        """
        处理数据库配置
        
        Args:
            databases: Django DATABASES 配置
            
        Returns:
            Dict[str, Any]: 处理后的数据库配置
        """
        config = {}
        
        # 处理默认数据库
        if 'default' in databases:
            db_config = databases['default']
            config.update({
                'database.engine': db_config.get('ENGINE', ''),
                'database.name': db_config.get('NAME', ''),
                'database.user': db_config.get('USER', ''),
                'database.password': db_config.get('PASSWORD', ''),
                'database.host': db_config.get('HOST', 'localhost'),
                'database.port': db_config.get('PORT', 3306),
                'database.options': db_config.get('OPTIONS', {}),
            })
        
        # 处理其他数据库连接
        for db_name, db_config in databases.items():
            if db_name != 'default':
                config[f'database.{db_name}'] = db_config
        
        return config
    
    def _process_cache_config(self, caches: Dict[str, Any]) -> Dict[str, Any]:
        """
        处理缓存配置
        
        Args:
            caches: Django CACHES 配置
            
        Returns:
            Dict[str, Any]: 处理后的缓存配置
        """
        config = {}
        
        # 处理默认缓存
        if 'default' in caches:
            cache_config = caches['default']
            config.update({
                'performance.cache.backend': cache_config.get('BACKEND', ''),
                'performance.cache.location': cache_config.get('LOCATION', ''),
                'performance.cache.timeout': cache_config.get('TIMEOUT', 300),
                'performance.cache.options': cache_config.get('OPTIONS', {}),
            })
        
        # 处理其他缓存配置
        for cache_name, cache_config in caches.items():
            if cache_name != 'default':
                config[f'performance.cache.{cache_name}'] = cache_config
        
        return config
    
    def _process_q_cluster_config(self, q_cluster: Dict[str, Any]) -> Dict[str, Any]:
        """
        处理 Q_CLUSTER 配置
        
        Args:
            q_cluster: Django Q_CLUSTER 配置
            
        Returns:
            Dict[str, Any]: 处理后的 Q_CLUSTER 配置
        """
        config = {}
        
        for key, value in q_cluster.items():
            config_key = f"performance.q_cluster.{key.lower()}"
            config[config_key] = value
        
        return config
    
    def get_django_setting(self, key: str, default: Any = None) -> Any:
        """
        直接获取 Django setting
        
        Args:
            key: Django setting 键名
            default: 默认值
            
        Returns:
            Any: 配置值
        """
        return getattr(settings, key, default)
    
    def has_django_setting(self, key: str) -> bool:
        """
        检查 Django setting 是否存在
        
        Args:
            key: Django setting 键名
            
        Returns:
            bool: 是否存在
        """
        return hasattr(settings, key)