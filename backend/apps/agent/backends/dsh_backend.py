"""DeepSeek Harness 后端：把「同步 SDK 跑一轮 → 吐 SSE 事件」接成 ``AgentBackend``。

## 本模块管什么

从 ``_HarnessPool.acquire(...)`` 到本轮最后一个事件。三处必须自己造的东西：

1. **同步 → 异步桥**：SDK 是同步阻塞的（``Session.run()`` 一直到本轮结束才返回），
   增量事件只能从 ``on_notification`` 回调拿。编排层是 async 的，所以要把回调
   桥成 ``AsyncGenerator``（见 :class:`_NotificationBridge`）。
2. **事件翻译**：dsh 的 notification → ``sse_types.py`` 的 12 种契约事件
   （见 :meth:`DshBackend._translate`）。
3. **审批接收**：``approval_requests=True`` 后 runtime 会把 ``approval/request``
   塞进 ``client.next_request()`` 的队列，必须有人持续抽走并 reply，否则运行时
   会一直等（见 :class:`_ApprovalPump`）。

**不接管**（留在编排层 ``services/chat/stream.py``）：铸造用户凭证、落库、
事件总线订阅、用户文案翻译。边界与 ``pi_backend`` 完全一致，理由见 ``base.py``。

## 审批：默认 fail-closed（这是本模块唯一未完成的接线）

真实链路要求「dsh 的 approval 请求 → Django ``request_approval()`` → 前端卡片 →
用户决定 → ``client.respond()``」。这条链路**跨线程**：``next_request()`` 是阻塞
的同步调用，只能跑在线程里，而 ``request_approval`` 是 async 且要读 ORM、发
Redis。技术上可行（``asyncio.run_coroutine_threadsafe`` 把协程丢回主事件循环），
但它需要一次真实的 ``DEEPSEEK_API_KEY`` 跑通才能确认 payload 语义（例如
``callId`` 到底对应哪个工具调用、``reason`` 里有没有参数）。

因此本版本**默认 fail-closed**：拿到审批请求就记日志并 ``respond`` 一个
``rejected``，即高危工具调用会被拒绝但会话不崩。安全方向正确（宁拒不放），
但**功能上是未完成项**——用户会看到「dsh 拒绝了一次高危工具调用」而不是审批
卡片。接入闸门见 :data:`_APPROVAL_WIRED`。

``approval=False`` 时列在 ``_UNWIRED_KINDS`` 里的请求（``user-question/ask``）
必须 ``respond_error`` 清掉：不回的请求会让运行时永远挂起（实测表现为整轮
卡到超时），而会话本身的审批闸门仍在——drop 一个提问只是「模型这次没问到人」。
"""

from __future__ import annotations

import asyncio
import logging
import threading
from collections.abc import AsyncGenerator
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from typing import Any

from asgiref.sync import sync_to_async

from .base import BackendCapabilities, BackendError, BackendErrorKind, RunContext, StreamFrame

logger = logging.getLogger(__name__)

# 顶层 import 而不是延迟 import：本模块只能被 ``builtin.ensure_registered``
# **在 SDK 可用时**才导入（那里做 try/ImportError 判断）。若这里再延迟 import，
# 每次发事件都要多一次 ``import`` 查字典，且「SDK 没装」的失败点会从 import
# 边界漂到 stream 里——那时已经建好会话、铸好凭证，回滚代价大得多。
from deepseek_harness import DeepSeekHarness, DeepSeekHarnessConfig
from deepseek_harness.models import Notification

#: 审批接线是否完成。``False`` = fail-closed stub：收到审批请求即拒绝并记日志。
#: 改 ``True`` 前必须：①用真实 key 跑一次拿到真实 ``approval/request`` payload；
#: ②把 :class:`_ApprovalPump` 里的 stub 换成 ``request_approval`` 调用并写测试。
_APPROVAL_WIRED = False

#: 本模块会主动 reply 的请求方法；其余方法一律 ``respond_error`` 掉，绝不静默丢弃
#: （见模块 docstring）。
_APPROVAL_METHODS = frozenset({"approval/request"})

#: 无用户可见内容、但**属于已知语义**的通知方法（不该透传成 ``unknown``）。
#: ``session.status`` 是会话忙碌/空闲切换，``session.query.completed`` 是一次查询
#: 的收尾——两者的信息已由 ``run()`` 的返回值表达，再产事件只会让前端多出空 activity。
_SILENT_METHODS = frozenset({"session.status", "session.query.completed"})

#: 同上，按 ``session.event`` 里的 ``event.type`` 判定。
#: ``agent/inbox/spliced`` 是本轮 prompt 的入队回执（见 ``api.py`` 的
#: ``_is_inbox_receipt``），没有正文。
_SILENT_EVENT_TYPES = frozenset({"agent/inbox/spliced"})

