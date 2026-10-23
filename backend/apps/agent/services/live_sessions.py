"""运行中会话注册表 —— 让「插话」能找到正在跑的那个 pi 进程。

## 为什么需要它

pi 每请求一个新进程，`PiRpcSession` 的生命周期就包在 `stream_chat` 的
`async with pool.acquire(...)` 里。用户想在 agent 写到一半时插一句
（steer / follow_up），HTTP 请求必须能拿到**同一个**进程句柄——否则
要么找不到（连接已断开），要么起个新进程说给空气听。

这里用一张 `session_id -> PiRpcSession` 的表把二者接上：

    stream_chat 进入 async with  → register(session_id, pi_session)
    POST /sessions/{id}/steer    → get(session_id) → pi_session.steer(...)
    stream_chat 退出             → unregister(session_id, pi_session)

## 为什么是进程内表而不是 Redis

`PiRpcSession` 持有真实子进程的 stdin/stdout 管道，**无法序列化跨进程传递**。
多 worker 部署下，插话请求必须落到「跑着这个会话的 worker」才能生效。
这一点与审批相反：审批走 Redis 是因为「用户 SSE 在 A、审批回调在 B」，
而 steer 天然要求同 worker。跨 worker 时如实返回「会话不在本实例运行」，
由前端提示重试，绝不假装成功。

## 同会话并发

同一会话同时只允许一个运行中的 pi 进程（第二条消息会让模型看到两份
互相冲突的上下文）。`register` 遇到已存在的会话时抛 `SessionBusyError`。
"""

from __future__ import annotations

import asyncio
import logging
from typing import Any

logger = logging.getLogger(__name__)


class SessionBusyError(RuntimeError):
    """同一会话已有运行中的 pi 进程。"""


class LiveSessionRegistry:
    """进程内「运行中会话」表（session_id → PiRpcSession）。"""

    def __init__(self) -> None:
        self._sessions: dict[str, Any] = {}
        self._lock = asyncio.Lock()

    async def register(self, session_id: str, pi_session: Any) -> None:
        """登记一个正在运行的 pi 会话。

        Raises:
            SessionBusyError: 该会话已有运行中的进程。
        """
        async with self._lock:
            existing = self._sessions.get(session_id)
            if existing is not None and existing is not pi_session:
                raise SessionBusyError(f"会话 {session_id} 已有运行中的对话")
            self._sessions[session_id] = pi_session

    async def unregister(self, session_id: str, pi_session: Any) -> None:
        """注销；只在表里存的仍是同一个进程时才删（防止误删后来者）。"""
        async with self._lock:
            if self._sessions.get(session_id) is pi_session:
                self._sessions.pop(session_id, None)

    async def get(self, session_id: str) -> Any | None:
        """取运行中的 pi 会话；没有则 ``None``（由调用方转成可读错误）。"""
        async with self._lock:
            return self._sessions.get(session_id)

    async def is_live(self, session_id: str) -> bool:
        return await self.get(session_id) is not None

    async def clear(self) -> None:
        """清空（测试收尾 / 进程关闭时用）。"""
        async with self._lock:
            self._sessions.clear()


_registry = LiveSessionRegistry()


def get_live_registry() -> LiveSessionRegistry:
    """进程级单例。"""
    return _registry


# ── P2-3 跨 Worker Steer 路由 ──────────────────────────────────────────────

LIVE_ROUTE_PREFIX = "agent:live:route:"
LIVE_ROUTE_TTL = 120


def _route_client() -> Any:
    """原生 Redis 客户端（与 event_bus 同源）。"""
    try:
        from django.core.cache import cache

        inner = getattr(cache, "_cache", None)
        return getattr(inner, "_cache", None) if inner else None
    except Exception:
        return None


def register_live_route(session_id: str, worker_id: str) -> None:
    """P2-3：注册本 worker 正在运行某会话（Redis 路由表）。"""
    client = _route_client()
    if client:
        try:
            client.set(f"{LIVE_ROUTE_PREFIX}{session_id}", worker_id, ex=LIVE_ROUTE_TTL)
        except Exception:
            pass


def unregister_live_route(session_id: str) -> None:
    """P2-3：会话结束，移除路由。"""
    client = _route_client()
    if client:
        try:
            client.delete(f"{LIVE_ROUTE_PREFIX}{session_id}")
        except Exception:
            pass


def get_live_worker(session_id: str) -> str | None:
    """P2-3：查会话在哪个 worker 上运行（None=本 worker 或无人运行）。"""
    client = _route_client()
    if not client:
        return None
    try:
        raw = client.get(f"{LIVE_ROUTE_PREFIX}{session_id}")
        return raw.decode() if isinstance(raw, bytes) else raw
    except Exception:
        return None
