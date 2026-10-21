"""会话服务 —— 会话 CRUD 与归属过滤。

四层架构约束：ORM 查询只出现在 Service 层，API 层做参数提取与调用。
所有查询带归属过滤（``user_id``），防横向越权。
"""

from __future__ import annotations

from typing import Any

from django.db.models import QuerySet

from ..models import AgentSession


def _scoped(user_id: int | None) -> QuerySet[AgentSession]:
    """按用户过滤的会话查询集（查询集构造是惰性的，不会触发同步 DB 访问）。"""
    queryset: QuerySet[AgentSession] = AgentSession.objects.all()
    if user_id is not None:
        queryset = queryset.filter(user_id=user_id)
    return queryset


def _bounded(limit: int, cap: int = 200) -> int:
    return max(1, min(limit, cap))


async def create_session(*, title: str, llm_model: str, user_id: int | None) -> AgentSession:
    """新建会话。"""
    return await AgentSession.objects.acreate(title=title, llm_model=llm_model, user_id=user_id)


async def list_sessions(*, user_id: int | None, limit: int) -> list[AgentSession]:
    """列出该用户的会话（最近的在前）。"""
    queryset = _scoped(user_id)[: _bounded(limit)]
    return [session async for session in queryset]


async def get_session(*, session_id: str, user_id: int | None) -> AgentSession | None:
    """按 session_id 取会话（带归属过滤）。"""
    return await _scoped(user_id).filter(session_id=session_id).afirst()


async def delete_session(*, session_id: str, user_id: int | None) -> int:
    """删除会话（级联删除消息与审批），返回删除数。"""
    deleted, _ = await _scoped(user_id).filter(session_id=session_id).adelete()
    return deleted