#: 后台线程里跑 ``Session.run()`` 的线程池上限。dsh 一轮就是一个常驻子进程，
#: 线程只是「阻塞等待」，不占 CPU；上限取 8 与 pi 侧进程池默认（4）同量级留余量。
_MAX_RUNNING_THREADS = 8

#: 一轮结束后等待队列排空的超时（秒）。SDK 在 ``RunResult`` 返回前已经把本轮
#: 的通知全部投递给 ``on_notification``，但 ``call_soon_threadsafe`` 的投递与
#: 生成器侧的 ``await queue.get()`` 之间有一次线程切换，给一点余量。
_DRAIN_TIMEOUT_SECONDS = 2.0

#: 单轮运行结束的哨兵：放进事件队列表示「run 已返回（或抛异常）」。
_DONE = object()


def _log_unmapped(method: str, payload: dict[str, Any]) -> None:
    """未识别的事件记 debug 并原样透传给前端。

    为什么 debug 而不是 warning：dsh 的通知流里有大量内部方法（``session.status``
    / ``session.query.completed`` / ``agent/inbox/spliced`` …），每轮都会刷几十条，
    按 warning 记会把日志淹掉。但**必须记**——接入新版本时这些事件名会变，
    没有日志就只能靠猜。

    为什么透传而不是丢弃：pi 的 bridge 选择静默丢弃（把内部诊断挡在浏览器外），
    dsh 不一样——它的 SDK 是 rc 版本，事件名与字段都还没稳，静默丢弃会让「前端
    少了一栏内容」变成无迹可查。透传 ``unknown`` 让前端能选择忽略，也让联调时
    一眼看到「来了个我们不认识的事件」。**待真实 key 跑一次后按实际事件名收敛**：
    认识的按语义翻译，不认识的再考虑丢。
    """
    logger.debug("dsh 未映射事件 method=%s payload_keys=%s", method, sorted(payload))
    return


@dataclass(frozen=True)
class DshRunResult:
    """一轮跑完后交回编排层的事实（与 ``PiRunResult`` 同构，便于编排层统一处理）。

    ``model`` 只有解析成功才有值；``context_used`` / ``context_total`` **恒为
    ``None``**：dsh SDK 目前没有暴露会话水位/上下文统计的接口（``Session`` 只有
    ``run`` / ``get_working_directory``）。编造 0 会让前端显示「上下文已满」，
    所以如实留空。**待 SDK 暴露 usage/stats 后补**。
    """

    model: str | None
    context_used: int | None = None
    context_total: int | None = None


