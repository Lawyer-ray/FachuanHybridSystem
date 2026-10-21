"""Agent 对话编排 —— 把一次对话跑在 pi 上。

## 与 apps.workbench 的关系

完全独立：不使用 workbench 的模型、服务或 ContextVar。
workbench 保持原样，作为既有功能的回退路径。

## 并发模型

- 每个请求从进程池借一个 pi 进程，用完归还
- 事件经 ``event_bus`` 按会话分发（审批回调也是这条通道）
- 会话历史存 Django，pi 以 ``--no-session`` 运行，不持有状态

## 事件契约

    activity → delta* → tool_call*/tool_result* → approval_request? → error? → done
"""

from __future__ import annotations

import asyncio
import logging
import os
from collections.abc import AsyncIterator
from typing import Any

from django.utils import timezone

from ..models import AgentMessage, AgentSession
from ..pi.bridge import stream_events
from ..pi.pool import PiProcessPool, PoolConfig
from ..pi.rpc_client import PiError, PiNotAvailableError
from ..pi.shared_mcp import resolve_endpoint, shared_enabled
from .event_bus import get_bus

logger = logging.getLogger(__name__)

DEFAULT_POOL_SIZE = 4
MAX_POOL_SIZE = 32

_pool: PiProcessPool | None = None
_pool_lock = asyncio.Lock()


def _resolve_pool_size() -> int:
    try:
        raw = os.environ.get("FACHUAN_AGENT_POOL_SIZE", "")
        size = int(raw) if raw.strip() else DEFAULT_POOL_SIZE
    except ValueError:
        size = DEFAULT_POOL_SIZE
    return max(1, min(size, MAX_POOL_SIZE))


async def get_pool() -> PiProcessPool:
    """进程级单例池（首次使用时按配置创建）。"""
    global _pool
    async with _pool_lock:
        if _pool is None:
            _pool = PiProcessPool(
                PoolConfig(
                    size=_resolve_pool_size(),
                    model=os.environ.get("FACHUAN_PI_MODEL") or None,
                    provider=os.environ.get("FACHUAN_PI_PROVIDER") or None,
                    extension_path=os.environ.get("FACHUAN_PI_APPROVAL_EXTENSION") or None,
                    mcp_endpoint=resolve_endpoint() if shared_enabled() else None,
                )
            )
            logger.info("Agent pi 进程池已创建 size=%s", _pool.size)
        return _pool


async def close_pool() -> None:
    """销毁池（进程退出 / 测试清理时调用）。"""
    global _pool
    async with _pool_lock:
        if _pool is not None:
            await _pool.close()
            _pool = None


def _session_env(session: AgentSession | None, user_id: int | None) -> dict[str, str]:
    """注入给 pi extension 的环境变量（审批回调需要）。"""
    env: dict[str, str] = {}
    if session is not None:
        env["FACHUAN_SESSION_ID"] = str(session.session_id)
    if user_id is not None:
        env["FACHUAN_USER_ID"] = str(user_id)
    approval_url = os.environ.get("FACHUAN_APPROVAL_URL", "").strip()
    if approval_url:
        env["FACHUAN_APPROVAL_URL"] = approval_url
    token = os.environ.get("FACHUAN_INTERNAL_TOKEN", "").strip()
    if token:
        env["FACHUAN_INTERNAL_TOKEN"] = token
    return env


async def stream_chat(
    *,
    session: AgentSession,
    user_message: str,
    user_id: int | None = None,
) -> AsyncIterator[dict[str, Any]]:
    """跑一轮对话，产出 SSE 事件。"""
    await AgentMessage.objects.acreate(
        session=session,
        role=AgentMessage.Role.USER,
        content=user_message,
    )
    AgentSession.objects.filter(pk=session.pk).update(updated_at=timezone.now())

    bus = get_bus()
    external_queue = await bus.register(str(session.session_id))
    internal_queue: asyncio.Queue[dict[str, Any] | None] = asyncio.Queue()

    follow_ok = True
    try:
        yield {"type": "meta", "session_id": str(session.session_id), "agent": "pi"}
        yield {"type": "activity", "status": "thinking", "agent": "pi"}

        pool = await get_pool()
        async with pool.acquire() as pi_session:
            await pi_session.prompt(user_message)

            pump = asyncio.create_task(_pump(pi_session, internal_queue))
            try:
                while True:
                    event = await _next_event(internal_queue, external_queue)
                    if event is None:
                        break
                    yield event
                    if event.get("type") == "done":
                        break
            finally:
                pump.cancel()
                try:
                    await pump
                except asyncio.CancelledError:
                    pass

    except PiNotAvailableError as exc:
        follow_ok = False
        logger.error("pi 不可用: %s", exc)
        yield {"type": "error", "message": f"pi runtime 不可用：{exc}"}
    except PiError as exc:
        follow_ok = False
        logger.error("pi 运行失败: %s", exc)
        yield {"type": "error", "message": f"pi 运行失败：{exc}"}
    except Exception:
        follow_ok = False
        logger.exception("Agent runtime 未预期错误")
        yield {"type": "error", "message": "Agent 运行失败，请稍后重试"}
    finally:
        await bus.unregister(str(session.session_id), external_queue)
        if follow_ok:
            yield {"type": "done", "session_id": str(session.session_id)}


async def _next_event(
    internal: asyncio.Queue[dict[str, Any] | None],
    external: asyncio.Queue[dict[str, Any]],
) -> dict[str, Any] | None:
    """谁先来取谁：pi 事件流 或 外部总线（审批请求）。"""
    get_internal = asyncio.ensure_future(internal.get())
    get_external = asyncio.ensure_future(external.get())
    try:
        done, pending = await asyncio.wait(
            {get_internal, get_external},
            return_when=asyncio.FIRST_COMPLETED,
        )
        for task in pending:
            task.cancel()
        if get_external in done:
            return get_external.result()
        return get_internal.result()
    finally:
        for task in (get_internal, get_external):
            if not task.done():
                task.cancel()


async def _pump(session: Any, queue: asyncio.Queue[dict[str, Any] | None]) -> None:
    """把 pi 事件翻成前端事件推进队列，结束时补 None。"""
    try:
        async for event in stream_events(session):
            await queue.put(event)
    except asyncio.CancelledError:
        raise
    except Exception:
        logger.exception("pi 事件泵异常")
    finally:
        await queue.put(None)
