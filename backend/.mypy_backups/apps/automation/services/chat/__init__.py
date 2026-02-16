"""
群聊服务模块

本模块提供平台无关的群聊管理功能，支持多种即时通讯平台。
采用策略模式和抽象工厂模式实现可扩展的架构设计。

主要组件:
- ChatProvider: 群聊提供者抽象接口
- ChatResult: 统一的操作结果数据结构
- MessageContent: 消息内容数据结构
- ChatProviderFactory: 群聊提供者工厂类

异常类:
- ChatProviderException: 群聊提供者异常基类
- UnsupportedPlatformException: 不支持的平台异常
- ChatCreationException: 群聊创建失败异常
- MessageSendException: 消息发送失败异常
- ConfigurationException: 配置错误异常
"""

from .base import ChatProvider, ChatResult, MessageContent
from .factory import ChatProviderFactory

# 自动注册群聊提供者
def _register_providers():
    """自动注册所有可用的群聊提供者"""
    from apps.core.enums import ChatPlatform
    
    # 避免重复注册：检查是否已经注册过
    if ChatProviderFactory.is_platform_registered(ChatPlatform.FEISHU):
        return
    
    # 注册飞书提供者
    try:
        from .feishu_provider import FeishuChatProvider
        ChatProviderFactory.register(ChatPlatform.FEISHU, FeishuChatProvider)
    except ImportError as e:
        import logging
        logger = logging.getLogger(__name__)
        logger.warning(f"无法导入飞书群聊提供者: {str(e)}")
    
    # 未来可以在这里注册其他平台提供者
    # 例如：
    # try:
    #     from .dingtalk_provider import DingtalkChatProvider
    #     if not ChatProviderFactory.is_platform_registered(ChatPlatform.DINGTALK):
    #         ChatProviderFactory.register(ChatPlatform.DINGTALK, DingtalkChatProvider)
    # except ImportError:
    #     pass

# 模块导入时自动注册提供者（避免重复注册）
_register_providers()

__all__ = [
    'ChatProvider',
    'ChatResult', 
    'MessageContent',
    'ChatProviderFactory',
]