class _HarnessPool:
    """``(user_id, session_id)`` → ``DeepSeekHarness`` 的进程内池。

    ## 为什么不能全局单例

    ``DeepSeekHarness`` 持有一个 runtime 子进程与一份 ``DSH_HOME``。全局单例意味着
    所有律师共用一个子进程与一个 home 目录：

    - 串号：某个会话的 ``session_id`` 在同一进程里跨用户可见；
    - 阻塞互斥：``Session.run()`` 是同步阻塞的，一个长回合会把别人的请求排在后面。

    pi 的 ``pool.py`` 注释里踩过同一个坑（进程内状态按会话隔离），这里不重犯。

    ## 为什么键里要有 ``user_id``

    仅按 ``session_id`` 索引时，两个不同用户拿同一个 session_id（历史数据回填、
    前端构造）会共享子进程与 dsh home。加上 ``user_id`` 后这种碰撞只会退化为
    「多开一个进程」，不会串号。

    ## 上限

    ``_MAX_RUNNING_THREADS`` 是同时能跑的 run 数（线程池），这里的 ``max_size``
    是同时能持有的子进程数。两者取同一量级：子进程比线程贵得多（每个是一份
    node runtime）。超出即拒绝（``BUSY``），不排队——排队会把用户拖到
    超时都看不到反馈，而 dsh 只是可选后端，快速失败让用户切回 pi 体验更好。
    """

    def __init__(self, max_size: int = _MAX_RUNNING_THREADS) -> None:
        self._max_size = max(1, max_size)
        self._harnesses: dict[tuple[int | None, str], DeepSeekHarness] = {}
        self._lock = threading.Lock()

    @property
    def size(self) -> int:
        with self._lock:
            return len(self._harnesses)

    @staticmethod
    def key_for(ctx: RunContext) -> tuple[int | None, str]:
        """池键：``(user_id, 纯 dsh session id)``。

        session id 用 ``str(ctx.session.session_id)`` 而不是 ``ctx.run_id``：
        ``run_id`` 是 ``{session_id}:{kind}:{seq}`` 的**编排层寻址键**，dsh 要的是
        纯 session id（同一个 Django 会话多轮必须落到同一个 dsh 会话，否则每轮
        都从零开始、上下文全丢）。
        """
        return (ctx.user_id, str(ctx.session.session_id))

    def acquire(self, ctx: RunContext, config: DeepSeekHarnessConfig) -> DeepSeekHarness:
        """取（或新建并启动）本会话的 harness。

        Raises:
            BackendError: ``BUSY``（池满）/ ``UNAVAILABLE``（runtime 起不来）。

        为什么启动放在池里而不是 ``stream`` 里：``start()`` 失败就是「后端不可用」，
        这个分类属于池的生命周期，应该在拿到 harness 之前就分好。
        """
        key = self.key_for(ctx)
        with self._lock:
            existing = self._harnesses.get(key)
            if existing is not None:
                return existing
            if len(self._harnesses) >= self._max_size:
                raise BackendError(
                    BackendErrorKind.BUSY,
                    f"dsh 执行位已满（{self._max_size}），请稍后重试",
                    retryable=True,
                )
            # 占位后再启动：启动可能耗时数秒，期间不能放第二个请求进来建第二份。
            harness = DeepSeekHarness(config)
            self._harnesses[key] = harness
        try:
            harness.start()
        except Exception as exc:
            # 启动失败必须把占位删掉，否则这一格永远被一个死对象占着，
            # 后续同会话请求都会拿到它并立刻再失败一次。
            with self._lock:
                if self._harnesses.get(key) is harness:
                    self._harnesses.pop(key, None)
            raise BackendError.wrap(exc, BackendErrorKind.UNAVAILABLE, retryable=False) from exc
        return harness

    def release(self, ctx: RunContext) -> None:
        """关闭并移除本会话的 harness（尽力而为）。

        失败只记日志：关闭失败不该覆盖本轮已经吐给用户的内容，也不该把成功的一轮
        记成失败。残留的子进程由 runtime 自身的 shutdown 兜底。
        """
        key = self.key_for(ctx)
        with self._lock:
            harness = self._harnesses.pop(key, None)
        if harness is None:
            return
        try:
            harness.close()
        except Exception:
            logger.warning("关闭 dsh harness 失败 session=%s（忽略）", key[1], exc_info=True)

    def reset(self) -> None:
        """清空池（测试收尾 / 进程退出用）。"""
        with self._lock:
            harnesses = list(self._harnesses.values())
            self._harnesses.clear()
        for harness in harnesses:
            try:
                harness.close()
            except Exception:
                logger.debug("关闭 dsh harness 失败（忽略）", exc_info=True)


_pool = _HarnessPool()


def get_pool() -> _HarnessPool:
    """进程级池单例。"""
    return _pool


class _NotificationBridge:
    """把同步的 ``on_notification`` 回调桥成 ``asyncio.Queue``。

    ## 为什么是这个形状

    ``on_notification`` 在 SDK 的**调用线程**（也就是我们跑 ``run()`` 的线程）上
    同步调用，而消费方在事件循环里。跨线程往 ``asyncio.Queue`` 放东西必须走
    ``loop.call_soon_threadsafe``——直接 ``queue.put_nowait`` 在无锁竞争时「大多
    数时候」能工作，但那正是最难查的 bug（事件偶发丢失、表现为少一段正文）。

    ## 结束与异常

    - 运行正常结束时投递哨兵 :data:`_DONE`；
    - 运行抛异常时投递异常对象，由消费方转 ``BackendError``；
    - 投递用 ``put_nowait`` 不设上限：通知量与本轮 token 数同量级，设上限后
      ``put_nowait`` 会抛 ``QueueFull`` 而**吞掉事件**，比内存占用更糟。
    """

    def __init__(self, loop: asyncio.AbstractEventLoop) -> None:
        self._loop = loop
        self._queue: asyncio.Queue[Any] = asyncio.Queue()

    def put(self, item: Any) -> None:
        """线程安全投递（可从 SDK 回调线程调用）。"""
        self.put_finalizer(self._queue.put_nowait, item)

    def put_finalizer(self, callback: Any, *args: Any) -> None:
        """线程安全地把任意回调排进事件循环（结束信号走这里）。

        ``RuntimeError`` 必须吞：事件循环已关闭时（客户端断开后我们主动收尾）
        再投递没有任何人会消费，静默丢弃是正确行为——抛出去会打死 SDK 的调用
        线程，连带 ``run()`` 永远不返回。
        """
        try:
            self._loop.call_soon_threadsafe(callback, *args)
        except RuntimeError:
            logger.debug("dsh 事件循环已关闭，丢弃一条事件")

    async def get(self) -> Any:
        """取一条；返回 :data:`_DONE` 表示运行已结束。"""
        return await self._queue.get()

    def empty(self) -> bool:
        """队列是否已排空（只在事件循环线程里调用）。"""
        return self._queue.empty()

    def drain_pending(self) -> list[Any]:
        """非阻塞取走当前队列里的全部条目（收尾用，避免提前 break 时丢事件）。"""
        items: list[Any] = []
        while True:
            try:
                items.append(self._queue.get_nowait())
            except asyncio.QueueEmpty:
                return items


