"""诉讼文书生成 Agent 状态定义."""

from __future__ import annotations

from collections.abc import Sequence
from typing import Annotated, Any

from pydantic import BaseModel, Field


def _merge_messages(left: Sequence[dict[str, Any]], right: Sequence[dict[str, Any]]) -> list[dict[str, Any]]:
    """合并消息列表,用于状态更新。"""
    return [*left, *right]


class LitigationAgentState(BaseModel):
    """诉讼文书生成 Agent 状态。"""

    session_id: str = Field(default="", description="会话唯一标识")
    case_id: int = Field(default=0, description="关联的案件 ID")

    document_type: str | None = Field(
        default=None,
        description=(
            "文书类型: complaint(起诉状), defense(答辩状), counterclaim(反诉状), counterclaim_defense(反诉答辩状)"
        ),
    )
    litigation_goal: str | None = Field(default=None, description="诉讼目标描述")

    evidence_item_ids: list[int] = Field(default_factory=list, description="所有选中的证据项 ID")
    our_evidence_item_ids: list[int] = Field(default_factory=list, description="我方证据项 ID")
    opponent_evidence_item_ids: list[int] = Field(default_factory=list, description="对方证据项 ID")

    draft: dict[str, Any] | None = Field(default=None, description="当前生成的草稿内容")
    draft_version: int = Field(default=0, description="草稿版本号")

    messages: Annotated[list[dict[str, Any]], _merge_messages] = Field(
        default_factory=list,
        description="对话消息列表",
    )

    collected_context: dict[str, Any] = Field(default_factory=dict, description="已收集的上下文信息")
    conversation_summary: str | None = Field(default=None, description="对话历史摘要")
    tool_call_history: list[dict[str, Any]] = Field(default_factory=list, description="工具调用历史记录")

    def to_metadata(self) -> dict[str, Any]:
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
                "messages": self.messages,
            },
            "conversation_summary": self.conversation_summary,
            "tool_call_history": self.tool_call_history,
        }

    @classmethod
    def from_metadata(cls, metadata: dict[str, Any]) -> LitigationAgentState:
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
        self.evidence_item_ids = evidence_item_ids
        self.our_evidence_item_ids = our_evidence_item_ids
        self.opponent_evidence_item_ids = opponent_evidence_item_ids

    def update_draft(self, draft: dict[str, Any]) -> None:
        self.draft = draft
        self.draft_version += 1

    def add_tool_call(
        self,
        tool_name: str,
        arguments: dict[str, Any],
        result: Any,
    ) -> None:
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
        self.conversation_summary = summary

    def get_messages_as_dicts(self) -> list[dict[str, Any]]:
        return list(self.messages)
