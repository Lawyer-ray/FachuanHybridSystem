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

例外是**隔离运行**（``acquire(isolated=True)``，综合结论这类一次性任务）：cwd、
配置目录与 session 文件都落在一次性的临时根目录里、用临时 session id，本轮结束即
整体删除——不读也不写真实会话的 pi 历史。
"""

from __future__ import annotations

import asyncio
import contextlib
import logging
import shutil
import tempfile
import time
import uuid
from collections.abc import AsyncIterator, Callable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from .rpc_client import PiError, PiRpcSession
from .session_store import layout
from .shared_mcp import YUANDIAN_API_KEY_ENV, McpEndpoint, write_pi_config

logger = logging.getLogger(__name__)


def _yuandian_env() -> dict[str, str]:
    """元典 MCP 的 Bearer key → pi 子进程 env；总开关关闭或没配 key 时返回空字典。

    同步函数：内部读 SystemConfig（同步 ORM），调用方必须用
    ``sync_to_async(..., thread_sensitive=True)`` 包住。

    **每个 pi 进程一把 key**：多把 key 时按进程内轮转（:func:`pick_api_key`），
    每次 ``acquire`` 拉起的新进程拿下一把。做不到按调用换 key——``mcp.json`` 里的
    ``Bearer ${...}`` 在 pi 启动时静态展开，同一进程内某把 key 被元典 429 了也换不了，
    只能等下一个进程。

    没 key 时**不写空串**：``Bearer ${...}`` 展开成 ``Bearer `` 只会换来一条看不懂的
    401；而且此时 :func:`shared_mcp._build_yuandian_server_entries` 也不会挂元典 server。
    """
    from apps.core.services.yuandian_settings import load_yuandian_settings, pick_api_key, yuandian_mcp_enabled

    if not yuandian_mcp_enabled():
        return {}
    api_keys = load_yuandian_settings().api_keys
    if not api_keys:
        return {}
    return {YUANDIAN_API_KEY_ENV: pick_api_key(api_keys)}


#: 隔离运行的临时根目录放在稳定根目录（``layout()`` 的父目录）下的这个子目录里。
ISOLATED_DIR_NAME = "isolated"

#: 超过这个时长的隔离目录视为进程崩溃残留（正常一轮早已结束并删除），建新目录时顺手清掉。
ISOLATED_STALE_SECONDS = 6 * 3600


def _make_isolated_root(stable_work_dir: Path) -> Path:
    """为一次隔离运行建临时根目录（``work/`` + ``config/`` + ``sessions/``，0700）。

    放在稳定根目录下而不是系统 ``/tmp``：里面会写含真实 key 的 models.json，
    与常规配置同一处、同一权限口径；``mkdtemp`` 本身就以 0700 创建。
    """
    base = Path(stable_work_dir).parent / ISOLATED_DIR_NAME
    base.mkdir(parents=True, exist_ok=True)
    _sweep_stale_isolated_roots(base)
    root = Path(tempfile.mkdtemp(prefix="run-", dir=str(base)))
    for name in ("work", "config", "sessions"):
        (root / name).mkdir(mode=0o700, exist_ok=True)
    return root


def _sweep_stale_isolated_roots(base: Path) -> None:
    """删掉进程崩溃时没来得及清理的隔离目录（里面有 key 与对话内容，不能长期留盘）。"""
    deadline = time.time() - ISOLATED_STALE_SECONDS
    for child in base.iterdir():
        try:
            stale = child.is_dir() and child.stat().st_mtime < deadline
        except OSError:
            continue
        if stale:
            _remove_isolated_root(child)


def _remove_isolated_root(root: Path) -> None:
    """删隔离运行的临时目录；失败只告警（目录里有 key 与对话内容，必须留痕）。"""

    def _warn(func: Callable[..., Any], path: str, exc: BaseException) -> None:
        logger.warning("隔离运行临时目录清理失败 path=%s（含 key 与对话内容）: %s", path, exc)

    shutil.rmtree(root, onexc=_warn)


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
        容量），不可用（或闸门操作本身失败）退化为进程内 asyncio.Semaphore。

        Raises:
            PoolQueueTimeoutError: 排队超过 ``queue_timeout``。
        """
        # P2-2：Redis 分布式信号量路径。INCR/EXPIRE/DECR 是同步网络 IO，
        # 必须放线程里跑，否则每次闸门操作都阻塞整个事件循环（所有 SSE 一起卡）。
        redis_gate = _try_redis_slot(self.size)
        if redis_gate is not None and await self._acquire_redis_slot(redis_gate):
            try:
                yield
            finally:
                # to_thread 的线程不受 await 取消影响，release 必然执行完（同原同步语义）
                await asyncio.to_thread(redis_gate.release)
            return

        # 进程内信号量路径：本来就没有 Redis，或闸门刚刚报错降级（见 _acquire_redis_slot）
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

    async def _acquire_redis_slot(self, redis_gate: _RedisGate) -> bool:
        """在分布式闸门上等到一个执行位。

        Returns:
            ``True`` = 已拿到执行位（调用方必须在退出时 ``release``）；
            ``False`` = 闸门不可用，调用方改走进程内信号量。

        Raises:
            PoolQueueTimeoutError: 等到 ``queue_timeout`` 仍无空位（真容量满）。

        S37-09（2026-11-23 二轮审计）：原实现把 ``try_acquire`` 的两个失败面
        （Redis 报错 / 容量满）当同一个 ``False``，每 0.2 秒重试一次直到
        ``queue_timeout``（默认 60 秒）——Redis 一抖（重启/超时/OOM/ACL 变更），
        全机所有对话就统一报「执行位已满（全机容量 4）」，与真容量满文案一模一样，
        且 ``try_acquire`` 的 except 分支一行日志都没有，日志里查不到 Redis 故障痕迹。
        现在闸门操作失败抛 :class:`_RedisGateUnavailable`：本 worker 立即降级为
        进程内信号量（仍限流），并留一条 warning；只有真的排满才抛
        ``PoolQueueTimeoutError``。
        """
        timeout = self._config.queue_timeout
        deadline = asyncio.get_event_loop().time() + (timeout if timeout > 0 else 3600)
        while True:
            try:
                if await asyncio.to_thread(redis_gate.try_acquire):
                    return True
            except _RedisGateUnavailable:
                logger.warning(
                    "Redis 执行位闸门不可用，本次降级为进程内信号量（容量 %s）",
                    self.size,
                    exc_info=True,
                )
                return False
            if timeout > 0 and asyncio.get_event_loop().time() >= deadline:
                raise PoolQueueTimeoutError(f"agent 执行位已满，排队超过 {timeout:.0f} 秒（全机容量 {self.size}）")
            await asyncio.sleep(0.2)

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
        tool_exclude: frozenset[str] | None = None,
        skill_paths: list[str] | None = None,
        api_key: str | None = None,
        isolated: bool = False,
        system_prompt: str | None = None,
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
            api_key: 本轮编排层指定的网关 key（``RunContext.api_key``），原样转交
                ``write_pi_config`` 写进 models.json；``None`` 时仍由写函数按
                ``_next_key`` 轮转（旧行为）。
            isolated: 隔离运行（``RunContext.isolated``）。为 ``True`` 时本轮用一次性
                临时根目录（cwd / ``PI_CODING_AGENT_DIR`` / session 文件都在里面）与
                临时 pi session id，**不读不写** ``session_id`` 对应的会话历史；本轮结束
                （含异常 / 取消）后整个目录删除；也不加载记忆注入 extension（律师个人
                记忆不进综合这类一次性任务）。``session_env`` 照旧注入，审批卡仍投到
                真实会话。
            system_prompt: 替换本轮的 ``AGENTS.md``（法穿给 pi 注入人格的唯一挂载点）。
                只在 ``isolated=True`` 时支持：常规路径的配置目录是全局共享的，不能为
                一轮改全局文件。非隔离时传入直接抛 ``PiError``，不静默忽略。

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
        if system_prompt is not None and not isolated:
            raise PiError("pi 只在隔离运行时支持替换 system prompt（配置目录全局共享，不能为一轮改全局 AGENTS.md）")
        effective_model = model or self._config.model
        # 稳定布局：work（cwd）/ config（PI_CODING_AGENT_DIR）/ sessions
        cwd, config_dir, sessions_root = layout()
        session_dir = str(Path(sessions_root) / session_id) if session_id else None
        pi_session_id = session_id
        isolated_root: Path | None = None
        session: PiRpcSession | None = None
        aborted = False
        queued = self._semaphore.locked()
        if queued:
            await self._announce_queue()
        try:
            async with self._slot():
                try:
                    if isolated:
                        # 拿到执行位后才建目录：排队期间不占磁盘、不留含 key 的文件。
                        isolated_root = _make_isolated_root(Path(cwd))
                        pi_session_id = uuid.uuid4().hex
                        cwd = isolated_root / "work"
                        config_dir = isolated_root / "config"
                        session_dir = str(isolated_root / "sessions" / pi_session_id)
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
                        config_dir, self._config.mcp_endpoint, model_hint=effective_model or "", api_key=api_key
                    )
                    if system_prompt is not None:
                        # 只会落到隔离目录（上面已拦住非隔离）：覆盖 write_pi_config 刚写的
                        # 法穿默认 AGENTS.md，本轮的人格与规则就是调用方给的这一份。
                        (Path(config_dir) / "AGENTS.md").write_text(system_prompt, encoding="utf-8")
                    # 思考等级由 write_pi_config 一并写入隔离目录的 settings.json
                    # （pi 官方开关是 modelThinkingLevels，不是 CLI 参数也不是
                    # models.json 的 reasoning 字段）。
                    #
                    # 元典 key 只经 env 进 pi：mcp.json 里写的是
                    # ``Bearer ${FACHUAN_YUANDIAN_API_KEY}`` 占位，这里注入真值。
                    # 与 write_pi_config 各自读一次库（get_value 有 300s 缓存，代价是
                    # 一次缓存命中），换来 write_pi_config 返回值仍是 Path——改成
                    # ``(path, env)`` 会波及拿它当路径用的调用点与既有断言。
                    yuandian_env = await sync_to_async(_yuandian_env, thread_sensitive=True)()
                    env = {
                        **(self._config.extra_env or {}),
                        "PI_CODING_AGENT_DIR": str(config_dir),
                        **yuandian_env,
                    }
                    env.update(session_env or {})
                    session = PiRpcSession(
                        cwd=str(cwd),
                        model=effective_model,
                        provider=self._config.provider,
                        extension_path=self._config.extension_path,
                        extra_env=env,
                        session_dir=session_dir,
                        session_id=pi_session_id,
                        tool_selection=tool_selection,
                        exclude_tools=tool_exclude,
                        skill_paths=skill_paths,
                        memory_injection=not isolated,
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
            if isolated_root is not None:
                _remove_isolated_root(isolated_root)
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

#: 闸门操作可能抛的具体异常（连接断 / 超时 / ACL 变更 / 协议错）。
#:
#: 不用裸宽捕获：异常棘轮禁止新增，而这里失败就该降级，
#: 用一个具名元组反而更诚实（与 ``event_bus._CACHE_ERRORS`` 同口径）。
_GATE_ERRORS: tuple[type[BaseException], ...] = (OSError, ValueError, TypeError, RuntimeError)
try:  # pragma: no cover - redis 随 RedisCache 一起装，这里只为类型收敛
    from redis.exceptions import RedisError as _RedisError

    _GATE_ERRORS = (*_GATE_ERRORS, _RedisError)
except ImportError:  # pragma: no cover
    pass


class _RedisGateUnavailable(Exception):
    """闸门操作失败（Redis 连不上 / 报错）。

    与「执行位已满」是两回事：满员是**正常排队的结论**，闸门不可用是**降级信号**
    （见 ``PiProcessPool._acquire_redis_slot``）。
    """


def _redis_sync_client() -> Any:
    """原生 Redis 客户端（同步；与 event_bus 同源判定）。"""
    from ..services.event_bus import raw_redis_client

    return raw_redis_client()


class _RedisGate:
    """极简分布式计数闸门：INCR/DECR + TTL 兜底回收。

    不是可重入锁——只做跨 worker 共享容量计数。进程崩溃后计数由 TTL 归零。
    """

    def __init__(self, key: str, size: int) -> None:
        self._key = key
        self._size = size
        self._acquired = False

    def try_acquire(self) -> bool:
        """试着占一个执行位。

        Returns:
            ``True`` = 占到了；``False`` = 容量已满（**正常排队信号**）。

        Raises:
            _RedisGateUnavailable: Redis 连不上或 INCR/EXPIRE 报错（**降级信号**）。

        S37-09（2026-11-23 二轮审计）：原实现是裸 except + return False——
        把「Redis 故障」和「容量满」混成同一个返回值，且一行日志都不留。
        """
        client = _redis_sync_client()
        if client is None:
            raise _RedisGateUnavailable("Redis 客户端不可用")
        incremented = False
        try:
            current = int(client.incr(self._key))
            incremented = True
            client.expire(self._key, 300)  # 5 分钟兜底
        except _GATE_ERRORS as exc:
            if incremented:
                # INCR 已生效但 EXPIRE 没写下去：尽力归还这一格，
                # 否则计数没有 TTL 兜底，会永久泄漏成「容量永远满」。
                with contextlib.suppress(*_GATE_ERRORS):
                    client.decr(self._key)
            raise _RedisGateUnavailable(str(exc)) from exc
        if current > self._size:
            # 容量满：把刚多占的一格还回去（归还失败不影响「满员」这个结论）
            with contextlib.suppress(*_GATE_ERRORS):
                client.decr(self._key)
            return False
        self._acquired = True
        return True

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
                logger.warning("释放并发槽位失败 key=%s", self._key, exc_info=True)


def _try_redis_slot(size: int) -> _RedisGate | None:
    """Redis 可用返回分布式闸门；不可用返回 None（走进程内路径）。"""
    if _redis_sync_client() is None:
        return None
    return _RedisGate(_GLOBAL_SEM_KEY, size)