class _ApprovalPump:
    """持续抽 ``client.next_request()`` 并 reply 的后台线程。

    ## 为什么必须是独立线程

    ``next_request()`` 在内部 ``queue.Queue`` 上阻塞等待。``approval_requests=True``
    让 runtime 把审批请求发给我们而不是走它自己的 answerer，**没人抽就会一直挂**：
    表现是模型停在那里不动、直到超时。所以必须在 ``run()`` 之外另起一条线程。

    ## fail-closed

    本版本不接 Django 审批服务（见模块 docstring 的 ``_APPROVAL_WIRED``）：
    收到 ``approval/request`` 一律回 ``{"outcome": "rejected"}``。方向正确（高危
    工具宁拒不放），但用户拿不到审批卡片——这是**已知未完成项**。

    非审批类请求（``user-question/ask`` 等）回 ``respond_error``：不回的请求会让
    运行时永远等下去，而 ``respond_error`` 至少让模型拿到一个明确失败。

    ## 生命周期

    ``start()`` 起线程，``stop()`` 置停止标志并关闭 harness——**必须关 harness 才能
    让 ``next_request()`` 抛出**（它靠 ``_fail_waiters`` 往队列里塞 ``TransportClosedError``
    结束阻塞），所以 ``stop()`` 的顺序是「先置标志、再 close」。
    """

    def __init__(self, harness: DeepSeekHarness, kind: str) -> None:
        self._harness = harness
        self._kind = kind
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None

    def start(self) -> None:
        self._thread = threading.Thread(target=self._loop, name="dsh-approval-pump", daemon=True)
        self._thread.start()

    def stop(self) -> None:
        """置停止标志；**不 close harness**（关闭由池负责，顺序见类 docstring）。"""
        self._stop.set()

    def _loop(self) -> None:
        client = self._harness.client
        while not self._stop.is_set():
            try:
                request = client.next_request()
            except Exception:
                # runtime 关闭 / 传输断开：正常收尾路径，不是错误。
                logger.debug("dsh 请求队列已关闭，审批泵退出", exc_info=True)
                return
            if self._stop.is_set():
                return
            try:
                self._handle(request)
            except Exception:
                # 处理单条失败不能让泵死掉：泵死了后续审批全挂。
                logger.warning("处理 dsh 请求失败 method=%s", getattr(request, "method", "?"), exc_info=True)

    def _handle(self, request: Any) -> None:
        method = str(getattr(request, "method", "") or "")
        payload = getattr(request, "payload", {}) or {}
        if method in _APPROVAL_METHODS:
            tool_name = str(payload.get("toolName") or "")
            logger.warning(
                "dsh 审批未接入，按拒绝处理（fail-closed） tool=%s session=%s request=%s",
                tool_name,
                payload.get("sessionId"),
                getattr(request, "id", "?"),
            )
            # 【已知未接入】审批目前是 fail-closed：一律拒绝，不弹审批卡。
            #
            # 这不是遗漏，是**有意的待接入状态**：用户已确认「等 dsh SDK 自带审批
            # 能力后再接」。当前行为方向是安全的（高危工具被拒绝而非放行），
            # 只是体验缺口——律师看到的是「被拒绝」而不是审批弹窗。
            #
            # 接入位置就在下一行：把 rejected 换成调 Django 的 request_approval()，
            # 再把结果映射回 dsh 的决定。注意跨线程调 ORM 要用 sync_to_async。
            self._harness.client.respond(request.id, {"outcome": "rejected"})
            return

        _log_unmapped(method, dict(payload) if isinstance(payload, dict) else {})
        # 必须显式回错：不回的话 runtime 会一直等这个请求。
        self._harness.client.respond_error(
            request.id,
            code=-32601,
            message=f"unsupported method: {method}",
        )


def _acquire_without_proxy(pool: Any, ctx: RunContext, sdk_config: Any) -> Any:
    """在「代理变量已拿掉」的环境里取 harness。

    单独一个模块级函数而不是内联 lambda：它要在线程里跑（``sync_to_async``），
    而上下文管理器必须在**同一线程**内进出——写成闭包容易被误当成可重入。
    """
    # 延迟 import：dsh_config 会读 LLMProvider（同步 ORM），而本模块在
    # 「SDK 没装」时也要能被 import（builtin 用 ImportError 判定可否注册）。
    from .dsh_config import without_proxy_env

    with without_proxy_env():
        return pool.acquire(ctx, sdk_config)


