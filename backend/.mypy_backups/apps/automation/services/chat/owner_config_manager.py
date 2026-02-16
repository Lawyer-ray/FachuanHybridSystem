"""
群主配置管理器

本模块实现群主配置的加载、验证和获取逻辑，支持环境变量配置和默认值处理。
为飞书群聊群主设置增强功能提供配置管理支持。

主要功能：
- 从环境变量加载默认群主配置
- 验证群主ID格式的有效性
- 提供有效群主ID的获取逻辑（优先使用指定值，否则使用默认值）
- 支持测试环境的特殊处理
- 处理空值和无效值的情况

设计原则：
- 单一职责：专注于群主配置管理
- 配置优先级：指定值 > 默认值 > None
- 输入验证：严格验证群主ID格式
- 环境感知：支持测试和生产环境的不同配置
"""

import logging
import os
import re
from typing import Optional
from django.conf import settings

from apps.core.exceptions import ValidationException
from apps.core.exceptions import ConfigurationException

logger = logging.getLogger(__name__)


class OwnerConfigManager:
    """群主配置管理器
    
    负责管理群主配置的加载、验证和获取逻辑。
    支持从环境变量和Django settings中读取配置。
    
    配置优先级：
    1. 方法调用时指定的群主ID
    2. 环境变量中的默认群主ID
    3. Django settings中的默认群主ID
    4. None（无群主）
    
    支持的群主ID格式：
    - open_id: ou_xxxxxx（飞书用户的open_id）
    - union_id: on_xxxxxx（飞书用户的union_id）
    
    Requirements: 2.1, 2.2, 2.4
    """
    
    # 飞书用户ID格式正则表达式
    # 飞书ID使用32位十六进制字符（0-9, a-f）
    OPEN_ID_PATTERN = re.compile(r'^ou_[a-fA-F0-9]{32}$')
    UNION_ID_PATTERN = re.compile(r'^on_[a-fA-F0-9]{32}$')
    
    def __init__(self):
        """初始化群主配置管理器
        
        加载配置并进行基本验证。
        """
        self._config = self._load_config()
        self._default_owner_id = self._load_default_owner_id()
        
        logger.debug("OwnerConfigManager 初始化完成")
    
    def _load_config(self) -> dict:
        """加载配置
        
        优先从Admin后台SystemConfig加载，然后从Django settings和环境变量中加载。
        
        配置优先级：
        1. Admin后台 SystemConfig (feishu分类)
        2. Django settings
        3. 环境变量
        4. 默认值
        
        Returns:
            dict: 配置字典
            
        Raises:
            ConfigurationException: 当配置格式错误时
        """
        try:
            config = {}
            
            # 优先级1: 从Admin后台SystemConfig获取飞书配置
            try:
                from apps.core.models import SystemConfig
                db_configs = SystemConfig.get_category_configs('feishu')
                
                if db_configs:
                    # 映射数据库配置键到内部配置键
                    key_mapping = {
                        'FEISHU_APP_ID': 'APP_ID',
                        'FEISHU_APP_SECRET': 'APP_SECRET',
                        'FEISHU_TIMEOUT': 'TIMEOUT',
                        'FEISHU_DEFAULT_OWNER_ID': 'DEFAULT_OWNER_ID',
                        'FEISHU_WEBHOOK_URL': 'WEBHOOK_URL',
                    }
                    
                    for db_key, internal_key in key_mapping.items():
                        if db_key in db_configs and db_configs[db_key]:
                            config[internal_key] = db_configs[db_key]
                    
                    logger.debug(f"从SystemConfig加载飞书配置: {list(config.keys())}")
                    
            except Exception as e:
                logger.debug(f"从SystemConfig加载配置失败，回退到settings: {str(e)}")
            
            # 优先级2: 从Django settings获取飞书配置（不覆盖已有配置）
            feishu_config = getattr(settings, 'FEISHU', {})
            case_chat_config = getattr(settings, 'CASE_CHAT', {})
            
            if 'APP_ID' not in config:
                config['APP_ID'] = feishu_config.get('APP_ID')
            if 'APP_SECRET' not in config:
                config['APP_SECRET'] = feishu_config.get('APP_SECRET')
            if 'TIMEOUT' not in config:
                config['TIMEOUT'] = feishu_config.get('TIMEOUT', 30)
            if 'DEFAULT_OWNER_ID' not in config:
                config['DEFAULT_OWNER_ID'] = case_chat_config.get('DEFAULT_OWNER_ID')
            
            # 优先级3: 环境变量配置（测试和验证相关）
            config['TEST_MODE'] = os.environ.get('FEISHU_TEST_MODE', 'false').lower() == 'true'
            config['TEST_OWNER_ID'] = os.environ.get('FEISHU_TEST_OWNER_ID')
            config['OWNER_VALIDATION_ENABLED'] = os.environ.get('FEISHU_OWNER_VALIDATION_ENABLED', 'true').lower() == 'true'
            config['OWNER_RETRY_ENABLED'] = os.environ.get('FEISHU_OWNER_RETRY_ENABLED', 'true').lower() == 'true'
            config['OWNER_MAX_RETRIES'] = int(os.environ.get('FEISHU_OWNER_MAX_RETRIES', 3))
            
            # 确保TIMEOUT是整数类型
            if 'TIMEOUT' in config and config['TIMEOUT']:
                try:
                    config['TIMEOUT'] = int(config['TIMEOUT'])
                except (ValueError, TypeError):
                    config['TIMEOUT'] = 30
            else:
                config['TIMEOUT'] = 30
            
            logger.debug(f"已加载群主配置: test_mode={config['TEST_MODE']}, "
                        f"validation_enabled={config['OWNER_VALIDATION_ENABLED']}, "
                        f"has_default_owner={bool(config.get('DEFAULT_OWNER_ID'))}")
            
            return config
            
        except Exception as e:
            logger.error(f"加载群主配置失败: {str(e)}")
            raise ConfigurationException(
                message=f"无法加载群主配置: {str(e)}",
                platform="feishu",
                errors={"original_error": str(e)}
            ) from e
    
    def _load_default_owner_id(self) -> Optional[str]:
        """加载默认群主ID
        
        直接从已加载的配置中获取默认群主ID。
        配置加载时已按优先级处理：SystemConfig > Django settings > 环境变量
        
        Returns:
            Optional[str]: 默认群主ID，如果未配置则返回None
            
        Requirements: 2.1
        """
        # 从已加载的配置中获取（已按优先级处理）
        default_owner = self._config.get('DEFAULT_OWNER_ID')
        if default_owner and default_owner.strip():
            default_owner = default_owner.strip()
            logger.debug(f"使用默认群主ID: {default_owner}")
            return default_owner
        
        # 测试环境特殊处理
        if self.is_test_environment():
            test_owner = self._config.get('TEST_OWNER_ID')
            if test_owner and test_owner.strip():
                test_owner = test_owner.strip()
                logger.debug(f"从测试环境配置加载默认群主ID: {test_owner}")
                return test_owner
        
        logger.debug("未找到默认群主ID配置")
        return None
    
    def get_default_owner_id(self) -> Optional[str]:
        """获取默认群主ID
        
        返回系统配置的默认群主ID。
        
        Returns:
            Optional[str]: 默认群主ID，如果未配置则返回None
            
        Requirements: 2.1
        
        Example:
            manager = OwnerConfigManager()
            default_owner = manager.get_default_owner_id()
            if default_owner:
                print(f"默认群主: {default_owner}")
        """
        return self._default_owner_id
    
    def get_effective_owner_id(self, specified_owner: Optional[str]) -> Optional[str]:
        """获取有效的群主ID
        
        根据优先级规则返回有效的群主ID：
        1. 如果指定了群主ID且有效，使用指定的群主ID
        2. 否则使用默认群主ID
        3. 如果都没有，返回None
        
        Args:
            specified_owner: 指定的群主ID（可选）
            
        Returns:
            Optional[str]: 有效的群主ID，如果都没有则返回None
            
        Requirements: 2.2
        
        Example:
            manager = OwnerConfigManager()
            # 使用指定的群主
            owner = manager.get_effective_owner_id("ou_abc123def456")
            # 使用默认群主
            owner = manager.get_effective_owner_id(None)
        """
        # 优先级1: 使用指定的群主ID
        if specified_owner and specified_owner.strip():
            specified_owner = specified_owner.strip()
            
            # 如果启用了验证，检查格式
            if self._config.get('OWNER_VALIDATION_ENABLED', True):
                if self.validate_owner_id(specified_owner):
                    logger.debug(f"使用指定的群主ID: {specified_owner}")
                    return specified_owner
                else:
                    logger.warning(f"指定的群主ID格式无效，回退到默认值: {specified_owner}")
            else:
                # 未启用验证，直接使用
                logger.debug(f"使用指定的群主ID（未验证）: {specified_owner}")
                return specified_owner
        
        # 优先级2: 使用默认群主ID
        default_owner = self.get_default_owner_id()
        if default_owner:
            logger.debug(f"使用默认群主ID: {default_owner}")
            return default_owner
        
        # 都没有配置
        logger.debug("未找到有效的群主ID配置")
        return None
    
    def validate_owner_id(self, owner_id: str) -> bool:
        """验证群主ID格式是否有效
        
        检查群主ID是否符合飞书用户ID的格式要求：
        - open_id: ou_xxxxxx（32位十六进制字符）
        - union_id: on_xxxxxx（32位十六进制字符）
        
        Args:
            owner_id: 要验证的群主ID
            
        Returns:
            bool: ID格式是否有效
            
        Raises:
            ValidationException: 当ID格式无效且启用严格验证时
            
        Requirements: 2.3
        
        Example:
            manager = OwnerConfigManager()
            if manager.validate_owner_id("ou_abc123def456"):
                print("群主ID格式有效")
        """
        if not owner_id or not isinstance(owner_id, str):
            return False
        
        owner_id = owner_id.strip()
        if not owner_id:
            return False
        
        # 检查是否匹配飞书用户ID格式
        is_valid = (
            self.OPEN_ID_PATTERN.match(owner_id) or 
            self.UNION_ID_PATTERN.match(owner_id)
        )
        
        if not is_valid:
            logger.debug(f"群主ID格式验证失败: {owner_id}")
        
        return is_valid
    
    def validate_owner_id_strict(self, owner_id: str) -> None:
        """严格验证群主ID格式
        
        与validate_owner_id类似，但在验证失败时抛出异常。
        用于需要强制验证的场景。
        
        Args:
            owner_id: 要验证的群主ID
            
        Raises:
            ValidationException: 当ID格式无效时
            
        Requirements: 2.3
        
        Example:
            manager = OwnerConfigManager()
            try:
                manager.validate_owner_id_strict("invalid_id")
            except ValidationException as e:
                print(f"验证失败: {e.message}")
        """
        if not self.validate_owner_id(owner_id):
            raise ValidationException(
                message=f"群主ID格式无效: {owner_id}",
                code="INVALID_OWNER_ID_FORMAT",
                errors={
                    "owner_id": owner_id,
                    "expected_format": "ou_xxxxxx 或 on_xxxxxx（32位十六进制字符）",
                    "validation_patterns": [
                        "open_id: ou_[a-fA-F0-9]{32}",
                        "union_id: on_[a-fA-F0-9]{32}"
                    ]
                }
            )
    
    def is_test_environment(self) -> bool:
        """检查是否为测试环境
        
        根据配置判断当前是否运行在测试环境中。
        测试环境可能有不同的群主配置和验证规则。
        
        Returns:
            bool: 是否为测试环境
            
        Example:
            manager = OwnerConfigManager()
            if manager.is_test_environment():
                print("当前运行在测试环境")
        """
        return self._config.get('TEST_MODE', False)
    
    def is_validation_enabled(self) -> bool:
        """检查是否启用了群主ID验证
        
        Returns:
            bool: 是否启用验证
        """
        return self._config.get('OWNER_VALIDATION_ENABLED', True)
    
    def is_retry_enabled(self) -> bool:
        """检查是否启用了重试机制
        
        Returns:
            bool: 是否启用重试
        """
        return self._config.get('OWNER_RETRY_ENABLED', True)
    
    def get_max_retries(self) -> int:
        """获取最大重试次数
        
        Returns:
            int: 最大重试次数
        """
        return self._config.get('OWNER_MAX_RETRIES', 3)
    
    def handle_empty_owner_id(self, owner_id: Optional[str]) -> Optional[str]:
        """处理空的群主ID
        
        统一处理空值、空字符串和仅包含空白字符的群主ID。
        根据配置决定是否回退到默认值。
        
        Args:
            owner_id: 可能为空的群主ID
            
        Returns:
            Optional[str]: 处理后的群主ID，可能为None
            
        Requirements: 2.4
        
        Example:
            manager = OwnerConfigManager()
            # 处理各种空值情况
            result1 = manager.handle_empty_owner_id(None)
            result2 = manager.handle_empty_owner_id("")
            result3 = manager.handle_empty_owner_id("   ")
        """
        # 检查是否为空值
        if not owner_id or not owner_id.strip():
            logger.debug("群主ID为空，回退到默认配置")
            return self.get_default_owner_id()
        
        # 返回清理后的值
        return owner_id.strip()
    
    def get_config_summary(self) -> dict:
        """获取配置摘要
        
        返回当前配置的摘要信息，用于调试和监控。
        不包含敏感信息。
        
        Returns:
            dict: 配置摘要
            
        Example:
            manager = OwnerConfigManager()
            summary = manager.get_config_summary()
            print(f"配置摘要: {summary}")
        """
        return {
            "has_default_owner": bool(self._default_owner_id),
            "test_mode": self.is_test_environment(),
            "validation_enabled": self.is_validation_enabled(),
            "retry_enabled": self.is_retry_enabled(),
            "max_retries": self.get_max_retries(),
            "default_owner_id_prefix": self._default_owner_id[:3] if self._default_owner_id else None
        }
    
    def reload_config(self) -> None:
        """重新加载配置
        
        重新从环境变量和Django settings中加载配置。
        用于配置更新后的动态重载。
        
        Requirements: 2.5
        
        Example:
            manager = OwnerConfigManager()
            # 更新环境变量后
            manager.reload_config()
        """
        logger.info("重新加载群主配置")
        
        try:
            self._config = self._load_config()
            self._default_owner_id = self._load_default_owner_id()
            
            logger.info("群主配置重新加载完成")
            logger.debug(f"配置摘要: {self.get_config_summary()}")
            
        except Exception as e:
            logger.error(f"重新加载群主配置失败: {str(e)}")
            raise ConfigurationException(
                message=f"重新加载配置失败: {str(e)}",
                platform="feishu",
                errors={"original_error": str(e)}
            ) from e