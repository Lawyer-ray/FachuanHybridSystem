"""Module for middleware."""

from __future__ import annotations

"""
诉讼文书生成 Agent 中间件

实现对话历史持久化和摘要功能.

Requirements: 3.1, 3.2, 3.5, 5.1, 5.2, 5.3, 5.4
"""

import logging
from typing import TYPE_CHECKING, Any

from .interfaces import IMemoryMiddleware

if TYPE_CHECKING:
    from apps.litigation_ai.services.session.conversation_service import LitigationConversationSessionService

logger = logging.getLogger("apps.litigation_ai")


class LitigationMemoryMiddleware(IMemoryMiddleware):
    """
    诉讼文书生成的 Memory 中间件

    负责对话历史的加载和持久化,实现 Agent 执行前后的钩子.

    Attributes:
        session_id: 会话 ID
        max_messages: 加载的最大历史消息数量
        _conversation_service: ConversationService 实例(延迟加载)
    """

    def __init__(
        self,
        session_id: str,
        max_messages: int = 20,
    ) -> None:
        """
        初始化 Memory 中间件

        Args:
            session_id: 会话 ID
            max_messages: 加载的最大历史消息数量
        """
        self.session_id = session_id
        self.max_messages = max_messages
        self._conversation_service: LitigationConversationSessionService | None = None

    @property
    def conversation_service(self) -> LitigationConversationSessionService:
        """延迟加载 ConversationService"""
        if self._conversation_service is None:
            from apps.litigation_ai.services.session.conversation_service import (
                LitigationConversationSessionService as ConversationService,
            )

            self._conversation_service = ConversationService()
        return self._conversation_service

    def before_agent(
        self,
        state: dict[str, Any],
        runtime: Any | None = None,
    ) -> dict[str, Any] | None:
        """
        Agent 执行前的钩子,加载历史消息

        从数据库加载对话历史,添加到 state 的 messages 中.

        Args:
            state: 当前状态
            runtime: 运行时上下文(可选)

        Returns:
            修改后的状态
        """
        try:
            # 获取历史消息
            history = self.conversation_service.get_messages(
                session_id=self.session_id,
                limit=self.max_messages,
            )

            if history:
                # 将历史消息转换为统一消息格式
                history_messages = []
                for msg in history:
                    history_messages.append(
                        {
                            "role": msg.role,
                            "content": msg.content,
                        }
                    )

                # 合并到现有消息前面
                existing_messages = state.get("messages", [])
                state["messages"] = history_messages + existing_messages

                logger.info(
                    "加载历史消息",
                    extra={
                        "session_id": self.session_id,
                        "history_count": len(history_messages),
                    },
                )

            return state

        except Exception as e:
            logger.error(
                "加载历史消息失败",
                extra={
                    "session_id": self.session_id,
                    "error": str(e),
                },
            )
            return state

    def after_agent(
        self,
        state: dict[str, Any],
        runtime: Any | None = None,
    ) -> dict[str, Any] | None:
        """
        Agent 执行后的钩子,保存新消息

        将 Agent 生成的响应保存到数据库.

        Args:
            state: 当前状态
            runtime: 运行时上下文(可选)

        Returns:
            修改后的状态
        """
        try:
            messages = state.get("messages", [])
            if not messages:
                return state

            # 获取最后一条消息(应该是 assistant 的响应)
            last_message = messages[-1]

            # 兼容消息对象形式
            if hasattr(last_message, "type"):
                role = last_message.type
                content = last_message.content
                tool_calls = getattr(last_message, "tool_calls", [])
            elif isinstance(last_message, dict):
                role = last_message.get("role", "assistant")
                content = last_message.get("content", "")
                tool_calls = last_message.get("tool_calls", [])
            else:
                return state

            # 只保存 assistant 消息
            if role in ("assistant", "ai"):
                self.conversation_service.add_message(
                    session_id=self.session_id,
                    role="assistant",
                    content=content,
                    metadata={"tool_calls": tool_calls} if tool_calls else {},
                )

                logger.info(
                    "保存 Assistant 消息",
                    extra={
                        "session_id": self.session_id,
                        "content_length": len(content),
                        "has_tool_calls": bool(tool_calls),
                    },
                )

            return state

        except Exception as e:
            logger.error(
                "保存消息失败",
                extra={
                    "session_id": self.session_id,
                    "error": str(e),
                },
            )
            return state

    def save_user_message(self, content: str, metadata: dict[str, Any] | None = None) -> None:
        """
        保存用户消息

        Args:
            content: 消息内容
            metadata: 消息元数据
        """
        try:
            self.conversation_service.add_message(
                session_id=self.session_id,
                role="user",
                content=content,
                metadata=metadata or {},
            )
        except Exception as e:
            logger.error(
                "保存用户消息失败",
                extra={
                    "session_id": self.session_id,
                    "error": str(e),
                },
            )


