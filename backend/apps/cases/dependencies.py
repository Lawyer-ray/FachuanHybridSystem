"""跨模块依赖注入 - 隔离 cases 模块对其他 app 的导入."""

from __future__ import annotations

from typing import TYPE_CHECKING, cast

if TYPE_CHECKING:
    from apps.automation.services.chat.factory import ChatProviderFactory
    from apps.core.dto.chat import MessageContent
    from apps.documents.services.placeholders import EnhancedContextBuilder


def get_chat_provider_factory() -> type[ChatProviderFactory]:
    """获取群聊提供者工厂类"""
    from apps.automation.services.chat.factory import ChatProviderFactory

    return ChatProviderFactory


def create_message_content(*, title: str, text: str, file_path: str | None = None) -> MessageContent:
    """创建消息内容实例"""
    from apps.automation.services.chat.base import MessageContent

    return MessageContent(title=title, text=text, file_path=file_path)


def get_enhanced_context_builder() -> EnhancedContextBuilder:
    """获取增强上下文构建器实例"""
    from apps.documents.services.placeholders import EnhancedContextBuilder

    return EnhancedContextBuilder()
