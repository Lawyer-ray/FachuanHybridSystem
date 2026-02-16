"""跨模块依赖注入 - 隔离 cases 模块对其他 app 的导入."""

from typing import Any


def get_chat_provider_factory() -> Any:
    """获取群聊提供者工厂类"""
    from apps.automation.services.chat.factory import ChatProviderFactory

    return ChatProviderFactory


def create_message_content(*, title: str, text: str, file_path: str | None = None) -> Any:
    """创建消息内容实例"""
    from apps.automation.services.chat.base import MessageContent

    return MessageContent(title=title, text=text, file_path=file_path)


def get_chat_result_class() -> type:
    """获取 ChatResult 类(用于类型判断)"""
    from apps.automation.services.chat.base import ChatResult

    return ChatResult


def get_enhanced_context_builder() -> Any:
    """获取增强上下文构建器实例"""
    from apps.documents.services.placeholders import EnhancedContextBuilder

    return EnhancedContextBuilder()
