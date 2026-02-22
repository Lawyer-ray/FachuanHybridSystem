"""
对话服务

提供 LangChain 上下文记忆功能,管理多轮对话的历史记录.
"""

import uuid
from dataclasses import dataclass
from datetime import timedelta
from typing import Any, cast

from django.db import models
from django.utils import timezone

try:
    from langchain.memory import ConversationBufferWindowMemory as _LangChainConversationBufferWindowMemory
except ModuleNotFoundError:
    _LangChainConversationBufferWindowMemory = None


@dataclass
class _HumanMessage:
    content: str


@dataclass
class _AIMessage:
    content: str


@dataclass
class _SystemMessage:
    content: str


try:
    from langchain_core.messages import AIMessage as _LCAIMessage
    from langchain_core.messages import HumanMessage as _LCHumanMessage
    from langchain_core.messages import SystemMessage as _LCSystemMessage

    HumanMessage = _LCHumanMessage
    AIMessage = _LCAIMessage
    SystemMessage = _LCSystemMessage
except ModuleNotFoundError:
    HumanMessage = _HumanMessage  # type: ignore[assignment,misc]
    AIMessage = _AIMessage  # type: ignore[assignment,misc]
    SystemMessage = _SystemMessage  # type: ignore[assignment,misc]


from apps.core.models import ConversationHistory
from apps.core.repositories.conversation_repository import ConversationHistoryRepository


class _SimpleChatMemory:
    def __init__(self, max_messages: int) -> None:
        self._max_messages = max_messages
        self.messages: list[Any] = []

    def _trim(self) -> None:
        if len(self.messages) > self._max_messages:
            self.messages = self.messages[-self._max_messages :]

    def add_message(self, message: object) -> None:
        self.messages.append(message)
        self._trim()

    def add_user_message(self, content: str) -> None:
        self.add_message(HumanMessage(content=content))

    def add_ai_message(self, content: str) -> None:
        self.add_message(AIMessage(content=content))

    def clear(self) -> None:
        self.messages = []


class _SimpleConversationBufferWindowMemory:
    def __init__(self, k: int, return_messages: bool, memory_key: str) -> None:
        self.k = k
        self.return_messages = return_messages
        self.memory_key = memory_key
        self.chat_memory = _SimpleChatMemory(max_messages=max(1, k * 2))

    def clear(self) -> None:
        self.chat_memory.clear()


