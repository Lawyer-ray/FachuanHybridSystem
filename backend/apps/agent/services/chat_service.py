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


async def _resolve_model() -> str | None:
    """解析 agent 使用的模型：显式环境变量 > LLMProvider.default_model。

    不返回空串：pi 收到 ``--model ""`` 会报错，此时应让 pi 自己选默认模型。

    **必须异步调用**：``_load_provider`` 走同步 ORM，在 async 上下文里直接调
    会抛 ``SynchronousOnlyOperation``；若被 except 吞掉，model 退化为 None，
    pi 就去连它自己配置里那个不存在的 provider，表现为每次请求都
    ``Connection error`` 重试 3 次。这里用 ``sync_to_async`` 包一层。
    """
    explicit = os.environ.get("FACHUAN_PI_MODEL", "").strip()
    if explicit:
        return explicit

    def _read() -> str | None:
        from ..pi.model_config import _load_provider, _provider_models

        provider = _load_provider()
        if provider is None:
            return None
        models = _provider_models(provider)
        return models[0] if models else None

    from asgiref.sync import sync_to_async

    return await sync_to_async(_read, thread_sensitive=True)()


async def get_pool() -> PiProcessPool:
    """进程级单例池（首次使用时按配置创建）。"""
    global _pool
    async with _pool_lock:
        if _pool is None:
            model = await _resolve_model()
            endpoint = None
            if shared_enabled():
                endpoint = resolve_endpoint()
                # 共享 MCP 是单点：没起就拉起，否则每个 pi 会退回 stdio
                # 各起一份（实测 225MB/份），并发一上来就爆内存。
                from asgiref.sync import sync_to_async

                from ..pi.shared_mcp import ensure_shared_server

                await sync_to_async(ensure_shared_server, thread_sensitive=False)(endpoint)
            _pool = PiProcessPool(
                PoolConfig(
                    size=_resolve_pool_size(),
                    model=model,
                    provider=os.environ.get("FACHUAN_PI_PROVIDER") or None,
                    extension_path=os.environ.get("FACHUAN_PI_APPROVAL_EXTENSION") or None,
                    mcp_endpoint=endpoint,
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
    await AgentSession.objects.filter(pk=session.pk).aupdate(updated_at=timezone.now())

    bus = get_bus()
    external_queue = await bus.register(str(session.session_id))

    follow_ok = True
    try:
        yield {"type": "meta", "session_id": str(session.session_id), "agent": "pi"}
        yield {"type": "activity", "status": "thinking", "agent": "pi"}

        pool = await get_pool()
        async with pool.acquire() as pi_session:
            await pi_session.prompt(user_message)

            # 同时消费两个来源：pi 事件流 + 外部总线（审批请求）。
            # 不用「两个 get() task + asyncio.wait」—那个写法在 yield 让出控制权后
            # 容易丢掉已取出的事件（实测表现为只有 activity、无 delta）。
            # 改为：pi 事件流为主循环，审批事件用非阻塞轮询插队。
            stream = stream_events(pi_session)
            pending_next: asyncio.Task[dict[str, Any]] | None = None
            while True:
                while True:
                    try:
                        yield external_queue.get_nowait()
                    except asyncio.QueueEmpty:
                        break

                if pending_next is None:
                    pending_next = asyncio.ensure_future(stream.__anext__())
                await asyncio.wait({pending_next}, timeout=0.2)
                if pending_next.done():
                    task, pending_next = pending_next, None
                    try:
                        event = task.result()
                    except StopAsyncIteration:
                        break
                    yield event
                    if event.get("type") == "done":
                        break

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
        # 注意：生成器的 finally 里**不能 yield**。客户端断开时本协程会收到
        # GeneratorExit，此时再 yield 会抛 RuntimeError（"async generator ignored
        # GeneratorExit"），表现为 SSE 被截断、curl 返回 CURLE_PARTIAL_FILE(18)。
        await bus.unregister(str(session.session_id), external_queue)

    if follow_ok:
        yield {"type": "done", "session_id": str(session.session_id)}
