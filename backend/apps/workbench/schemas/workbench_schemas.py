"""工作台 Schema 定义"""

from __future__ import annotations

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, Field

from apps.core.api.schemas import SchemaMixin

class SessionCreateIn(BaseModel):
    title: str = Field("", max_length=255, description="会话标题")
    llm_model: str = Field("", description="使用的 LLM 模型 ID")

class SessionUpdateIn(BaseModel):
    title: str | None = Field(None, max_length=255, description="会话标题")
    llm_model: str | None = Field(None, description="使用的 LLM 模型 ID")
    status: str | None = Field(None, description="会话状态")

class SessionOut(SchemaMixin, BaseModel):
    id: int
    session_id: UUID
    title: str
    llm_model: str
    status: str
    created_at: datetime
    updated_at: datetime
    last_message_preview: str = ""

    model_config = {"from_attributes": True}

    @staticmethod
    def resolve_created_at(obj: object) -> datetime | None:
        return SchemaMixin._resolve_datetime(getattr(obj, "created_at", None))

    @staticmethod
    def resolve_updated_at(obj: object) -> datetime | None:
        return SchemaMixin._resolve_datetime(getattr(obj, "updated_at", None))

class MessageIn(BaseModel):
    content: str = Field(..., min_length=1, description="用户消息内容")
    llm_model: str = Field("", description="使用的 LLM 模型 ID（覆盖会话默认）")
    agent_type: str = Field("", description="Agent 类型: triage/case/contract/research")

class MessageOut(SchemaMixin, BaseModel):
    id: int
    role: str
    content: str
    llm_model: str
    tool_call_id: str
    tool_name: str
    tool_input: dict
    tool_output: dict
    metadata: dict
    created_at: datetime

    model_config = {"from_attributes": True}

    @staticmethod
    def resolve_created_at(obj: object) -> datetime | None:
        return SchemaMixin._resolve_datetime(getattr(obj, "created_at", None))
