"""pi 进程池单例与配置解析（原 chat_service.py 的池管理部分）。"""

from __future__ import annotations

import asyncio
import logging
import os

from asgiref.sync import sync_to_async

from ...pi.pool import PiProcessPool, PoolConfig
from ...pi.shared_mcp import resolve_endpoint, shared_enabled

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
    async with _pool_lock:
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
    async with _pool_lock:
        if _pool is not None:
            await _pool.close()
            _pool = None