class SummarizationConfig:
    """
    摘要配置

    配置对话历史摘要的触发条件和保留策略.

    Attributes:
        token_threshold: 触发摘要的 token 阈值
        preserve_messages: 保留的最近消息数量
        model: 用于摘要的模型
    """

    def __init__(
        self,
        token_threshold: int = 2000,
        preserve_messages: int = 10,
        model: str | None = None,
    ) -> None:
        """
        初始化摘要配置

        Args:
            token_threshold: 触发摘要的 token 阈值
            preserve_messages: 保留的最近消息数量
            model: 用于摘要的模型(默认使用系统配置)
        """
        self.token_threshold = token_threshold
        self.preserve_messages = preserve_messages
        self.model = model

    @classmethod
    def from_settings(cls) -> SummarizationConfig:
        """
        从 Django settings 创建配置

        Returns:
            SummarizationConfig 实例
        """
        from django.conf import settings

        return cls(
            token_threshold=getattr(settings, "LITIGATION_AGENT_SUMMARIZATION_THRESHOLD", 2000),
            preserve_messages=getattr(settings, "LITIGATION_AGENT_PRESERVE_MESSAGES", 10),
            model=getattr(settings, "LITIGATION_AGENT_MODEL", None),
        )


class LitigationSummarizationMiddleware:
    """
    诉讼文书生成的摘要中间件

    当对话历史超过 token 阈值时,自动生成摘要以压缩历史.
    保留最近 N 条消息不被摘要.

    Attributes:
        session_id: 会话 ID
        config: 摘要配置
    """

    def __init__(
        self,
        session_id: str,
        config: SummarizationConfig | None = None,
    ) -> None:
        """
        初始化摘要中间件

        Args:
            session_id: 会话 ID
            config: 摘要配置
        """
        self.session_id = session_id
        self.config = config or SummarizationConfig.from_settings()

    def should_summarize(self, messages: list[dict[str, Any]]) -> bool:
        """
        判断是否需要摘要

        Args:
            messages: 消息列表

        Returns:
            True 表示需要摘要
        """
        # 简单估算 token 数量(每个字符约 0.5 token)
        total_chars = sum(len(m.get("content", "")) for m in messages)
        estimated_tokens = total_chars * 0.5

        return estimated_tokens > self.config.token_threshold

    async def summarize(
        self,
        messages: list[dict[str, Any]],
    ) -> dict[str, Any]:
        """
        生成对话摘要

        保留最近 N 条消息,将之前的消息摘要为一条系统消息.

        Args:
            messages: 消息列表

        Returns:
            包含摘要和保留消息的字典
        """
        if len(messages) <= self.config.preserve_messages:
            return {"messages": messages, "summary": None}

        # 分离要摘要的消息和要保留的消息
        to_summarize = messages[: -self.config.preserve_messages]
        to_preserve = messages[-self.config.preserve_messages :]

        # 生成摘要
        summary_prompt = self._build_summary_prompt(to_summarize)

        try:
            from asgiref.sync import sync_to_async

            from apps.litigation_ai.services.wiring import get_llm_service

            llm_service = await sync_to_async(get_llm_service, thread_sensitive=True)()
            response = await llm_service.achat(
                messages=[
                    {"role": "system", "content": "你是一个对话摘要助手.请简洁地总结以下对话的要点."},
                    {"role": "user", "content": summary_prompt},
                ],
                model=self.config.model,
                temperature=0.3,
            )

            summary = response.content or ""

            # 构建新的消息列表
            new_messages = [
                {"role": "system", "content": f"[对话历史摘要]\n{summary}"},
            ] + to_preserve

            logger.info(
                "生成对话摘要",
                extra={
                    "session_id": self.session_id,
                    "summarized_count": len(to_summarize),
                    "preserved_count": len(to_preserve),
                },
            )

            return {"messages": new_messages, "summary": summary}

        except Exception as e:
            logger.error(
                "生成摘要失败",
                extra={
                    "session_id": self.session_id,
                    "error": str(e),
                },
            )
            return {"messages": messages, "summary": None}

    def _build_summary_prompt(self, messages: list[dict[str, Any]]) -> str:
        """
        构建摘要提示词

        Args:
            messages: 要摘要的消息列表

        Returns:
            摘要提示词
        """
        lines = []
        for msg in messages:
            role = msg.get("role", "unknown")
            content = msg.get("content", "")
            lines.append(f"{role}: {content[:200]}...")

        return "\n".join(lines)
