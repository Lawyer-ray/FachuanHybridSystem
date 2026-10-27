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

每次 ``acquire()``：解析稳定目录（``session_store.layout``）→ 渲染 pi 配置
（models.json 从数据库读）→ 以 ``--session-dir/--session-id`` 启动进程 →
交给调用方 → 退出时关闭进程。

目录**不再随请求删除**：``--session-id`` 按 cwd 隔离会话，稳定的 cwd 是
多轮记忆的前提；含 API key 的 models.json 由 ``write_models_json`` 以 0600
原子创建、目录 0700，安全性不再依赖「用完就删」。
"""

from __future__ import annotations

import asyncio
import contextlib
import logging
from collections.abc import AsyncIterator, Callable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from .rpc_client import PiRpcSession
from .session_store import layout
from .shared_mcp import McpEndpoint, write_pi_config

logger = logging.getLogger(__name__)


class PoolQueueTimeoutError(RuntimeError):
    """排队超时：池容量被占满且等待过久。

    不无限排队的原因：用户盯着转圈 5 分钟比直接告诉他「系统忙」更糟，
    也会把 HTTP 连接和 SSE 都拖住，最终两头超时且查不到原因。
    """


@dataclass(slots=True)
class PoolConfig:
    """池的容量与进程参数。"""

    size: int = 4
    model: str | None = None
    provider: str | None = None
    extension_path: str | None = None
    extra_env: dict[str, str] = field(default_factory=dict)
    mcp_endpoint: McpEndpoint | None = None
    #: 排队最长等待（秒）。0 表示不限（仅测试 / 内部批量场景使用）。
    queue_timeout: float = 60.0
    #: 排队期间的回调：收到「前面还有几位」。由 chat_service 转成 queued 事件。
    on_queued: Callable[[int], None] | None = None


class PiProcessPool:
    """并发受限的 pi 进程工厂（进程不回收，用完即毁）。"""

    def __init__(self, config: PoolConfig | None = None) -> None:
        self._config = config or PoolConfig()
        self._semaphore = asyncio.Semaphore(max(1, self._config.size))
        self._closed = False
        #: 正在排队的请求数（用于告诉前端「前方 N 人」）
        self._waiting = 0
        self._waiting_lock = asyncio.Lock()

    @property
    def size(self) -> int:
        return max(1, self._config.size)

    @property
    def waiting(self) -> int:
        """当前排队中的请求数（不含正在跑的）。"""
        return self._waiting

    @property
    def saturated(self) -> bool:
        """执行位是否已全部占满（新请求会排队）。"""
        return self._semaphore.locked()

    @contextlib.asynccontextmanager
    async def _slot(self) -> AsyncIterator[None]:
        """取一个执行位；满员时带排队超时，不无限挂死。

        P2-2 全机并发闸门：Redis 可用时走分布式计数（跨 worker 共享
        容量），不可用退化为进程内 asyncio.Semaphore（现行行为）。

        Raises:
            PoolQueueTimeoutError: 排队超过 ``queue_timeout``。
        """
        # P2-2：Redis 分布式信号量路径
        redis_gate = _try_redis_slot(self.size)
        if redis_gate is not None:
            timeout = self._config.queue_timeout
            deadline = asyncio.get_event_loop().time() + (timeout if timeout > 0 else 3600)
            while True:
                if redis_gate.try_acquire():
                    break
                if timeout > 0 and asyncio.get_event_loop().time() >= deadline:
                    raise PoolQueueTimeoutError(f"agent 执行位已满，排队超过 {timeout:.0f} 秒（全机容量 {self.size}）")
                await asyncio.sleep(0.2)
            try:
                yield
            finally:
                redis_gate.release()
            return

        # 无 Redis 路径（现行行为）
        timeout = self._config.queue_timeout
        if timeout <= 0:
            async with self._semaphore:
                yield
            return
        try:
            await asyncio.wait_for(self._semaphore.acquire(), timeout=timeout)
        except TimeoutError as exc:
            raise PoolQueueTimeoutError(f"agent 执行位已满，排队超过 {timeout:.0f} 秒（容量 {self.size}）") from exc
        try:
            yield
        finally:
            self._semaphore.release()

    async def _announce_queue(self) -> None:
        """登记排队并回调前端可见的排队位置。"""
        callback = self._config.on_queued
        async with self._waiting_lock:
            self._waiting += 1
            position = self._waiting
        if callback is None:
            return
        try:
            callback(position)
        except Exception:
            logger.debug("排队回调失败（忽略）", exc_info=True)

    async def _leave_queue(self) -> None:
        async with self._waiting_lock:
            self._waiting = max(0, self._waiting - 1)

    @contextlib.asynccontextmanager
    async def acquire(
        self,
        session_env: dict[str, str] | None = None,
        model: str | None = None,
        session_id: str | None = None,
        tool_selection: str | None = None,
        skill_paths: list[str] | None = None,
    ) -> AsyncIterator[PiRpcSession]:
        """构造一个 pi 会话，退出时销毁进程并清理临时目录。

        Args:
            session_env: 会话级环境变量（审批回调需要 session_id / user_id）。
            model: 本请求使用的模型；缺省用池配置里的模型。按请求传入使
                Admin 修改 LLMProvider 默认模型后立即生效（``--model`` 与
                models.json 同源，不会失配）。
            skill_paths: 本会话注入的 Agent Skills 目录（``--skill``）。
                ``None`` 表示不注入任何技能（配合 rpc_client 恒定的
                ``--no-skills``，宿主机用户级技能不会混进来）。

        三条纪律：

        - **排队可见**：池满时先登记排队并回调排队位置（前端显示「前方 N 人」），
          再等执行位；不无限挂死，超过 ``queue_timeout`` 抛 PoolQueueTimeoutError。
        - **取消时真中止**：用户点停止 / 客户端断开时先 clear_queue + abort 再关，
          否则模型会在服务端跑完继续烧 token。
        - **目录稳定不删**：cwd 与配置目录必须稳定（``--session-id`` 按 cwd 隔离
          会话，换目录会让同一会话丢失记忆）。目录权限 0700，models.json 由
          ``write_models_json`` 以 0600 原子创建，不再依赖「用完就删」来兜底。
        """
        if self._closed:
            raise RuntimeError("进程池已关闭")
        effective_model = model or self._config.model
        # 稳定布局：work（cwd）/ config（PI_CODING_AGENT_DIR）/ sessions
        cwd, config_dir, sessions_root = layout()
        session_dir = str(Path(sessions_root) / session_id) if session_id else None
        session: PiRpcSession | None = None
        aborted = False
        queued = self._semaphore.locked()
        if queued:
            await self._announce_queue()
        try:
            async with self._slot():
                try:
                    # 自愈共享 MCP：原实现只在进程池首次创建时拉一次，
                    # 之后 MCP 崩了就「所有会话无工具直到 Django 重启」。
                    # 每次拿到执行位都 ensure 一把（幂等，端口在就秒回）；
                    # 新拉实例等到 ready 再放行 pi 连接（冷启动 ~6s）。
                    # ensure 失败只降级（无工具但能对话），下次 acquire 重试。
                    if self._config.mcp_endpoint is not None:
                        from asgiref.sync import sync_to_async

                        from .shared_mcp import ensure_shared_server

                        with contextlib.suppress(OSError):
                            await sync_to_async(ensure_shared_server, thread_sensitive=False)(
                                self._config.mcp_endpoint, wait_ready=True
                            )
                    # write_pi_config 会读数据库（LLMProvider），放线程里跑，
                    # 否则 async 上下文抛 SynchronousOnlyOperation。
                    from asgiref.sync import sync_to_async

                    await sync_to_async(write_pi_config, thread_sensitive=True)(
                        config_dir, self._config.mcp_endpoint, model_hint=effective_model or ""
                    )
                    # 思考等级由 write_pi_config 一并写入隔离目录的 settings.json
                    # （pi 官方开关是 modelThinkingLevels，不是 CLI 参数也不是
                    # models.json 的 reasoning 字段）。
                    env = {**(self._config.extra_env or {}), "PI_CODING_AGENT_DIR": str(config_dir)}
                    env.update(session_env or {})
                    session = PiRpcSession(
                        cwd=str(cwd),
                        model=effective_model,
                        provider=self._config.provider,
                        extension_path=self._config.extension_path,
                        extra_env=env,
                        session_dir=session_dir,
                        session_id=session_id,
                        tool_selection=tool_selection,
                        skill_paths=skill_paths,
                    )
                    await session.start()
                    yield session
                except (GeneratorExit, asyncio.CancelledError):
                    # 取消路径：当前任务已处于取消中，await 会立即重新抛
                    # CancelledError，所以关闭动作必须屏蔽外层取消，
                    # 否则 abort 根本发不出去。
                    aborted = True
                    if session is not None:
                        with contextlib.suppress(Exception):
                            await asyncio.shield(session.close(abort_running=True))
                    raise
                finally:
                    if session is not None and not aborted:
                        try:
                            await session.close()
                        except Exception:
                            logger.warning("pi 进程关闭异常（忽略）", exc_info=True)
        finally:
            if queued:
                await self._leave_queue()

    async def close(self) -> None:
        """停用闸门（在途请求各自收尾，本类不再持有长期资源）。"""
        self._closed = True

    async def __aenter__(self) -> PiProcessPool:
        return self

    async def __aexit__(self, *exc_info: Any) -> None:
        await self.close()


# ── P2-2 全机并发闸门（Redis 计数信号量）────────────────────────────────────

_GLOBAL_SEM_KEY = "agent:pool:global_count"


def _redis_sync_client() -> Any:
    """原生 Redis 客户端（同步；与 event_bus 同源判定）。"""
    try:
        from django.core.cache import cache

        inner = getattr(cache, "_cache", None)
        return getattr(inner, "_cache", None) if inner else None
    except Exception:
        return None


class _RedisGate:
    """极简分布式计数闸门：INCR/DECR + TTL 兜底回收。

    不是可重入锁——只做跨 worker 共享容量计数。进程崩溃后计数由 TTL 归零。
    """

    def __init__(self, key: str, size: int) -> None:
        self._key = key
        self._size = size
        self._acquired = False

    def try_acquire(self) -> bool:
        client = _redis_sync_client()
        if client is None:
            return False
        try:
            current = int(client.incr(self._key))
            client.expire(self._key, 300)  # 5 分钟兜底
            if current > self._size:
                client.decr(self._key)
                return False
            self._acquired = True
            return True
        except Exception:
            return False

    def release(self) -> None:
        if not self._acquired:
            return
        self._acquired = False
        client = _redis_sync_client()
        if client:
            try:
                client.decr(self._key)
            except Exception:
                # best-effort 释放并发槽位：Redis 抖动不应中断调用方，
                # 但要留痕——否则槽位泄漏表现为「后面全部排队超时」，无从查起。
                logger.debug("释放并发槽位失败 key=%s", self._key, exc_info=True)


def _try_redis_slot(size: int) -> _RedisGate | None:
    """Redis 可用返回分布式闸门；不可用返回 None（走进程内路径）。"""
    if _redis_sync_client() is None:
        return None
    return _RedisGate(_GLOBAL_SEM_KEY, size)
