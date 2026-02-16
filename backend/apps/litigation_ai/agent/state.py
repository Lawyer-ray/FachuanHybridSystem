"""
诉讼文书生成 Agent 状态定义

定义 Agent 运行时的状态结构,包括会话信息、文书生成上下文、证据选择等.
兼容 LangChain/LangGraph 的状态管理模式.

Requirements: 7.1, 7.3
"""

from collections.abc import Sequence
from typing import Annotated, Any

from langchain_core.messages import BaseMessage
from pydantic import BaseModel, Field


def _merge_messages(
    left: Sequence[BaseMessage | dict[str, Any]],
    right: Sequence[BaseMessage | dict[str, Any]],
) -> list[BaseMessage | dict[str, Any]]:
    """
    合并消息列表,用于 LangGraph 风格的状态更新

    Args:
        left: 现有消息列表
        right: 新增消息列表

    Returns:
        合并后的消息列表
    """
    return list(left) + list(right)


class LitigationAgentState(BaseModel):
    """
    诉讼文书生成 Agent 状态

    兼容 LangChain/LangGraph 的状态定义模式,使用 Pydantic BaseModel.
    该状态会被持久化到 LitigationSession.metadata 中.

    设计说明:
    - messages 字段使用 Annotated 类型,支持 LangGraph 风格的状态合并
    - 支持 LangChain BaseMessage 和普通 dict 两种消息格式
    - 提供 to_metadata() 和 from_metadata() 方法实现状态持久化

    Attributes:
        session_id: 会话唯一标识
        case_id: 关联的案件 ID
        document_type: 文书类型 (complaint/defense/counterclaim/counterclaim_defense)
        litigation_goal: 诉讼目标描述
        evidence_item_ids: 所有选中的证据项 ID
        our_evidence_item_ids: 我方证据项 ID
        opponent_evidence_item_ids: 对方证据项 ID
        draft: 当前生成的草稿内容
        draft_version: 草稿版本号
        messages: 对话消息列表(LangChain 格式)
        collected_context: 已收集的上下文信息
        conversation_summary: 对话摘要(SummarizationMiddleware 生成)
        tool_call_history: 工具调用历史
    """

    # 会话信息
    session_id: str = Field(default="", description="会话唯一标识")
    case_id: int = Field(default=0, description="关联的案件 ID")

    # 文书生成上下文
    document_type: str | None = Field(
        default=None,
        description=(
            "文书类型: complaint(起诉状), defense(答辩状), counterclaim(反诉状), counterclaim_defense(反诉答辩状)"
        ),
    )
    litigation_goal: str | None = Field(default=None, description="诉讼目标描述")

    # 证据选择
    evidence_item_ids: list[int] = Field(default_factory=list, description="所有选中的证据项 ID")
    our_evidence_item_ids: list[int] = Field(default_factory=list, description="我方证据项 ID")
    opponent_evidence_item_ids: list[int] = Field(default_factory=list, description="对方证据项 ID")

    # 生成结果
    draft: dict[str, Any] | None = Field(default=None, description="当前生成的草稿内容")
    draft_version: int = Field(default=0, description="草稿版本号")

    # 对话消息(LangChain 格式,支持 BaseMessage 和 dict)
    # 使用 Annotated 支持 LangGraph 风格的状态合并
    messages: Annotated[list[BaseMessage | dict[str, Any]], _merge_messages] = Field(
        default_factory=list, description="对话消息列表,支持 LangChain BaseMessage 和 dict 格式"
    )

    # 已收集的上下文
    collected_context: dict[str, Any] = Field(
        default_factory=dict, description="已收集的上下文信息,如案件信息、证据摘要等"
    )

    # 对话摘要(SummarizationMiddleware 生成)
    conversation_summary: str | None = Field(default=None, description="对话历史摘要,由 SummarizationMiddleware 生成")

    # 工具调用历史
    tool_call_history: list[dict[str, Any]] = Field(default_factory=list, description="工具调用历史记录")

    model_config: dict[str, Any] = {  # type: ignore[misc,assignment]
        # 允许任意类型(兼容 LangChain 对象)
        "arbitrary_types_allowed": True,
    }

    def to_metadata(self) -> dict[str, Any]:
        """
        转换为可存储的 metadata 字典

        将 Agent 状态序列化为可存储到数据库的格式.
        注意:messages 中的 BaseMessage 对象会被转换为 dict 格式.

        Returns:
            可序列化的字典,用于存储到 LitigationSession.metadata
        """
        # 将 messages 转换为可序列化格式
        serialized_messages = []
        for msg in self.messages:
            if isinstance(msg, BaseMessage):
                serialized_messages.append(
                    {
                        "type": msg.type,
                        "content": msg.content,
                        "additional_kwargs": getattr(msg, "additional_kwargs", {}),
                    }
                )
            elif isinstance(msg, dict):
                serialized_messages.append(msg)

        return {
            "agent_state": {
                "session_id": self.session_id,
                "case_id": self.case_id,
                "document_type": self.document_type,
                "litigation_goal": self.litigation_goal,
                "evidence_item_ids": self.evidence_item_ids,
                "our_evidence_item_ids": self.our_evidence_item_ids,
                "opponent_evidence_item_ids": self.opponent_evidence_item_ids,
                "draft": self.draft,
                "draft_version": self.draft_version,
                "collected_context": self.collected_context,
                "messages": serialized_messages,
            },
            "conversation_summary": self.conversation_summary,
            "tool_call_history": self.tool_call_history,
        }

    @classmethod
    def from_metadata(cls, metadata: dict[str, Any]) -> "LitigationAgentState":
        """
        从 metadata 字典恢复状态

        从数据库存储的 metadata 恢复 Agent 状态.

        Args:
            metadata: LitigationSession.metadata 字典

        Returns:
            恢复的 LitigationAgentState 实例
        """
        if not metadata:
            return cls()

        agent_state = metadata.get("agent_state", {})
        return cls(
            session_id=agent_state.get("session_id", ""),
            case_id=agent_state.get("case_id", 0),
            document_type=agent_state.get("document_type"),
            litigation_goal=agent_state.get("litigation_goal"),
            evidence_item_ids=agent_state.get("evidence_item_ids", []),
            our_evidence_item_ids=agent_state.get("our_evidence_item_ids", []),
            opponent_evidence_item_ids=agent_state.get("opponent_evidence_item_ids", []),
            draft=agent_state.get("draft"),
            draft_version=agent_state.get("draft_version", 0),
            collected_context=agent_state.get("collected_context", {}),
            messages=agent_state.get("messages", []),
            conversation_summary=metadata.get("conversation_summary"),
            tool_call_history=metadata.get("tool_call_history", []),
        )

    def update_evidence_selection(
        self,
        evidence_item_ids: list[int],
        our_evidence_item_ids: list[int],
        opponent_evidence_item_ids: list[int],
    ) -> None:
        """
        更新证据选择

        Args:
            evidence_item_ids: 所有选中的证据项 ID
            our_evidence_item_ids: 我方证据项 ID
            opponent_evidence_item_ids: 对方证据项 ID
        """
        self.evidence_item_ids = evidence_item_ids
        self.our_evidence_item_ids = our_evidence_item_ids
        self.opponent_evidence_item_ids = opponent_evidence_item_ids

    def update_draft(self, draft: dict[str, Any]) -> None:
        """
        更新草稿内容并递增版本号

        Args:
            draft: 新的草稿内容
        """
        self.draft = draft
        self.draft_version += 1

    def add_tool_call(
        self,
        tool_name: str,
        arguments: dict[str, Any],
        result: Any,
    ) -> None:
        """
        记录工具调用

        Args:
            tool_name: 工具名称
            arguments: 调用参数
            result: 调用结果
        """
        from datetime import datetime

        self.tool_call_history.append(
            {
                "tool_name": tool_name,
                "arguments": arguments,
                "result": result,
                "timestamp": datetime.now().isoformat(),
            }
        )

    def set_conversation_summary(self, summary: str) -> None:
        """
        设置对话摘要

        Args:
            summary: 对话摘要内容
        """
        self.conversation_summary = summary

    def get_messages_as_dicts(self) -> list[dict[str, Any]]:
        """
        获取消息列表的 dict 格式

        将所有消息(包括 BaseMessage 对象)转换为 dict 格式.

        Returns:
            消息列表的 dict 格式
        """
        result = []
        for msg in self.messages:
            if isinstance(msg, BaseMessage):
                result.append(
                    {
                        "role": msg.type,
                        "content": msg.content,
                    }
                )
            elif isinstance(msg, dict):
                result.append(msg)
        return result
