"""
群聊提供者抽象接口和数据结构

本模块定义了平台无关的群聊操作接口，采用策略模式实现多平台支持。
所有群聊提供者都必须实现 ChatProvider 抽象基类。
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Optional
from apps.core.enums import ChatPlatform


@dataclass
class ChatResult:
    """群聊操作结果
    
    统一的群聊操作返回结果，包含成功状态、相关数据和错误信息。
    
    Attributes:
        success: 操作是否成功
        chat_id: 群聊ID（创建群聊时返回）
        chat_name: 群聊名称
        message: 操作结果消息或错误描述
        error_code: 平台特定的错误代码
        raw_response: 原始API响应数据
    """
    success: bool
    chat_id: Optional[str] = None
    chat_name: Optional[str] = None
    message: Optional[str] = None
    error_code: Optional[str] = None
    raw_response: Optional[dict] = None


@dataclass
class MessageContent:
    """消息内容
    
    统一的消息内容结构，支持文本和文件消息。
    
    Attributes:
        title: 消息标题
        text: 消息正文
        file_path: 文件路径（可选）
    """
    title: str
    text: str
    file_path: Optional[str] = None


class ChatProvider(ABC):
    """群聊提供者抽象接口
    
    定义了所有群聊提供者必须实现的标准操作接口。
    采用策略模式，使业务层代码与具体平台实现解耦。
    """
    
    @abstractmethod
    def create_chat(self, chat_name: str, owner_id: Optional[str] = None) -> ChatResult:
        """创建群聊
        
        Args:
            chat_name: 群聊名称
            owner_id: 群主ID（可选，某些平台需要）
            
        Returns:
            ChatResult: 包含群聊ID和创建结果的响应对象
            
        Raises:
            ChatCreationException: 当群聊创建失败时
        """
        pass
    
    @abstractmethod
    def send_message(self, chat_id: str, content: MessageContent) -> ChatResult:
        """发送消息到群聊
        
        Args:
            chat_id: 群聊ID
            content: 消息内容
            
        Returns:
            ChatResult: 消息发送结果
            
        Raises:
            MessageSendException: 当消息发送失败时
        """
        pass
    
    @abstractmethod
    def send_file(self, chat_id: str, file_path: str) -> ChatResult:
        """发送文件到群聊
        
        Args:
            chat_id: 群聊ID
            file_path: 文件路径
            
        Returns:
            ChatResult: 文件发送结果
            
        Raises:
            MessageSendException: 当文件发送失败时
        """
        pass
    
    @abstractmethod
    def get_chat_info(self, chat_id: str) -> ChatResult:
        """获取群聊信息
        
        Args:
            chat_id: 群聊ID
            
        Returns:
            ChatResult: 包含群聊详细信息的响应对象
            
        Raises:
            ChatProviderException: 当获取群聊信息失败时
        """
        pass
    
    @property
    @abstractmethod
    def platform(self) -> ChatPlatform:
        """返回平台类型
        
        Returns:
            ChatPlatform: 当前提供者对应的平台枚举值
        """
        pass
    
    @abstractmethod
    def is_available(self) -> bool:
        """检查平台是否可用
        
        检查平台配置是否完整，是否可以正常使用。
        
        Returns:
            bool: 平台是否可用
        """
        pass