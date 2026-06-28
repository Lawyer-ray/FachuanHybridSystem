"""
群聊提供者抽象接口和数据结构

本模块定义了平台无关的群聊操作接口，采用策略模式实现多平台支持。
所有群聊提供者都必须实现 ChatProvider 抽象基类。
"""

from abc import ABC, abstractmethod

from asgiref.sync import sync_to_async

from apps.core.dto.chat import ChatResult, MessageContent
from apps.core.models.enums import ChatPlatform

__all__ = ["ChatResult", "MessageContent", "ChatProvider"]


class ChatProvider(ABC):  # pragma: no cover
    """群聊提供者抽象接口

    定义了所有群聊提供者必须实现的标准操作接口。
    采用策略模式，使业务层代码与具体平台实现解耦。

    每个操作都提供同步和异步两种版本：
    - 同步方法（create_chat, send_message, send_file, ...）：供同步上下文调用
    - 异步方法（acreate_chat, asend_message, asend_file, ...）：供异步上下文调用

    异步方法的默认实现会通过 sync_to_async 包装对应的同步方法，
    子类可以原生实现异步版本以避免线程池开销。
    """

    @abstractmethod
    def create_chat(self, chat_name: str, owner_id: str | None = None) -> ChatResult:  # pragma: no cover
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

    async def acreate_chat(self, chat_name: str, owner_id: str | None = None) -> ChatResult:
        """异步创建群聊（默认通过 sync_to_async 包装同步版本）

        子类可覆盖此方法提供原生异步实现。

        Args:
            chat_name: 群聊名称
            owner_id: 群主ID（可选，某些平台需要）

        Returns:
            ChatResult: 包含群聊ID和创建结果的响应对象
        """
        return await sync_to_async(self.create_chat)(chat_name, owner_id)

    @abstractmethod
    def send_message(self, chat_id: str, content: MessageContent) -> ChatResult:  # pragma: no cover
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

    async def asend_message(self, chat_id: str, content: MessageContent) -> ChatResult:
        """异步发送消息到群聊（默认通过 sync_to_async 包装同步版本）

        子类可覆盖此方法提供原生异步实现。

        Args:
            chat_id: 群聊ID
            content: 消息内容

        Returns:
            ChatResult: 消息发送结果
        """
        return await sync_to_async(self.send_message)(chat_id, content)

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

    async def asend_file(self, chat_id: str, file_path: str) -> ChatResult:
        """异步发送文件到群聊（默认通过 sync_to_async 包装同步版本）

        子类可覆盖此方法提供原生异步实现。

        Args:
            chat_id: 群聊ID
            file_path: 文件路径

        Returns:
            ChatResult: 文件发送结果
        """
        return await sync_to_async(self.send_file)(chat_id, file_path)

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

    async def aget_chat_info(self, chat_id: str) -> ChatResult:
        """异步获取群聊信息（默认通过 sync_to_async 包装同步版本）

        子类可覆盖此方法提供原生异步实现。

        Args:
            chat_id: 群聊ID

        Returns:
            ChatResult: 包含群聊详细信息的响应对象
        """
        return await sync_to_async(self.get_chat_info)(chat_id)

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

    async def ais_available(self) -> bool:
        """异步检查平台是否可用（默认通过 sync_to_async 包装同步版本）

        子类可覆盖此方法提供原生异步实现。

        Returns:
            bool: 平台是否可用
        """
        return await sync_to_async(self.is_available)()