class ConversationService:
    """
    对话服务

    提供基于 LangChain 的对话记忆功能,支持多轮对话的上下文管理.
    """

    def __init__(
        self,
        session_id: str | None = None,
        user_id: str | None = None,
        repository: ConversationHistoryRepository | None = None,
    ) -> None:
        """
        初始化对话服务

        Args:
            session_id: 会话ID(可选,自动生成)
            user_id: 用户ID(可选)
            repository: 对话历史仓库(可选,用于依赖注入)
        """
        self.session_id = session_id or self._generate_session_id()
        self.user_id = user_id or ""
        self._memory: Any | None = None
        self._repository = repository or ConversationHistoryRepository()

    def _generate_session_id(self) -> str:
        """生成会话ID"""
        return f"session_{uuid.uuid4().hex[:12]}"

    @property
    def memory(self) -> Any:
        """获取 LangChain 记忆对象(延迟加载)"""
        if self._memory is None:
            if _LangChainConversationBufferWindowMemory is not None:
                self._memory = _LangChainConversationBufferWindowMemory(
                    k=10,
                    return_messages=True,
                    memory_key="chat_history",
                )
            else:
                self._memory = _SimpleConversationBufferWindowMemory(
                    k=10,
                    return_messages=True,
                    memory_key="chat_history",
                )
            # 从数据库加载历史记录
            self._load_history_from_db()
        return self._memory

    def _load_history_from_db(self) -> None:
        """从数据库加载对话历史到 LangChain 记忆"""
        if self._memory is None:
            return

        history = self._repository.get_by_session(self.session_id, limit=20)

        for record in history:
            if record.role == "user":
                message: Any = HumanMessage(content=record.content)
            elif record.role == "assistant":
                message = AIMessage(content=record.content)
            elif record.role == "system":
                message = SystemMessage(content=record.content)
            else:
                continue

            # 添加到记忆中
            self._memory.chat_memory.add_message(message)

    def add_user_message(self, content: str, metadata: dict[str, Any] | None = None) -> ConversationHistory:
        """
        添加用户消息

        Args:
            content: 消息内容
            metadata: 元数据(可选)

        Returns:
            创建的对话记录
        """
        # 保存到数据库
        record = self._repository.create(
            session_id=self.session_id,
            user_id=self.user_id,
            role="user",
            content=content,
            metadata=metadata or {},
        )

        # 添加到 LangChain 记忆
        self.memory.chat_memory.add_user_message(content)

        return record

    def add_assistant_message(self, content: str, metadata: dict[str, Any] | None = None) -> ConversationHistory:
        """
        添加助手消息

        Args:
            content: 消息内容
            metadata: 元数据(可选)

        Returns:
            创建的对话记录
        """
        # 保存到数据库
        record = self._repository.create(
            session_id=self.session_id,
            user_id=self.user_id,
            role="assistant",
            content=content,
            metadata=metadata or {},
        )

        # 添加到 LangChain 记忆
        self.memory.chat_memory.add_ai_message(content)

        return record

    def add_system_message(self, content: str, metadata: dict[str, Any] | None = None) -> ConversationHistory:
        """
        添加系统消息

        Args:
            content: 消息内容
            metadata: 元数据(可选)

        Returns:
            创建的对话记录
        """
        # 保存到数据库
        record = ConversationHistory.objects.create(
            session_id=self.session_id, user_id=self.user_id, role="system", content=content, metadata=metadata or {}
        )

        # 添加到 LangChain 记忆(系统消息不加入对话记忆)

        return record

    def get_messages_for_llm(self) -> list[dict[str, Any]]:
        """
        获取用于 LLM 的消息格式

        Returns:
            消息列表,格式为 [{"role": "user", "content": "..."}, ...]
        """
        messages = []

        for message in self.memory.chat_memory.messages:
            if isinstance(message, HumanMessage):
                messages.append({"role": "user", "content": message.content})
            elif isinstance(message, AIMessage):
                messages.append({"role": "assistant", "content": message.content})
            elif isinstance(message, SystemMessage):
                messages.append({"role": "system", "content": message.content})

        return messages

    def get_conversation_summary(self) -> str:
        """
        获取对话摘要

        Returns:
            对话摘要文本
        """
        messages = self.get_messages_for_llm()
        if not messages:
            return "暂无对话记录"

        # 简单的摘要逻辑
        user_messages = [msg["content"] for msg in messages if msg["role"] == "user"]
        return f"对话轮数: {len(user_messages)}, 最近用户消息: {user_messages[-1][:50] if user_messages else '无'}..."

    def clear_history(self) -> None:
        """清除对话历史"""
        # 清除数据库记录
        ConversationHistory.objects.filter(session_id=self.session_id).delete()

        # 清除 LangChain 记忆
        if self._memory:
            self._memory.clear()

    def get_history(self, limit: int = 50) -> list[ConversationHistory]:
        """
        获取对话历史记录

        Args:
            limit: 记录数量限制

        Returns:
            对话记录列表
        """
        return list(ConversationHistory.objects.filter(session_id=self.session_id).order_by("-created_at")[:limit])

    def cleanup_old_conversations(self, days: int = 30) -> int:
        """
        清理旧对话记录

        Args:
            days: 保留天数
        """
        cutoff_date = timezone.now() - timedelta(days=days)
        deleted_count, _ = ConversationHistory.objects.filter(created_at__lt=cutoff_date).delete()
        return deleted_count

    @classmethod
    def get_user_sessions(cls, user_id: str, limit: int = 10) -> list[dict[str, Any]]:
        """
        获取用户的会话列表

        Args:
            user_id: 用户ID
            limit: 会话数量限制

        Returns:
            会话信息列表
        """
        sessions = (
            ConversationHistory.objects.filter(user_id=user_id)
            .values("session_id")
            .annotate(last_message=models.Max("created_at"), message_count=models.Count("id"))
            .order_by("-last_message")[:limit]
        )

        return list(sessions)

    def chat_with_context(self, user_message: str, system_prompt: str | None = None) -> str:
        """
        带上下文的对话

        Args:
            user_message: 用户消息
            system_prompt: 系统提示(可选)

        Returns:
            助手回复
        """
        from .wiring import get_llm_service

        # 添加用户消息到历史
        self.add_user_message(user_message)

        # 获取 LLM 服务
        llm_service = get_llm_service()

        # 构建消息列表
        messages = []

        # 添加系统提示
        if system_prompt:
            messages.append({"role": "system", "content": system_prompt})

        # 添加对话历史
        messages.extend(self.get_messages_for_llm())

        # 调用 LLM
        response = llm_service.chat(messages, temperature=0.7)

        # 添加助手回复到历史
        self.add_assistant_message(
            response.content,
            metadata={
                "model": response.model,
                "backend": response.backend,
                "tokens": response.total_tokens,
                "duration_ms": response.duration_ms,
            },
        )

        return cast(str, response.content)
