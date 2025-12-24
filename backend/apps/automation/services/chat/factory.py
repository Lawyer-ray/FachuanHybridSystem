"""
群聊提供者工厂类

本模块实现了群聊提供者的工厂模式，负责管理和创建不同平台的群聊提供者实例。
采用抽象工厂模式，支持动态注册和获取群聊提供者。

设计原则：
- 开闭原则：对扩展开放，对修改关闭
- 依赖倒置：业务层依赖抽象接口而非具体实现
- 单例模式：工厂类使用类方法，确保全局唯一的提供者注册表

使用方式：
    # 注册提供者
    ChatProviderFactory.register(ChatPlatform.FEISHU, FeishuChatProvider)
    
    # 获取提供者实例
    provider = ChatProviderFactory.get_provider(ChatPlatform.FEISHU)
    
    # 获取可用平台列表
    platforms = ChatProviderFactory.get_available_platforms()
"""

from typing import Dict, List, Type
import logging

from apps.core.enums import ChatPlatform
from apps.core.exceptions import UnsupportedPlatformException, ConfigurationException
from .base import ChatProvider

logger = logging.getLogger(__name__)


class ChatProviderFactory:
    """群聊提供者工厂类
    
    负责管理群聊提供者的注册、创建和获取。
    使用类方法实现单例模式，确保全局唯一的提供者注册表。
    
    Attributes:
        _providers: 平台到提供者类的映射字典
        _instances: 提供者实例缓存（可选优化）
    """
    
    # 平台提供者类注册表
    _providers: Dict[ChatPlatform, Type[ChatProvider]] = {}
    
    # 提供者实例缓存（避免重复创建）
    _instances: Dict[ChatPlatform, ChatProvider] = {}
    
    @classmethod
    def register(cls, platform: ChatPlatform, provider_class: Type[ChatProvider]) -> None:
        """注册平台提供者
        
        将指定平台的提供者类注册到工厂中。
        支持运行时动态注册新的平台提供者。
        
        Args:
            platform: 群聊平台枚举值
            provider_class: 实现了 ChatProvider 接口的提供者类
            
        Raises:
            TypeError: 当 provider_class 不是 ChatProvider 的子类时
            
        Example:
            ChatProviderFactory.register(ChatPlatform.FEISHU, FeishuChatProvider)
        """
        if not issubclass(provider_class, ChatProvider):
            raise TypeError(f"提供者类 {provider_class.__name__} 必须继承 ChatProvider")
        
        cls._providers[platform] = provider_class
        
        # 清除缓存的实例（如果存在）
        if platform in cls._instances:
            del cls._instances[platform]
        
        logger.debug(f"已注册群聊提供者: {platform.value} -> {provider_class.__name__}")
    
    @classmethod
    def get_provider(cls, platform: ChatPlatform) -> ChatProvider:
        """获取平台提供者实例
        
        根据平台类型返回对应的群聊提供者实例。
        使用实例缓存避免重复创建。
        
        Args:
            platform: 群聊平台枚举值
            
        Returns:
            ChatProvider: 对应平台的群聊提供者实例
            
        Raises:
            UnsupportedPlatformException: 当平台未注册时
            ConfigurationException: 当提供者实例化失败时
            
        Example:
            provider = ChatProviderFactory.get_provider(ChatPlatform.FEISHU)
            result = provider.create_chat("测试群聊")
        """
        if platform not in cls._providers:
            available_platforms = [p.value for p in cls._providers.keys()]
            raise UnsupportedPlatformException(
                message=f"不支持的群聊平台: {platform.value}",
                platform=platform.value,
                errors={
                    "available_platforms": available_platforms,
                    "requested_platform": platform.value
                }
            )
        
        # 检查实例缓存
        if platform in cls._instances:
            return cls._instances[platform]
        
        # 创建新实例
        try:
            provider_class = cls._providers[platform]
            instance = provider_class()
            
            # 验证实例的平台属性是否正确
            if instance.platform != platform:
                raise ConfigurationException(
                    message=f"提供者实例的平台属性不匹配: 期望 {platform.value}, 实际 {instance.platform.value}",
                    platform=platform.value,
                    errors={
                        "expected_platform": platform.value,
                        "actual_platform": instance.platform.value
                    }
                )
            
            # 缓存实例
            cls._instances[platform] = instance
            
            logger.debug(f"已创建群聊提供者实例: {platform.value}")
            return instance
            
        except Exception as e:
            logger.error(f"创建群聊提供者实例失败: {platform.value}, 错误: {str(e)}")
            raise ConfigurationException(
                message=f"无法创建群聊提供者实例: {platform.value}",
                platform=platform.value,
                errors={"original_error": str(e)}
            ) from e
    
    @classmethod
    def get_available_platforms(cls) -> List[ChatPlatform]:
        """获取所有可用的群聊平台
        
        返回已注册且配置完整的群聊平台列表。
        只返回 is_available() 方法返回 True 的平台。
        
        Returns:
            List[ChatPlatform]: 可用的群聊平台列表
            
        Example:
            platforms = ChatProviderFactory.get_available_platforms()
            for platform in platforms:
                print(f"可用平台: {platform.label}")
        """
        available_platforms = []
        
        for platform in cls._providers.keys():
            try:
                provider = cls.get_provider(platform)
                if provider.is_available():
                    available_platforms.append(platform)
                else:
                    logger.debug(f"平台 {platform.value} 已注册但不可用（配置不完整）")
            except Exception as e:
                logger.warning(f"检查平台 {platform.value} 可用性时出错: {str(e)}")
                continue
        
        logger.debug(f"可用的群聊平台: {[p.value for p in available_platforms]}")
        return available_platforms
    
    @classmethod
    def is_platform_registered(cls, platform: ChatPlatform) -> bool:
        """检查平台是否已注册
        
        Args:
            platform: 群聊平台枚举值
            
        Returns:
            bool: 平台是否已注册
        """
        return platform in cls._providers
    
    @classmethod
    def get_registered_platforms(cls) -> List[ChatPlatform]:
        """获取所有已注册的平台
        
        返回所有已注册的平台列表，不检查可用性。
        
        Returns:
            List[ChatPlatform]: 已注册的平台列表
        """
        return list(cls._providers.keys())
    
    @classmethod
    def clear_cache(cls) -> None:
        """清除提供者实例缓存
        
        用于测试或配置更新后强制重新创建实例。
        """
        cls._instances.clear()
        logger.debug("已清除群聊提供者实例缓存")
    
    @classmethod
    def unregister(cls, platform: ChatPlatform) -> bool:
        """注销平台提供者
        
        从工厂中移除指定平台的提供者注册。
        主要用于测试场景。
        
        Args:
            platform: 要注销的群聊平台
            
        Returns:
            bool: 是否成功注销（平台是否存在）
        """
        if platform in cls._providers:
            del cls._providers[platform]
            if platform in cls._instances:
                del cls._instances[platform]
            logger.info(f"已注销群聊提供者: {platform.value}")
            return True
        return False