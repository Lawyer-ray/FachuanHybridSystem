"""
诉讼文书生成 Agent 服务

提供 Agent 的创建、消息处理、证据选择等功能.
遵循四层架构规范,支持依赖注入.

Requirements: 1.4, 7.1, 7.2, 7.4, 7.5, 8.1, 8.2, 8.4, 8.5
"""

from django.utils.translation import gettext_lazy as _
import logging
from collections.abc import Callable
from typing import Any

from apps.core.exceptions import NotFoundError
from apps.litigation_ai.agent.interfaces import ILitigationAgentService

logger = logging.getLogger("apps.litigation_ai")


class LitigationAgentService(ILitigationAgentService):
    """
    诉讼文书生成 Agent 服务

    负责管理 Agent 实例、处理用户消息、管理会话状态.
    遵循四层架构规范,使用依赖注入支持测试.

    Attributes:
        _agent_factory: Agent 工厂实例
        _conversation_service: 对话服务实例
        _agents: 会话 ID 到 Agent 实例的映射
    """

    def __init__(
        self,
        agent_factory: Any | None = None,
        conversation_service: Any | None = None,
    ) -> None:
        """
        初始化 Agent 服务

        Args:
            agent_factory: Agent 工厂实例(可选,支持依赖注入)
            conversation_service: 对话服务实例(可选,支持依赖注入)
        """
        self._agent_factory = agent_factory
        self._conversation_service = conversation_service
        self._agents: dict[str, Any] = {}

    @property
    def agent_factory(self) -> Any:
        """延迟加载 Agent 工厂"""
        if self._agent_factory is None:
            from apps.litigation_ai.agent.factory import LitigationAgentFactory

            self._agent_factory = LitigationAgentFactory()
        return self._agent_factory

    @property
    def conversation_service(self) -> Any:
        """延迟加载对话服务"""
        if self._conversation_service is None:
            from .conversation_service import ConversationService

            self._conversation_service = ConversationService()
        return self._conversation_service

    def get_or_create_agent(self, session_id: str, case_id: int) -> Any:
        """
        获取或创建 Agent 实例

        Args:
            session_id: 会话 ID
            case_id: 案件 ID

        Returns:
            Agent 实例
        """
        if session_id not in self._agents:
            self._agents[session_id] = self.agent_factory.create_agent(
                session_id=session_id,
                case_id=case_id,
            )
            logger.info("创建新 Agent 实例", extra={"session_id": session_id, "case_id": case_id})
        return self._agents[session_id]

    async def handle_message(
        self,
        session_id: str,
        case_id: int,
        user_message: str,
        metadata: dict[str, Any] | None = None,
        stream_callback: Callable[[str], Any] | None = None,
    ) -> dict[str, Any]:
        """
        处理用户消息

        Args:
            session_id: 会话 ID
            case_id: 案件 ID
            user_message: 用户消息内容
            metadata: 消息元数据
            stream_callback: 流式响应回调

        Returns:
            响应字典,包含 type、content、metadata 字段
        """
        from asgiref.sync import sync_to_async

        logger.info(
            "处理用户消息",
            extra={
                "session_id": session_id,
                "case_id": case_id,
                "message_length": len(user_message),
            },
        )

        # 保存用户消息
        await sync_to_async(self.conversation_service.add_message)(
            session_id=session_id,
            role="user",
            content=user_message,
            metadata=metadata or {},
        )

        # 获取 Agent
        agent = self.get_or_create_agent(session_id, case_id)

        # 调用 Agent
        if stream_callback:
            result = await agent.astream(
                {"messages": [{"role": "user", "content": user_message}]},
                stream_callback=stream_callback,
            )
        else:
            result = await agent.ainvoke(
                {
                    "messages": [{"role": "user", "content": user_message}],
                }
            )

        # 提取响应内容
        response_content = self._extract_response_content(result)

        # 保存 Assistant 消息
        await sync_to_async(self.conversation_service.add_message)(
            session_id=session_id,
            role="assistant",
            content=response_content,
            metadata={"tool_calls": result.get("tool_calls", [])},
        )

        return {
            "type": "assistant_complete",
            "content": response_content,
            "metadata": {
                "tool_calls": result.get("tool_calls", []),
            },
        }

    async def handle_evidence_selection(
        self,
        session_id: str,
        case_id: int,
        evidence_item_ids: list[int],
        our_evidence_item_ids: list[int],
        opponent_evidence_item_ids: list[int],
    ) -> dict[str, Any]:
        """
        处理证据选择

        Args:
            session_id: 会话 ID
            case_id: 案件 ID
            evidence_item_ids: 所有选中的证据项 ID
            our_evidence_item_ids: 我方证据项 ID
            opponent_evidence_item_ids: 对方证据项 ID

        Returns:
            响应字典
        """
        from asgiref.sync import sync_to_async

        from apps.litigation_ai.models import LitigationSession

        logger.info(
            "处理证据选择",
            extra={
                "session_id": session_id,
                "our_count": len(our_evidence_item_ids),
                "opponent_count": len(opponent_evidence_item_ids),
            },
        )

        # 更新会话元数据
        @sync_to_async
        def update_session() -> None:
            session = LitigationSession.objects.filter(session_id=session_id).first()
            if not session:
                raise NotFoundError(
                    message=_("会话不存在"),
                    code="SESSION_NOT_FOUND",
                    errors={"session_id": session_id},
                )

            metadata = session.metadata or {}
            metadata.update(
                {
                    "evidence_item_ids": evidence_item_ids,
                    "our_evidence_item_ids": our_evidence_item_ids,
                    "opponent_evidence_item_ids": opponent_evidence_item_ids,
                }
            )
            session.metadata = metadata
            session.save(update_fields=["metadata"])

        await update_session()

        # 构建消息让 Agent 处理
        message = (
            f"用户已选择证据:我方证据 {len(our_evidence_item_ids)} 项,"
            f"对方证据 {len(opponent_evidence_item_ids)} 项.请开始生成文书."
        )

        return await self.handle_message(
            session_id=session_id,
            case_id=case_id,
            user_message=message,
        )

    def cleanup_agent(self, session_id: str) -> None:
        """
        清理 Agent 实例

        Args:
            session_id: 会话 ID
        """
        if session_id in self._agents:
            del self._agents[session_id]
            logger.info("清理 Agent 实例", extra={"session_id": session_id})

    def _extract_response_content(self, result: dict[str, Any]) -> str:
        """
        从 Agent 结果中提取响应内容

        Args:
            result: Agent 返回的结果

        Returns:
            响应内容字符串
        """
        messages = result.get("messages", [])
        if not messages:
            return ""

        # 获取最后一条 assistant 消息
        for msg in reversed(messages):
            if hasattr(msg, "type") and msg.type in ("assistant", "ai"):
                return str(msg.content)
            elif isinstance(msg, dict) and msg.get("role") in ("assistant", "ai"):
                return str(msg.get("content", ""))

        return ""
