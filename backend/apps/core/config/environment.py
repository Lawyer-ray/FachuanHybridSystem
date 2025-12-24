"""
环境配置管理模块

提供环境感知的配置管理功能，支持不同环境的配置策略
"""
import os
from enum import Enum
from typing import Dict, Any, Optional, List
from .exceptions import ConfigException, SensitiveConfigError


class Environment(Enum):
    """
    支持的环境类型
    
    定义系统支持的所有环境类型及其标识符
    """
    DEVELOPMENT = "development"
    TESTING = "testing"
    STAGING = "staging"
    PRODUCTION = "production"
    
    @classmethod
    def from_string(cls, env_str: str) -> 'Environment':
        """
        从字符串创建环境枚举
        
        Args:
            env_str: 环境字符串
            
        Returns:
            Environment: 环境枚举值
            
        Raises:
            ValueError: 不支持的环境类型
        """
        env_str = env_str.lower().strip()
        for env in cls:
            if env.value == env_str:
                return env
        
        # 支持常见的别名
        aliases = {
            'dev': cls.DEVELOPMENT,
            'develop': cls.DEVELOPMENT,
            'test': cls.TESTING,
            'stage': cls.STAGING,
            'prod': cls.PRODUCTION,
            'production': cls.PRODUCTION
        }
        
        if env_str in aliases:
            return aliases[env_str]
        
        raise ValueError(f"不支持的环境类型: {env_str}. 支持的环境: {', '.join([e.value for e in cls])}")
    
    def is_production(self) -> bool:
        """是否为生产环境"""
        return self == Environment.PRODUCTION
    
    def is_development(self) -> bool:
        """是否为开发环境"""
        return self == Environment.DEVELOPMENT
    
    def is_testing(self) -> bool:
        """是否为测试环境"""
        return self == Environment.TESTING
    
    def is_staging(self) -> bool:
        """是否为预发布环境"""
        return self == Environment.STAGING