class DshBackend:
    """DeepSeek Harness 运行时（常驻子进程池化，同步 SDK 桥成异步事件流）。

    能力声明见 ``capabilities``：``steer`` 为 ``False``，因为 SDK 的 ``Session``
    只暴露 ``run`` / ``get_working_directory``，没有 steer / abort 的公开方法。
    声明 ``True`` 会让前端渲染出插话输入框，而用户敲进去的话会被直接丢弃——
    比禁用更糟（见 ``base.py`` 的 ``steer`` 字段注释）。

    ``concurrent_in_session`` 为 ``False``：同一个 dsh session id 上没有并发保护，
    两个 run 同时打到同一个 session 会让上下文交错。保守声明，与 pi 一致。
    """

    kind = "dsh"
    capabilities = BackendCapabilities(
        streaming=True,
        tool_calls=True,
        approval=True,
        compaction=True,
        steer=False,
        concurrent_in_session=False,
    )

    #: 按 ``run_id`` 归集的收尾事实。键控而不是单值——注册表里是单例，
    #: 实例属性会在并发会话间互相覆盖（pi 的 ``PiBackend`` 同因同解）。
    _results: dict[str, DshRunResult]

    def __init__(self, pool: _HarnessPool | None = None) -> None:
        self._results = {}
        self._pool = pool if pool is not None else get_pool()
        self._executor = ThreadPoolExecutor(max_workers=_MAX_RUNNING_THREADS, thread_name_prefix="dsh-run")

    def result_for(self, run_id: str) -> DshRunResult | None:
        """取某一轮的收尾事实；未跑过 / 本轮异常时为 ``None``。"""
        return self._results.get(run_id)

    def stream(self, ctx: RunContext) -> AsyncGenerator[StreamFrame, None]:
        """跑一轮，产出一轮全部 SSE 事件。

        事件体已带 ``agent="dsh"`` 与 ``run_id=ctx.run_id``；``meta`` / ``done``
        由编排层发（与 pi 一致）。其余细节见 :meth:`_stream`。

        Raises:
            BackendError: 配置不可用 / 池满 / SDK 异常，均在边界处转换。
                ``asyncio.CancelledError`` 原样上抛（用户按停止不是错误）。
        """
        return self._stream(ctx)

    # ── 主流程 ───────────────────────────────────────────────────────────

    async def _stream(self, ctx: RunContext) -> AsyncGenerator[StreamFrame, None]:
        session_id = str(ctx.session.session_id)
        # 解析 provider 走同步 ORM：必须放线程里。放主线程会抛
        # SynchronousOnlyOperation（并被兜底 except 吞成「未知错误」）。
        config = await self._resolve_config(ctx)
        model = config.model

        harness = await self._acquire(ctx, config)
        approval_pump = _ApprovalPump(harness, self.kind)
        if _APPROVAL_WIRED:
            approval_pump.start()

        bridge = _NotificationBridge(asyncio.get_running_loop())
        run_done = asyncio.Event()
        run_error: list[BaseException] = []
        # run_id 先声明：取消路径的日志要用它归因（两个 agent 同题并行时，
        # 只有 session_id 分不清是哪一条流被中止了）。
        run_id = ctx.run_id

        def _on_notification(notification: Notification) -> None:
            """SDK 回调（运行线程上同步调用）：只做投递，不做任何 IO/ORM。"""
            payload = dict(notification.payload or {})
            bridge.put((notification.method, payload))

        def _run_blocking() -> None:
            try:
                harness.run(ctx.prompt, session_id=session_id, on_notification=_on_notification)
            except BaseException as exc:
                # 捕 ``BaseException`` 而不是 ``Exception``：运行线程里的任何逃逸异常
                # 都会让 ``run()`` 永远不返回而消费侧无限等待，捕范围越宽越安全。
                # ``CancelledError`` 不会出现在这条线程上（它不跑协程）。
                run_error.append(exc)
            finally:
                bridge.put(_DONE)
                bridge.put_finalizer(run_done.set)

        try:
            self._results.pop(run_id, None)
            future = self._executor.submit(_run_blocking)
            try:
                async for frame in self._consume(bridge, run_done, run_error, ctx, model):
                    yield frame
            except asyncio.CancelledError:
                # 取消：尽力让线程里的 run 尽快退出。SDK 没有 abort 接口，能做的是
                # 关闭 harness（子进程收到 shutdown 后 reader 线程报错，run 里阻塞的
                # 订阅者随之抛 TransportClosedError）。这里**不等**它跑完——
                # 关闭可能耗时几百毫秒，等它会把「用户按停止」变成「点了没反应」。
                logger.info(
                    "dsh 本轮被取消 session=%s run=%s，尝试关闭 harness 让运行线程退出",
                    session_id,
                    run_id,
                )
                self._pool.release(ctx)
                raise
            finally:
                approval_pump.stop()
                # 取消路径之外，future 应该已结束；加 done_callback 兜住「生成器
                # 提前 break 但线程还在跑」的情况，避免线程泄漏到进程退出。
                future.add_done_callback(self._log_thread_failure)
                if not future.done():
                    logger.warning("dsh 运行线程未在本轮结束时退出 session=%s run=%s", session_id, run_id)
        finally:
            # 正常结束也释放：dsh 是常驻子进程，不释放会一直占着内存与池位。
            # 放在最后而不是 ``async for`` 后：``done`` 事件之后编排层不会再拉
            # 生成器，只有 ``finally`` 保证释放一定发生。
            self._pool.release(ctx)

    async def _resolve_config(self, ctx: RunContext) -> Any:
        """解析本轮 dsh 配置；不可用时报可读错误而不是静默用默认值。

        ``user_token`` 必须在这里传进去：业务工具的 MCP patch 里那行
        ``Authorization: Bearer <token>`` 只能用**本轮律师**的票（``:8011`` 强制
        每个请求带它，且刻意不回退服务账号）。``user_id`` 只决定 dsh home 归属，
        不能拿来换代币。

        为什么不在 ``_acquire`` 里补写 patch：配置在进池前就定了（``patches``
        是 ``DeepSeekHarnessConfig`` 的构造参数），事后补写文件不会被已经拼好的
        ``--patch`` 命令行看到——那是「文件写对了但没生效」的静默故障。
        """
        from . import dsh_config as config_module

        try:
            config = await sync_to_async(config_module.build_config, thread_sensitive=True)(
                user_id=ctx.user_id,
                model_hint=ctx.model,
                user_token=ctx.user_token,
            )
        except Exception as exc:
            # 读库失败（连接断了 / 迁移没跑）：这是后端基础设施问题，不是配置缺失。
            raise BackendError.wrap(exc, BackendErrorKind.UNAVAILABLE) from exc
        if config is None:
            # 明确告诉用户「没有可用的平台配置」，而不是让 dsh 用自己的默认 provider
            # ——那会用错的 key、打到官方端点，账目与结果都不可信。
            raise BackendError(
                BackendErrorKind.UNAVAILABLE,
                "未配置可用的 AI 平台（base_url / api_key），dsh 无法启动；请联系管理员",
            )
        return config

    async def _acquire(self, ctx: RunContext, config: Any) -> DeepSeekHarness:
        """取池里的 harness（同步启动放线程，避免卡住事件循环数秒）。

        **子进程启动必须包在 `without_proxy_env()` 里**：律所大模型网关是内网
        地址，而开发机的 `HTTPS_PROXY` 指向本地 Clash；dsh SDK 用
        `os.environ.copy()` 构造子进程环境（只能加不能删），不拿掉代理变量的话
        请求会被送到代理 → 代理无法回源内网 → 网关侧 **502 no body**。

        实测（正式验收）：同一 key + base_url，直连 `chat/completions` 正常回答，
        走代理则 502 且重试 5 次后返回空。
        与 `pi/rpc_client.py` 的 `_clean_env` 是同一个坑、同一种解法。
        """
        sdk_config = DeepSeekHarnessConfig(**config.sdk_kwargs())
        # 用**本模块自己的 executor**（`_executor`，thread_name_prefix="dsh-run"），
        # 不用 ``sync_to_async(..., thread_sensitive=False)``。
        #
        # 理由（本仓 `test_db_pool_default_off` 的审计要求）：
        # 起 dsh 子进程是**秒级长任务**且**完全不碰 DB**，thread_sensitive=False
        # 会把这类长任务塞进全局共享线程池，挤占其它 sync_to_async 的槽位
        # （历史上就因此引发过 PoolTimeout）。审计用例的建议正是「长任务改用
        # 显式 executor」——这里照做，同时让 `thread_sensitive=False` 的总量
        # 保持基线不变（新增必须被看见，但能不新增就不新增）。
        loop = asyncio.get_running_loop()
        return await loop.run_in_executor(self._executor, _acquire_without_proxy, self._pool, ctx, sdk_config)

    # ── 事件消费与翻译 ───────────────────────────────────────────────────

    async def _consume(
        self,
        bridge: _NotificationBridge,
        run_done: asyncio.Event,
        run_error: list[BaseException],
        ctx: RunContext,
        model: str,
    ) -> AsyncGenerator[StreamFrame, None]:
        """从队列取通知并产出 SSE 事件，直到运行结束。

        ``done`` 由编排层统一发（``stream.py`` 最后那个 ``yield done``），本层
        不重复发——协议要求「一轮只一个 done」，两个来源必然有一个要猜。
        """
        done_seen = False
        while True:
            if run_done.is_set() and bridge.empty():
                # 运行已返回且队列排空：真结束。若队列里还留着事件（SDK 先投递通知、
                # 再让 run 返回），下面继续按普通条目消费，末段正文不会丢。
                break
            try:
                item = await asyncio.wait_for(bridge.get(), timeout=_DRAIN_TIMEOUT_SECONDS)
            except TimeoutError:
                if run_done.is_set():
                    break
                # 本轮暂时没有新事件：让出一个 tick，编排层借这个间隙把外部总线里
                # 的审批事件推进来（与 pi 的 ``yield None`` 语义一致）。
                yield None
                continue
            if item is _DONE:
                break
            method, payload = item
            for frame in self._translate(method, payload):
                done_seen = True
                yield {**frame, "agent": self.kind, "run_id": ctx.run_id}
        # 运行抛了异常：即使事件流已结束也要让编排层知道（否则前端看到的是
        # 「正常结束但答了一半」）。抛在循环之后而不是每次取到事件就抛，是为了
        # 让 run 失败前已投递的事件先送到前端——用户至少看到失败前的进度。
        if run_error:
            raise self._wrap_error(run_error[0])
        if done_seen:
            # 收尾事实必须在消费结束时（含 done 之前）就位：编排层靠它回写
            # ``AgentSession.llm_model`` 与 ``AgentRun.model``，留空会让成本归因
            # 丢掉模型维度。水位恒为 None（SDK 未暴露，见 ``DshRunResult``）。
            self._results[ctx.run_id] = DshRunResult(model=model)

    def _translate(self, method: str, payload: dict[str, Any]) -> list[dict[str, Any]]:
        """把一条 dsh 通知翻成 0..n 个 SSE 事件。

        ## 已知的 dsh 事件形态（从 SDK 源码确认，非实测）

        ``api.py`` 的 ``_RunActivity.record`` 只在 ``method == "session.event"`` 且
        ``payload["sessionId"] == 本会话`` 时把 ``payload["event"]`` 收进
        ``RunResult.events``；``final_response()`` / ``finish_reason()`` 则按
        ``event["type"]`` 读取：

        - ``assistant/message`` → ``event["data"]["message"]["content"]`` 里的
          ``{"type": "text", "text": ...}`` 块（或 ``data.content``）
        - ``turn/end`` → ``event["data"]["reason"]["kind"]``
        - ``agent/inbox/spliced`` → 本轮 prompt 的入队回执

        所以本函数的主路径是「先拆 ``session.event`` 外壳，再看 ``event.type``」。

        ## 正文增量 vs 整段

        SDK 源码**没有**暴露逐 token 的增量事件名（``assistant/message`` 看起来是
        整条消息）。因此本版本对 ``assistant/message`` 按「整段 delta」下发：一次
        ``run`` 里若有多个 assistant 消息（工具循环），会产出多个 ``delta``，前端
        拼接后与全文一致。``capabilities.streaming=True`` 的语义是「产出 delta 事件」
        ——这一点成立（只是粒度粗），前端仍能逐条追加而不是等全部结束。

        **待真实 key 跑一次后按实际事件名收敛**：若存在 ``assistant/delta`` 之类的
        增量事件，加一个分支即可，无需改本函数的骨架。
        """
        event: dict[str, Any] | None = None
        if method == "session.event":
            raw_event = payload.get("event")
            if isinstance(raw_event, dict):
                event = raw_event
        if event is not None:
            event_type = str(event.get("type") or "")
            raw_data = event.get("data")
            data: dict[str, Any] = raw_data if isinstance(raw_data, dict) else {}
            frames = self._translate_event(event_type, data)
            if frames is not None:
                return frames
            # 认得 ``session.event`` 外壳但不认得 ``event.type``：透传而不是静默吞。
            _log_unmapped(method, event)
            return [{"type": "unknown", "raw": {"method": method, "event": event}}]

        if method in _SILENT_METHODS:
            # 生命周期类通知没有事件体：运行开始/结束/入队回执，由 ``run()`` 的
            # 返回与哨兵表达。产事件会让前端多出无内容的 activity。
            return []
        if method in _APPROVAL_METHODS:
            # 审批请求走 ``next_request`` 通道（见 ``_ApprovalPump``），不走通知流。
            # 走到这里说明 runtime 版本变了，记日志即可（不能静默）。
            _log_unmapped(method, payload)
            return []
        _log_unmapped(method, payload)
        return [{"type": "unknown", "raw": {"method": method, "payload": payload}}]

    def _translate_event(self, event_type: str, data: dict[str, Any]) -> list[dict[str, Any]] | None:
        """按 ``event["type"]`` 分派；返回 ``None`` 表示**不认识的类型**。

        为什么要区分「认识但无事件」和「不认识」：两者都产出空列表的话，调用方
        无法判断该不该透传 ``unknown``——`turn/end` 正常结束（空）与全新事件类型
        （该透传）会混成一类，前者会被当成未知事件刷到前端。

        每个分支的注释说明「为什么这么取字段」——字段名来自 SDK 源码里的
        ``final_response`` / ``finish_reason``，不是猜的。
        """
        if event_type == "assistant/message":
            return self._translate_assistant_message(data)
        if event_type == "turn/end":
            # 本轮结束。``reason.kind`` 为 ``"error"`` 时是模型侧失败（SDK 的
            # ``finish_reason``），要报成 error 而不是静默结束——否则用户看到的是
            # 「答了一半就没了」且没有任何解释。
            reason = data.get("reason") if isinstance(data.get("reason"), dict) else {}
            kind = str((reason or {}).get("kind") or "")
            if kind == "error":
                message = str((reason or {}).get("message") or "dsh 本轮以 error 结束")
                return [{"type": "error", "message": message}]
            return []
        if event_type in _SILENT_EVENT_TYPES:
            # 入队回执等：有事件体但无用户可见内容。
            return []
        return None

    @staticmethod
    def _translate_assistant_message(data: dict[str, Any]) -> list[dict[str, Any]]:
        """``assistant/message`` → ``thinking`` / ``delta`` / ``tool_call``。

        字段形状照 ``api.py`` 的 ``final_response``：

        ::

            data["message"]["content"] = [
                {"type": "text", "text": "..."},
                {"type": "thinking", "text": "..."},        # 思考块（推断）
                {"type": "toolCall", ...},                  # 工具调用（推断）
            ]

        ``final_response`` 里的 ``content_owner = message if isinstance(message, dict)
        else data``，说明两种形状都可能出现（有 ``message`` 包装 / 无包装）。
        这里同样两路都认。

        思考块与工具调用块的类型名是**推断**（``final_response`` 只处理 text 块，
        源码里没有它们的定义）。认得就翻译，认不得就跳过——**待真实跑一次后按
        实际类型名收敛**，跳过的部分会体现在工具调用数为 0 上，不会静默变成正文。
        """
        message = data.get("message") if isinstance(data.get("message"), dict) else data
        content = (message or {}).get("content")
        if not isinstance(content, list):
            return []
        frames: list[dict[str, Any]] = []
        for block in content:
            if not isinstance(block, dict):
                continue
            block_type = str(block.get("type") or "")
            if block_type == "text":
                text = block.get("text")
                if isinstance(text, str) and text:
                    frames.append({"type": "delta", "content": text})
            elif block_type in ("thinking", "reasoning"):
                text = block.get("text") or block.get("thinking")
                if isinstance(text, str) and text:
                    frames.append({"type": "thinking", "content": text})
            elif block_type in ("toolCall", "tool_call"):
                call_id = str(block.get("id") or block.get("toolCallId") or "")
                name = str(block.get("name") or block.get("toolName") or "")
                if call_id and name:
                    args = block.get("arguments") or block.get("args")
                    frames.append(
                        {
                            "type": "tool_call",
                            "tool_call_id": call_id,
                            "name": name,
                            "arguments": args if isinstance(args, str) else None,
                        }
                    )
        return frames

    @staticmethod
    def _wrap_error(exc: BaseException) -> BackendError:
        """把 SDK / 传输异常转成 ``BackendError``（分类见 ``base.py`` 的映射表口径）。

        分类依据只能是消息：dsh 的 ``HarnessError`` 层次（``TransportClosedError`` /
        ``JsonRpcError`` / ``SdkProtocolError``）都只带文本。按关键词分四类，
        与 pi 的做法一致——粗糙但比「一律未知」好：``AUTH`` / ``CONTEXT_OVERFLOW``
        不会被提示成「请稍后重试」。
        """
        if isinstance(exc, BackendError):
            return exc
        text = str(exc) or exc.__class__.__name__
        lowered = text.lower()
        if "api key" in lowered or "401" in lowered or "403" in lowered or "unauthorized" in lowered:
            return BackendError.wrap(exc, BackendErrorKind.AUTH)
        if "429" in lowered or "rate limit" in lowered:
            return BackendError.wrap(exc, BackendErrorKind.RATE_LIMITED, retryable=True)
        if "context" in lowered and ("window" in lowered or "length" in lowered or "overflow" in lowered):
            return BackendError.wrap(exc, BackendErrorKind.CONTEXT_OVERFLOW)
        if isinstance(exc, FileNotFoundError):
            # runtime 可执行文件缺失（未装 deepseek-harness-runtime-bin）。
            return BackendError.wrap(exc, BackendErrorKind.UNAVAILABLE)
        return BackendError.wrap(exc, BackendErrorKind.UNKNOWN)

    @staticmethod
    def _log_thread_failure(future: Any) -> None:
        """线程池任务的兜底日志：吞掉的异常会让「运行没跑完」无迹可查。"""
        try:
            exc = future.exception()
        except asyncio.CancelledError:
            return
        if exc is not None:
            logger.warning("dsh 运行线程异常（本轮已按失败上报）", exc_info=exc)
