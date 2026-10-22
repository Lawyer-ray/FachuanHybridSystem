"""会话服务 —— 会话 CRUD 与归属过滤。

四层架构约束：ORM 查询只出现在 Service 层，API 层做参数提取与调用。
所有查询带归属过滤（``user_id``），防横向越权。
"""

from __future__ import annotations

from django.db.models import QuerySet

from ..models import AgentMessage, AgentSession


def _scoped(user_id: int | None) -> QuerySet[AgentSession]:
    """按用户过滤的会话查询集（查询集构造是惰性的，不会触发同步 DB 访问）。"""
    queryset: QuerySet[AgentSession] = AgentSession.objects.all()
    if user_id is not None:
        queryset = queryset.filter(user_id=user_id)
    return queryset


def _bounded(limit: int, cap: int = 200) -> int:
    return max(1, min(limit, cap))


async def create_session(*, title: str, user_id: int | None) -> AgentSession:
    """新建会话（模型由服务端在对话时解析并回写，客户端不指定）。"""
    return await AgentSession.objects.acreate(title=title, user_id=user_id)


async def list_sessions(*, user_id: int | None, limit: int) -> list[AgentSession]:
    """列出该用户的会话（最近的在前）。"""
    queryset = _scoped(user_id)[: _bounded(limit)]
    return [session async for session in queryset]


async def get_session(*, session_id: str, user_id: int | None) -> AgentSession | None:
    """按 session_id 取会话（带归属过滤）。"""
    return await _scoped(user_id).filter(session_id=session_id).afirst()


async def list_messages(*, session_id: str, user_id: int | None, limit: int = 200) -> list[AgentMessage] | None:
    """列出会话消息（旧→新），供前端重开会话时回放转录。

    Returns:
        消息列表；会话不存在或不归属当前用户时返回 ``None``（由 API 层转 404）。
    """
    session = await get_session(session_id=session_id, user_id=user_id)
    if session is None:
        return None
    rows = AgentMessage.objects.filter(session=session).order_by("-created_at", "-id")[: _bounded(limit, 1000)]
    messages = [m async for m in rows]
    messages.reverse()
    return messages


async def delete_session(*, session_id: str, user_id: int | None) -> int:
    """删除会话（级联删除消息与审批），返回删除数。"""
    deleted, _ = await _scoped(user_id).filter(session_id=session_id).adelete()
    return deleted


async def rename_session(*, session_id: str, user_id: int | None, title: str) -> AgentSession | None:
    """重命名会话（title 已由 API 层校验非空）；不存在或不归属时返回 ``None``。"""
    session = await get_session(session_id=session_id, user_id=user_id)
    if session is None:
        return None
    session.title = title.strip()[:200]
    await session.asave(update_fields=["title", "updated_at"])
    return session
