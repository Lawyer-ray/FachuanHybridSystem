"""
对话服务

提供轻量上下文记忆功能,管理多轮对话的历史记录.
"""

import uuid
from dataclasses import dataclass
from datetime import timedelta
from typing import Any

from django.db import models
from django.utils import timezone


@dataclass
class _HumanMessage:  # pragma: no cover
    content: str


@dataclass
class _AIMessage:  # pragma: no cover
    content: str


@dataclass
class _SystemMessage:  # pragma: no cover
    content: str


HumanMessage = _HumanMessage
AIMessage = _AIMessage
SystemMessage = _SystemMessage

from apps.core.models import ConversationHistory
from apps.core.repositories.conversation_repository import ConversationHistoryRepository


class _SimpleChatMemory:  # pragma: no cover
    def __init__(self, max_messages: int) -> None:  # pragma: no cover
        self._max_messages = max_messages
        self.messages: list[Any] = []

    def _trim(self) -> None:  # pragma: no cover
        if len(self.messages) > self._max_messages:
            self.messages = self.messages[-self._max_messages :]

    def add_message(self, message: object) -> None:  # pragma: no cover
        self.messages.append(message)
        self._trim()

    def add_user_message(self, content: str) -> None:  # pragma: no cover
        self.add_message(HumanMessage(content=content))

    def add_ai_message(self, content: str) -> None:  # pragma: no cover
        self.add_message(AIMessage(content=content))

    def clear(self) -> None:  # pragma: no cover
        self.messages = []


class _SimpleConversationBufferWindowMemory:  # pragma: no cover
    def __init__(self, k: int, return_messages: bool, memory_key: str) -> None:  # pragma: no cover
        self.k = k
        self.return_messages = return_messages
        self.memory_key = memory_key
        self.chat_memory = _SimpleChatMemory(max_messages=max(1, k * 2))

    def clear(self) -> None:  # pragma: no cover
        self.chat_memory.clear()


class ConversationService:  # pragma: no cover
    """
    对话服务

    提供基于内置窗口缓存的对话记忆功能,支持多轮对话的上下文管理.
    """

    def __init__(  # pragma: no cover
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

    def _generate_session_id(self) -> str:  # pragma: no cover
        """生成会话ID"""
        return f"session_{uuid.uuid4().hex[:12]}"

    @property
    def memory(self) -> Any:  # pragma: no cover
        """获取对话记忆对象(延迟加载)"""
        if self._memory is None:
            self._memory = _SimpleConversationBufferWindowMemory(
                k=10,
                return_messages=True,
                memory_key="chat_history",
            )
            # 从数据库加载历史记录
            self._load_history_from_db()
        return self._memory

    def _load_history_from_db(self) -> None:  # pragma: no cover
        """从数据库加载对话历史到会话记忆"""
        if self._memory is None:
            return

        history = self._repository.get_by_session_id(self.session_id).order_by("created_at")[:20]

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

    def add_user_message(self, content: str, metadata: dict[str, Any] | None = None) -> ConversationHistory:  # pragma: no cover
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

        # 添加到会话记忆
        self.memory.chat_memory.add_user_message(content)

        return record

    def add_assistant_message(self, content: str, metadata: dict[str, Any] | None = None) -> ConversationHistory:  # pragma: no cover
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

        # 添加到会话记忆
        self.memory.chat_memory.add_ai_message(content)

        return record

    def add_system_message(self, content: str, metadata: dict[str, Any] | None = None) -> ConversationHistory:  # pragma: no cover
        """
        添加系统消息

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
            role="system",
            content=content,
            metadata=metadata or {},
            litigation_session_id=None,
            step="",
        )

        # 系统消息不加入对话记忆

        return record

    def get_messages_for_llm(self) -> list[dict[str, Any]]:  # pragma: no cover
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

    async def aadd_user_message(self, content: str, metadata: dict[str, Any] | None = None) -> ConversationHistory:  # pragma: no cover
        """异步添加用户消息"""
        record = await self._repository.acreate(
            session_id=self.session_id,
            user_id=self.user_id,
            role="user",
            content=content,
            metadata=metadata or {},
        )
        await self._ensure_memory_loaded()
        self.memory.chat_memory.add_user_message(content)
        return record

    async def aadd_assistant_message(self, content: str, metadata: dict[str, Any] | None = None) -> ConversationHistory:  # pragma: no cover
        """异步添加助手消息"""
        record = await self._repository.acreate(
            session_id=self.session_id,
            user_id=self.user_id,
            role="assistant",
            content=content,
            metadata=metadata or {},
        )
        await self._ensure_memory_loaded()
        self.memory.chat_memory.add_ai_message(content)
        return record

    async def aadd_system_message(self, content: str, metadata: dict[str, Any] | None = None) -> ConversationHistory:  # pragma: no cover
        """异步添加系统消息"""
        record = await self._repository.acreate(
            session_id=self.session_id,
            user_id=self.user_id,
            role="system",
            content=content,
            metadata=metadata or {},
            litigation_session_id=None,
            step="",
        )
        return record

    async def _ensure_memory_loaded(self) -> None:  # pragma: no cover
        """异步安全地初始化 memory 并加载历史记录"""
        if self._memory is None:
            self._memory = _SimpleConversationBufferWindowMemory(
                k=10,
                return_messages=True,
                memory_key="chat_history",
            )
            await self._aload_history_from_db()

    async def _aload_history_from_db(self) -> None:  # pragma: no cover
        """异步从数据库加载对话历史到会话记忆"""
        if self._memory is None:
            return

        history = [
            (record.role, record.content)
            async for record in self._repository.get_by_session_id(
                self.session_id
            ).order_by("created_at")[:20]
        ]

        for role, content in history:
            if role == "user":
                message: Any = HumanMessage(content=content)
            elif role == "assistant":
                message = AIMessage(content=content)
            elif role == "system":
                message = SystemMessage(content=content)
            else:
                continue
            self._memory.chat_memory.add_message(message)

    async def achat_with_context(self, user_message: str, system_prompt: str | None = None) -> str:  # pragma: no cover
        """异步带上下文的对话"""
        from .wiring import get_llm_service

        await self.aadd_user_message(user_message)

        llm_service = get_llm_service()

        messages: list[dict[str, Any]] = []
        if system_prompt:
            messages.append({"role": "system", "content": system_prompt})
        messages.extend(self.get_messages_for_llm())

        response = await llm_service.achat(messages, temperature=0.7)

        await self.aadd_assistant_message(
            response.content,
            metadata={
                "model": response.model,
                "backend": response.backend,
                "tokens": response.total_tokens,
                "duration_ms": response.duration_ms,
            },
        )

        return str(response.content)

    def get_conversation_summary(self) -> str:  # pragma: no cover
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

    def clear_history(self) -> None:  # pragma: no cover
        """清除对话历史"""
        # 清除数据库记录
        self._repository.delete_by_session_id(self.session_id)

        # 清除会话记忆
        if self._memory:
            self._memory.clear()

    def get_history(self, limit: int = 50) -> list[ConversationHistory]:  # pragma: no cover
        """
        获取对话历史记录

        Args:
            limit: 记录数量限制

        Returns:
            对话记录列表
        """
        return list(self._repository.get_by_session_id(self.session_id).order_by("-created_at")[:limit])

    def chat_with_context(self, user_message: str, system_prompt: str | None = None) -> str:  # pragma: no cover
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

        return str(response.content)
