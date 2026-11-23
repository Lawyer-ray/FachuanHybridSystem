"""pi 进程池单例与配置解析（原 chat_service.py 的池管理部分）。"""

from __future__ import annotations

import asyncio
import logging
import os
import weakref

from asgiref.sync import sync_to_async

from ...pi.pool import PiProcessPool, PoolConfig
from ...pi.shared_mcp import resolve_endpoint, shared_enabled

logger = logging.getLogger(__name__)

from .config import DEFAULT_POOL_SIZE, MAX_POOL_SIZE, resolve_pool_size

_pool: PiProcessPool | None = None

# 锁必须**按 event loop 懒建**（F5，2026-11-23 二轮审计）：
# 模块级 `asyncio.Lock()` 在第一次 await 时绑定当时那个 loop，而
# `subtask_runner` 用 `asyncio.run(...)` 每次新建 loop —— 第二次调用就会拿到
# 绑定在旧 loop 上的锁，抛 "attached to a different loop"（或被判成未加锁）。
_pool_locks: weakref.WeakKeyDictionary = weakref.WeakKeyDictionary()


def _pool_lock_for_current_loop() -> asyncio.Lock:
    loop = asyncio.get_running_loop()
    lock = _pool_locks.get(loop)
    if lock is None:
        lock = asyncio.Lock()
        _pool_locks[loop] = lock
    return lock


class _LoopScopedLock:
    """兼容旧名 ``_pool_lock`` 的「按 loop 取锁」代理（真正的锁见 ``_pool_lock_for_current_loop``）。

    `chat/__init__.py` 曾把 `_pool_lock` 写进 `__all__`（F7 待收敛），外部/测试有引用；
    直接删会 ImportError。用这个代理即可保持名字可用，同时避免模块级锁绑定到第一个 loop（F5）。
    """

    def __init__(self) -> None:
        self._held: asyncio.Lock | None = None

    async def __aenter__(self) -> _LoopScopedLock:
        lock = _pool_lock_for_current_loop()
        await lock.acquire()
        self._held = lock
        return self

    async def __aexit__(self, *_exc: object) -> bool:
        if self._held is not None:
            self._held.release()
            self._held = None
        return False


_pool_lock = _LoopScopedLock()


def _resolve_pool_size() -> int:
    """保留旧入口名，实际逻辑在 `chat/config.resolve_pool_size`（单源）。"""
    return resolve_pool_size()


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
        from ...pi.model_config import _load_provider, _provider_models

        provider = _load_provider()
        if provider is None:
            return None
        models = _provider_models(provider)
        return models[0] if models else None

    return await sync_to_async(_read, thread_sensitive=True)()


def _resolve_queue_timeout() -> float:
    """排队上限（秒）：0 表示不限。默认 60 秒——再长不如直接告诉用户忙。"""
    try:
        raw = os.environ.get("FACHUAN_AGENT_QUEUE_TIMEOUT", "")
        return float(raw) if raw.strip() else 60.0
    except ValueError:
        return 60.0


async def get_pool() -> PiProcessPool:
    """进程级单例池（首次使用时按配置创建）。"""
    global _pool
    async with _pool_lock_for_current_loop():
        if _pool is None:
            model = await _resolve_model()
            endpoint = None
            if shared_enabled():
                endpoint = resolve_endpoint()
                # 共享 MCP 是单点：没起就拉起，否则每个 pi 会退回 stdio
                # 各起一份（实测 225MB/份），并发一上来就爆内存。
                from ...pi.shared_mcp import ensure_shared_server

                await sync_to_async(ensure_shared_server, thread_sensitive=False)(endpoint)
            _pool = PiProcessPool(
                PoolConfig(
                    size=_resolve_pool_size(),
                    model=model,
                    provider=os.environ.get("FACHUAN_PI_PROVIDER") or None,
                    extension_path=os.environ.get("FACHUAN_PI_APPROVAL_EXTENSION") or None,
                    mcp_endpoint=endpoint,
                    queue_timeout=_resolve_queue_timeout(),
                )
            )
            logger.info("Agent pi 进程池已创建 size=%s", _pool.size)
        return _pool


async def close_pool() -> None:
    """销毁池（进程退出 / 测试清理时调用）。"""
    global _pool
    async with _pool_lock_for_current_loop():
        if _pool is not None:
            await _pool.close()
            _pool = None
