"""会话服务 —— 会话 CRUD 与归属过滤。

四层架构约束：ORM 查询只出现在 Service 层，API 层做参数提取与调用。
所有查询带归属过滤（``user_id``），防横向越权。
"""

from __future__ import annotations

from django.db.models import QuerySet

from ..models import AgentMessage, AgentSession


def _scoped(user_id: int | None) -> QuerySet[AgentSession]:
    """按用户过滤的会话查询集（查询集构造是惰性的，不会触发同步 DB 访问）。

    ``user_id 为 None`` 表示「没有登录身份」，此时必须**什么也匹配不到**：
    早期实现是「None 就不加过滤」，等于未登录/无身份调用方能看到并删除
    **任意用户的会话**（单测 test_cross_user_delete_does_not_touch_pi_context
    就是踩到这个才写的）。无主会话只能由服务端内部代码直接访问模型，
    不走这里。
    """
    if user_id is None:
        return AgentSession.objects.none()
    return AgentSession.objects.filter(user_id=user_id)


def _bounded(limit: int, cap: int = 200) -> int:
    return max(1, min(limit, cap))


async def create_session(
    *,
    title: str,
    user_id: int | None,
    origin: str = "chat",
    case_id: int | None = None,
    contract_id: int | None = None,
) -> AgentSession:
    """新建会话（模型由服务端在对话时解析并回写，客户端不指定）。"""
    return await AgentSession.objects.acreate(
        title=title,
        user_id=user_id,
        origin=origin,
        case_id=case_id,
        contract_id=contract_id,
    )


async def list_sessions(
    *,
    user_id: int | None,
    limit: int,
    origin: str | None = None,
    case_id: int | None = None,
    contract_id: int | None = None,
) -> list[AgentSession]:
    """列出该用户的会话（最近的在前）。

    Args:
        origin: 只看某个入口（对话 / 案件内 / 任务式）。
        case_id / contract_id: 只看与某个案件 / 合同相关的会话。

    归属永远按 ``user_id`` 过滤：``case_id`` 只是**再缩小**范围，不能替代
    归属校验（否则传别人的 case_id 就能列出别人的会话）。
    """
    queryset = _scoped(user_id)
    if origin:
        queryset = queryset.filter(origin=origin)
    if case_id is not None:
        queryset = queryset.filter(case_id=case_id)
    if contract_id is not None:
        queryset = queryset.filter(contract_id=contract_id)
    return [session async for session in queryset[: _bounded(limit)]]


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
    """删除会话（级联删除消息与审批），返回删除数。

    同时清理该会话的 pi session 文件：那是模型的上下文载体，含工具调用参数与
    工具返回的业务数据。只删数据库会让用户误以为「会话已删干净」。
    """
    # 先确认归属再删文件：否则越权者能借删除接口清掉别人的 pi 上下文
    existing = await get_session(session_id=session_id, user_id=user_id)
    if existing is None:
        return 0
    deleted, _ = await _scoped(user_id).filter(session_id=session_id).adelete()
    if deleted:
        from asgiref.sync import sync_to_async

        from .session_cleanup import delete_pi_session

        await sync_to_async(delete_pi_session, thread_sensitive=True)(session_id)
    return deleted


async def rename_session(*, session_id: str, user_id: int | None, title: str) -> AgentSession | None:
    """重命名会话（title 已由 API 层校验非空）；不存在或不归属时返回 ``None``。"""
    session = await get_session(session_id=session_id, user_id=user_id)
    if session is None:
        return None
    session.title = title.strip()[:200]
    await session.asave(update_fields=["title", "updated_at"])
    return session
