"""pi 进程池 —— 支撑高并发的执行层。

## 为什么是进程池

pi 的 session 是**进程内状态**。单进程里切 session 会串行，做不到真并发。

实测：4 个 pi 进程并行跑 prompt，总耗时 5.2s，各自独立 ``agent_settled``；
8 进程 + 共享 MCP 时总耗时 4.1s。确认进程级并发可行。

## 与共享 MCP 的配合

池里每个 pi 进程都通过 HTTP 连同一份共享 MCP（见 ``shared_mcp.py``），
因此池的大小只影响 pi 自身的开销，不再线性放大 MCP 的 225MB。

## 池的语义

- ``acquire()`` 取空闲会话；无空闲则新建（受 semaphore 限流）
- 用完 ``release()`` 归还；超过 ``max_idle`` 的归还时销毁
- 归还时检查进程存活，崩溃的进程不会回到池里
"""

from __future__ import annotations

import asyncio
import contextlib
import logging
import shutil
from collections.abc import AsyncIterator
from dataclasses import dataclass, field
from typing import Any

from .rpc_client import PiRpcSession, make_temp_workdir
from .shared_mcp import McpEndpoint, write_pi_mcp_config

logger = logging.getLogger(__name__)


@dataclass(slots=True)
class PoolConfig:
    """池的容量与进程参数。"""

    size: int = 4
    max_idle: int = 4
    model: str | None = None
    provider: str | None = None
    extension_path: str | None = None
    extra_env: dict[str, str] = field(default_factory=dict)
    mcp_endpoint: McpEndpoint | None = None


class PiProcessPool:
    """固定容量的 pi 子进程池。"""

    def __init__(self, config: PoolConfig | None = None) -> None:
        self._config = config or PoolConfig()
        self._semaphore = asyncio.Semaphore(max(1, self._config.size))
        self._idle: list[PiRpcSession] = []
        self._workdirs: list[str] = []
        self._closed = False
        self._lock = asyncio.Lock()

    @property
    def size(self) -> int:
        return max(1, self._config.size)

    async def _create(self) -> PiRpcSession:
        cwd = make_temp_workdir()
        self._workdirs.append(cwd)
        # 每个会话目录写一份 .pi/mcp.json，指向共享 MCP
        write_pi_mcp_config(cwd, self._config.mcp_endpoint)
        session = PiRpcSession(
            cwd=cwd,
            model=self._config.model,
            provider=self._config.provider,
            extension_path=self._config.extension_path,
            extra_env=self._config.extra_env,
        )
        await session.start()
        return session

    async def _take(self) -> PiRpcSession:
        async with self._lock:
            while self._idle:
                candidate = self._idle.pop()
                if candidate.alive:
                    return candidate
                # 已死进程：清理后继续找
                await candidate.close()
        return await self._create()

    async def _give_back(self, session: PiRpcSession) -> None:
        if not session.alive:
            await session.close()
            return
        async with self._lock:
            if not self._closed and len(self._idle) < max(1, self._config.max_idle):
                self._idle.append(session)
                return
        await session.close()

    @contextlib.asynccontextmanager
    async def acquire(self) -> AsyncIterator[PiRpcSession]:
        """借出一个会话，退出时自动归还。"""
        if self._closed:
            raise RuntimeError("进程池已关闭")
        async with self._semaphore:
            session = await self._take()
            try:
                yield session
            finally:
                await self._give_back(session)

    async def close(self) -> None:
        """销毁所有空闲会话与工作目录。"""
        self._closed = True
        async with self._lock:
            idle, self._idle = self._idle, []
        for session in idle:
            await session.close()
        for path in self._workdirs:
            with contextlib.suppress(Exception):
                shutil.rmtree(path, ignore_errors=True)
        self._workdirs.clear()

    async def __aenter__(self) -> PiProcessPool:
        return self

    async def __aexit__(self, *exc_info: Any) -> None:
        await self.close()
