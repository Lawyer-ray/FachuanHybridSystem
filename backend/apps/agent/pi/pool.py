"""pi 进程闸门 —— 限制并发、按请求造进程。

## 为什么每请求一个进程（不复用）

两个硬约束决定了复用不可行：

1. **审批路由靠环境变量**：审批 extension 在 pi 进程启动时读取
   ``FACHUAN_SESSION_ID`` / ``FACHUAN_USER_ID``，同一进程无法服务第二个会话
   （否则审批弹窗会推给错误的前端）。
2. **pi 的会话是进程内状态**：复用进程会把上一个用户的对话残留给下一个用户。

MCP 已经共享为一份常驻（见 ``shared_mcp.py``），进程本身的造价可接受；
「池」的作用退化为**限制并发数 + 统一进程构造**（配置渲染、临时目录、env 清洗）。

## 生命周期

每次 ``acquire()``：建临时目录 → 渲染 pi 配置（models.json 从数据库读）→
启动进程 → 交给调用方 → 退出时关闭进程并**删除临时目录**（目录里的
models.json 含真实 API key，绝不能在磁盘上累积）。
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
from .shared_mcp import McpEndpoint, write_pi_config

logger = logging.getLogger(__name__)


@dataclass(slots=True)
class PoolConfig:
    """池的容量与进程参数。"""

    size: int = 4
    model: str | None = None
    provider: str | None = None
    extension_path: str | None = None
    extra_env: dict[str, str] = field(default_factory=dict)
    mcp_endpoint: McpEndpoint | None = None


class PiProcessPool:
    """并发受限的 pi 进程工厂（进程不回收，用完即毁）。"""

    def __init__(self, config: PoolConfig | None = None) -> None:
        self._config = config or PoolConfig()
        self._semaphore = asyncio.Semaphore(max(1, self._config.size))
        self._closed = False

    @property
    def size(self) -> int:
        return max(1, self._config.size)

    @contextlib.asynccontextmanager
    async def acquire(
        self,
        session_env: dict[str, str] | None = None,
        model: str | None = None,
    ) -> AsyncIterator[PiRpcSession]:
        """构造一个 pi 会话，退出时销毁进程并清理临时目录。

        Args:
            session_env: 会话级环境变量（审批回调需要 session_id / user_id）。
            model: 本请求使用的模型；缺省用池配置里的模型。按请求传入使
                Admin 修改 LLMProvider 默认模型后立即生效（``--model`` 与
                models.json 同源，不会失配）。
        """
        if self._closed:
            raise RuntimeError("进程池已关闭")
        effective_model = model or self._config.model
        cwd = make_temp_workdir()
        session: PiRpcSession | None = None
        async with self._semaphore:
            try:
                # write_pi_config 会读数据库（LLMProvider），放线程里跑，
                # 否则 async 上下文抛 SynchronousOnlyOperation。
                from asgiref.sync import sync_to_async

                await sync_to_async(write_pi_config, thread_sensitive=True)(
                    cwd, self._config.mcp_endpoint, model_hint=effective_model or ""
                )
                # 思考等级由 write_pi_config 一并写入隔离目录的 settings.json
                # （pi 官方开关是 modelThinkingLevels，不是 CLI 参数也不是
                # models.json 的 reasoning 字段）。
                env = {**(self._config.extra_env or {}), "PI_CODING_AGENT_DIR": cwd}
                env.update(session_env or {})
                session = PiRpcSession(
                    cwd=cwd,
                    model=effective_model,
                    provider=self._config.provider,
                    extension_path=self._config.extension_path,
                    extra_env=env,
                )
                await session.start()
                yield session
            finally:
                # 目录里有 models.json（真实 API key），用完必须删。
                if session is not None:
                    try:
                        await session.close()
                    except Exception:
                        logger.warning("pi 进程关闭异常（忽略）", exc_info=True)
                shutil.rmtree(cwd, ignore_errors=True)

    async def close(self) -> None:
        """停用闸门（在途请求各自收尾，本类不再持有长期资源）。"""
        self._closed = True

    async def __aenter__(self) -> PiProcessPool:
        return self

    async def __aexit__(self, *exc_info: Any) -> None:
        await self.close()