class EnvironmentConfig:
    """
    环境感知配置管理器
    
    根据当前环境提供不同的配置策略和验证规则
    """
    
    # 环境变量名称
    ENV_VAR_NAME = "DJANGO_ENV"
    
    # 默认环境
    DEFAULT_ENVIRONMENT = Environment.DEVELOPMENT
    
    def __init__(self, env_override: Optional[str] = None):
        """
        初始化环境配置
        
        Args:
            env_override: 强制指定的环境类型，主要用于测试
        """
        self._env = self._detect_environment(env_override)
        self._config_cache: Dict[str, Any] = {}
    
    def _detect_environment(self, env_override: Optional[str] = None) -> Environment:
        """
        检测当前环境
        
        检测优先级：
        1. 方法参数 env_override
        2. 环境变量 DJANGO_ENV
        3. 默认环境 DEVELOPMENT
        
        Args:
            env_override: 强制指定的环境类型
            
        Returns:
            Environment: 检测到的环境类型
        """
        # 1. 检查方法参数
        if env_override:
            try:
                return Environment.from_string(env_override)
            except ValueError:
                # 忽略无效的覆盖值，继续检测
                pass
        
        # 2. 检查环境变量
        env_value = os.getenv(self.ENV_VAR_NAME)
        if env_value:
            try:
                return Environment.from_string(env_value)
            except ValueError:
                # 环境变量值无效，使用默认环境
                pass
        
        # 3. 返回默认环境
        return self.DEFAULT_ENVIRONMENT
    
    @property
    def current_environment(self) -> Environment:
        """
        获取当前环境
        
        Returns:
            Environment: 当前环境类型
        """
        return self._env
    
    @property
    def environment_name(self) -> str:
        """
        获取当前环境名称
        
        Returns:
            str: 环境名称字符串
        """
        return self._env.value
    
    def is_production(self) -> bool:
        """
        是否为生产环境
        
        Returns:
            bool: True表示生产环境
        """
        return self._env.is_production()
    
    def is_development(self) -> bool:
        """
        是否为开发环境
        
        Returns:
            bool: True表示开发环境
        """
        return self._env.is_development()
    
    def is_testing(self) -> bool:
        """
        是否为测试环境
        
        Returns:
            bool: True表示测试环境
        """
        return self._env.is_testing()
    
    def is_staging(self) -> bool:
        """
        是否为预发布环境
        
        Returns:
            bool: True表示预发布环境
        """
        return self._env.is_staging()
    
    def get_env_specific_config(self, base_config: Dict[str, Any]) -> Dict[str, Any]:
        """
        获取环境特定配置
        
        根据当前环境对基础配置进行调整和扩展
        
        Args:
            base_config: 基础配置字典
            
        Returns:
            Dict[str, Any]: 环境特定的配置字典
        """
        # 复制基础配置
        env_config = base_config.copy()
        
        # 根据环境类型调整配置
        if self.is_development():
            env_config.update(self._get_development_config())
        elif self.is_testing():
            env_config.update(self._get_testing_config())
        elif self.is_staging():
            env_config.update(self._get_staging_config())
        elif self.is_production():
            env_config.update(self._get_production_config())
        
        return env_config
    
    def _get_development_config(self) -> Dict[str, Any]:
        """
        获取开发环境特定配置
        
        Returns:
            Dict[str, Any]: 开发环境配置
        """
        return {
            'django.debug': True,
            'django.allowed_hosts': ['localhost', '127.0.0.1', '0.0.0.0'],
            'performance.rate_limit.enabled': False,
            'logging.level': 'DEBUG',
            'cache.timeout': 60,  # 短缓存时间便于开发调试
        }
    
    def _get_testing_config(self) -> Dict[str, Any]:
        """
        获取测试环境特定配置
        
        Returns:
            Dict[str, Any]: 测试环境配置
        """
        return {
            'django.debug': False,
            'django.allowed_hosts': ['testserver', 'localhost'],
            'database.name': ':memory:',  # 使用内存数据库
            'performance.rate_limit.enabled': False,
            'logging.level': 'WARNING',
            'cache.timeout': 1,  # 极短缓存时间
        }
    
    def _get_staging_config(self) -> Dict[str, Any]:
        """
        获取预发布环境特定配置
        
        Returns:
            Dict[str, Any]: 预发布环境配置
        """
        return {
            'django.debug': False,
            'performance.rate_limit.enabled': True,
            'logging.level': 'INFO',
            'cache.timeout': 300,
        }
    
    def _get_production_config(self) -> Dict[str, Any]:
        """
        获取生产环境特定配置
        
        Returns:
            Dict[str, Any]: 生产环境配置
        """
        return {
            'django.debug': False,
            'performance.rate_limit.enabled': True,
            'logging.level': 'WARNING',
            'cache.timeout': 3600,  # 长缓存时间
            'security.strict_mode': True,
        }
    
    def validate_sensitive_config(self, key: str, value: Any, is_sensitive: bool, 
                                 env_var_name: Optional[str] = None) -> None:
        """
        验证敏感配置
        
        在生产环境中，敏感配置必须通过环境变量设置
        
        Args:
            key: 配置项键名
            value: 配置项值
            is_sensitive: 是否为敏感配置
            env_var_name: 指定的环境变量名，如果不提供则自动生成
            
        Raises:
            SensitiveConfigError: 敏感配置验证失败
        """
        if not is_sensitive:
            return
        
        if self.is_production():
            # 生产环境必须通过环境变量设置敏感配置
            var_name = env_var_name or self._get_env_var_name_for_key(key)
            env_value = os.getenv(var_name)
            
            if not env_value:
                raise SensitiveConfigError(
                    key=key,
                    environment=self.environment_name
                )
            
            # 检查敏感配置值是否可能来自不安全的源
            if self._is_potentially_unsafe_value(value):
                raise SensitiveConfigError(
                    key=key,
                    environment=self.environment_name
                )
    
    def _is_potentially_unsafe_value(self, value: Any) -> bool:
        """
        检查配置值是否可能来自不安全的源
        
        Args:
            value: 配置值
            
        Returns:
            bool: True表示可能不安全
        """
        if not isinstance(value, str):
            return False
        
        # 检查是否为明显的测试/默认值
        unsafe_patterns = [
            'test', 'demo', 'example', 'sample', 'default',
            'changeme', 'password', '123456', 'secret',
            'your_key_here', 'replace_me'
        ]
        
        value_lower = value.lower()
        for pattern in unsafe_patterns:
            if pattern in value_lower:
                return True
        
        # 检查是否过短（可能是测试值）
        if len(value) < 8:
            return True
        
        return False
    
    def validate_all_sensitive_configs(self, config: Dict[str, Any], 
                                     sensitive_keys: List[str]) -> List[str]:
        """
        验证所有敏感配置
        
        Args:
            config: 配置字典
            sensitive_keys: 敏感配置键列表
            
        Returns:
            List[str]: 验证错误列表
        """
        errors = []
        
        for key in sensitive_keys:
            try:
                value = config.get(key)
                self.validate_sensitive_config(key, value, True)
            except SensitiveConfigError as e:
                errors.append(str(e))
        
        return errors
    
    def get_sensitive_config_requirements(self) -> Dict[str, str]:
        """
        获取敏感配置要求
        
        Returns:
            Dict[str, str]: 敏感配置键到环境变量名的映射
        """
        sensitive_configs = {
            'django.secret_key': 'SECRET_KEY',
            'database.password': 'DB_PASSWORD',
            'services.moonshot.api_key': 'MOONSHOT_API_KEY',
            'chat_platforms.feishu.app_secret': 'FEISHU_APP_SECRET',
            'chat_platforms.dingtalk.app_secret': 'DINGTALK_APP_SECRET',
            'chat_platforms.wechat_work.secret': 'WECHAT_WORK_SECRET',
            'chat_platforms.telegram.bot_token': 'TELEGRAM_BOT_TOKEN',
            'chat_platforms.slack.bot_token': 'SLACK_BOT_TOKEN',
            'automation.scraper_encryption_key': 'SCRAPER_ENCRYPTION_KEY',
        }
        
        return sensitive_configs
    
    def check_sensitive_config_compliance(self) -> Dict[str, Any]:
        """
        检查敏感配置合规性
        
        Returns:
            Dict[str, Any]: 合规性检查结果
        """
        result = {
            'compliant': True,
            'errors': [],
            'warnings': [],
            'missing_env_vars': [],
            'recommendations': []
        }
        
        if not self.is_production():
            result['warnings'].append(f"当前环境 ({self.environment_name}) 不是生产环境，敏感配置检查已跳过")
            return result
        
        sensitive_configs = self.get_sensitive_config_requirements()
        
        for config_key, env_var in sensitive_configs.items():
            env_value = os.getenv(env_var)
            
            if not env_value:
                result['missing_env_vars'].append(env_var)
                result['errors'].append(f"缺少敏感配置环境变量: {env_var} (用于 {config_key})")
                result['compliant'] = False
            elif self._is_potentially_unsafe_value(env_value):
                result['warnings'].append(f"环境变量 {env_var} 的值可能不安全")
                result['recommendations'].append(f"请为 {env_var} 设置更安全的值")
        
        return result
    
    def _get_env_var_name_for_key(self, key: str) -> str:
        """
        根据配置键生成环境变量名
        
        Args:
            key: 配置键（如 'django.secret_key'）
            
        Returns:
            str: 环境变量名（如 'DJANGO_SECRET_KEY'）
        """
        # 将点号路径转换为环境变量格式
        return key.replace('.', '_').upper()
    
    def get_fallback_config(self, env_config: Dict[str, Any], key: str, default: Any = None) -> Any:
        """
        获取回退配置值
        
        当环境特定配置缺失时，按以下顺序回退：
        1. 环境特定配置
        2. 通用配置（去掉环境前缀）
        3. 父级环境配置（staging -> production, testing -> development）
        4. 默认值
        
        Args:
            env_config: 环境配置字典
            key: 配置键
            default: 默认值
            
        Returns:
            Any: 配置值
        """
        # 1. 首先尝试获取环境特定配置
        if key in env_config:
            return env_config[key]
        
        # 2. 尝试获取通用配置（去掉环境前缀）
        generic_value = self._get_generic_config_value(env_config, key)
        if generic_value is not None:
            return generic_value
        
        # 3. 尝试从父级环境获取配置
        parent_value = self._get_parent_env_config_value(env_config, key)
        if parent_value is not None:
            return parent_value
        
        # 4. 返回默认值
        return default
    
    def _get_generic_config_value(self, env_config: Dict[str, Any], key: str) -> Any:
        """
        获取通用配置值（去掉环境前缀）
        
        Args:
            env_config: 环境配置字典
            key: 配置键
            
        Returns:
            Any: 配置值，如果不存在则返回 None
        """
        if '.' in key:
            parts = key.split('.')
            if len(parts) > 1 and parts[0] in ['development', 'testing', 'staging', 'production']:
                # 如果键包含环境前缀，尝试获取通用配置
                generic_key = '.'.join(parts[1:])
                if generic_key in env_config:
                    return env_config[generic_key]
        
        return None
    
    def _get_parent_env_config_value(self, env_config: Dict[str, Any], key: str) -> Any:
        """
        从父级环境获取配置值
        
        环境继承关系：
        - testing -> development
        - staging -> production
        
        Args:
            env_config: 环境配置字典
            key: 配置键
            
        Returns:
            Any: 配置值，如果不存在则返回 None
        """
        parent_env = self._get_parent_environment()
        if not parent_env:
            return None
        
        # 构造父级环境的配置键
        parent_key = f"{parent_env.value}.{key}" if '.' in key else key
        if parent_key in env_config:
            return env_config[parent_key]
        
        # 尝试获取父级环境的通用配置
        if '.' in key:
            parts = key.split('.')
            if len(parts) > 1:
                parent_generic_key = '.'.join(parts[1:])
                if parent_generic_key in env_config:
                    return env_config[parent_generic_key]
        
        return None
    
    def _get_parent_environment(self) -> Optional[Environment]:
        """
        获取父级环境
        
        Returns:
            Optional[Environment]: 父级环境，如果没有则返回 None
        """
        if self._env == Environment.TESTING:
            return Environment.DEVELOPMENT
        elif self._env == Environment.STAGING:
            return Environment.PRODUCTION
        else:
            return None
    
    def apply_fallback_strategy(self, config: Dict[str, Any], missing_keys: List[str]) -> Dict[str, Any]:
        """
        应用回退策略到配置字典
        
        对于缺失的配置项，尝试使用回退机制填充
        
        Args:
            config: 当前配置字典
            missing_keys: 缺失的配置键列表
            
        Returns:
            Dict[str, Any]: 应用回退策略后的配置字典
        """
        result_config = config.copy()
        
        for key in missing_keys:
            fallback_value = self.get_fallback_config(config, key)
            if fallback_value is not None:
                result_config[key] = fallback_value
        
        return result_config
    
    def get_required_env_vars(self) -> List[str]:
        """
        获取当前环境必需的环境变量列表
        
        Returns:
            List[str]: 必需的环境变量名称列表
        """
        required_vars = [self.ENV_VAR_NAME]
        
        if self.is_production():
            # 生产环境必需的敏感配置环境变量
            required_vars.extend([
                'SECRET_KEY',
                'DB_PASSWORD',
                'FEISHU_APP_SECRET',
                'MOONSHOT_API_KEY',
            ])
        
        return required_vars
    
    def validate_environment_setup(self) -> List[str]:
        """
        验证环境设置
        
        检查当前环境的配置是否完整和正确
        
        Returns:
            List[str]: 验证错误列表，空列表表示验证通过
        """
        errors = []
        
        # 检查必需的环境变量
        required_vars = self.get_required_env_vars()
        for var_name in required_vars:
            if not os.getenv(var_name):
                errors.append(f"缺少必需的环境变量: {var_name}")
        
        # 生产环境特殊检查
        if self.is_production():
            # 检查调试模式
            debug_value = os.getenv('DEBUG', '').lower()
            if debug_value in ('true', '1', 'yes'):
                errors.append("生产环境不应启用调试模式")
            
            # 检查允许的主机
            allowed_hosts = os.getenv('ALLOWED_HOSTS', '')
            if not allowed_hosts or 'localhost' in allowed_hosts:
                errors.append("生产环境应配置正确的 ALLOWED_HOSTS")
        
        return errors
    
    def __str__(self) -> str:
        """字符串表示"""
        return f"EnvironmentConfig(env={self.environment_name})"
    
    def __repr__(self) -> str:
        """调试表示"""
        return f"<EnvironmentConfig env={self._env} production={self.is_production()}>"