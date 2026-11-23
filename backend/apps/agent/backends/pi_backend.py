"""pi 后端：把「借一个 pi 进程 → 跑一轮 → 归还」收成一个 ``AgentBackend``。

## 边界（本模块只管什么）

接管范围从 ``pi_pool.acquire(...)`` 一直到本轮最后一个事件。搬自
``services/chat/stream.py``（原 chat_service.py）里那段踩过坑的逻辑，**逐行原样**
搬过来，注释一起搬——那些细节（上下文水位取法、审批事件插队、取消语义、pending
``__anext__`` 回收）每一条都对应一次线上故障，重写一遍等于重新踩一遍。

**不接管**（留在 ``services/chat/stream.py`` 编排层）：

- 铸造用户凭证（``env.mint_user_token``）：铸不出就整轮拒绝，那是编排层的准入；
- token 累加、写 ``AgentMessage`` / 会话标题 / ``AgentRun`` 成本记录：审计与成本
  只能有一个写入方，后端写库就会出现两套来源（见 ``base.py`` 的分工边界）；
- 事件总线 ``bus.register`` 的订阅：跨进程传输不归后端管；
- ``PoolQueueTimeoutError`` / ``PiError`` 的翻译：后端只按契约抛自己的异常，
  翻译成人话由编排层做。

## 审批事件为什么不进这里

pi 的审批走 extension → Redis → 事件总线，不在 pi 的事件流里。编排层从总线队列
非阻塞取。本模块在「本轮暂时没有新事件」时产出一个 ``None`` 让出控制权，编排层
借这个 tick 把审批事件推进来——这样两者都不用把对方的队列知识写进自己肚子。
``None`` 不是 SSE 事件，不转发给前端。
"""

from __future__ import annotations

import asyncio
import logging
import time
from collections.abc import AsyncGenerator
from dataclasses import dataclass
from typing import Any

from asgiref.sync import sync_to_async

from ..pi.bridge import stream_events
from ..pi.rpc_client import parse_context_usage
from ..services.chat import env
from ..services.chat import pool as chat_pool
from ..services.live_sessions import get_live_registry, register_live_route, unregister_live_route
from ..services.skill_service import enabled_skill_paths
from .base import BackendCapabilities, BackendError, BackendErrorKind, RunContext

logger = logging.getLogger(__name__)


#: 后端产出的一帧：``dict`` 是要转发给前端的 SSE 事件；``None`` 是「本 tick
#: 无事件」的让位信号（编排层借这个间隙把外部总线里的审批事件推进来），
#: **不转发给前端**。
#:
#: 为什么把 ``None`` 写进契约而不是用空 dict：空 dict 与「类型为未知的事件」
#: 无法区分，而 ``None`` 在类型上就表达「没有事件」。
StreamFrame = dict[str, Any] | None


@dataclass(frozen=True)
class PiRunResult:
    """一轮跑完后交回编排层的事实（不是为了产事件，而是为了收尾）。

    - ``model``：本轮实际用的模型。编排层要回写 ``AgentSession.llm_model`` 并记进
      ``AgentRun``；在 backend 里解析是因为它取决于池配置，而「解析不到 → 让 pi
      自己选」的兜底语义也属于 pi 的知识。
    - ``context_used`` / ``context_total``：轮结束、pi 关闭前取一次会话水位，供
      ``done`` 事件与 ``AgentRun`` 展示。拿不到保持 ``None``，**不编造 0**。
    """

    model: str | None
    context_used: int | None
    context_total: int | None


class PiBackend:
    """pi 运行时（每请求一个子进程，池化借用，跑完即关）。

    能力全开：pi 本身支持流式、工具调用、高危审批、自动 compaction 和运行中
    插话（steer / follow_up）。声明 ``True`` 就得真的产出对应事件——这些行为
    都由本模块与 pi extension 实际给出，不是愿望。

    一轮跑完后的事实（实际模型、上下文水位）由 ``result_for(run_id)`` 取：
    ``done`` 事件与 ``AgentRun`` 都要它，而它只有在 pi 进程关闭前才拿得到，
    异步生成器的 ``return`` 值调用方又取不到。

    **为什么不挂在 ``self.result`` 上**：注册表里存的是单例（``apps.py`` 启动时
    ``register(PiBackend())``），而 ``stream_chat`` 是并发的。实例属性会让两个
    并发会话互相覆盖对方的结果——表现为「A 会话看到 B 的模型名」或成本记到
    错误的会话上，且只在并发时才复现，极难排查。
    因此改为按 ``run_id`` 键控的字典，每轮各自独立。
    """

    kind = "pi"
    capabilities = BackendCapabilities(
        streaming=True,
        tool_calls=True,
        approval=True,
        compaction=True,
        steer=True,
    )

    #: 按 run_id 归集的收尾事实。键控而不是单值——见类 docstring
    #: 「为什么不挂在 self.result 上」。
    _results: dict[str, PiRunResult]

    def __init__(self) -> None:
        self._results = {}

    def result_for(self, run_id: str) -> PiRunResult | None:
        """取某一轮的收尾事实；未跑过 / 本轮异常时为 ``None``。"""
        return self._results.get(run_id)

    def stream(self, ctx: RunContext) -> AsyncGenerator[StreamFrame, None]:
        """借一个 pi 进程，跑完本轮，产出一轮全部 SSE 事件。

        事件体已带 ``agent="pi"`` 与 ``run_id=ctx.run_id``（``base.py`` 的事件
        契约要求）；``meta`` / ``done`` 由编排层发，这里只管中间过程。

        Args:
            ctx: 本轮输入；``user_token`` / ``prompt`` / ``model`` / ``tool_selection``
                都已由编排层准备好。

        Yields:
            ``StreamFrame``：前端 SSE 事件字典；本轮暂时无新事件时产出一个 ``None`` 作为
            「让出一个 tick」的信号（见模块 docstring 的审批插队说明）。

        Raises:
            PiNotAvailableError / PiError / PoolQueueTimeoutError: pi 侧异常原样外抛，
                由编排层翻译成中文 ``error`` 事件。
            BackendError: 非隔离运行却要求替换 system prompt；或本轮超过 ``ctx.max_turns``。

        ``ctx.isolated=True`` 时：不读写本会话的 pi 历史（池用临时目录）、不注入律师
        技能、不登记为可插话的运行中会话；审批 env 仍是真实会话。
        """
        return self._stream(ctx)

    async def _stream(self, ctx: RunContext) -> AsyncGenerator[StreamFrame, None]:
        session = ctx.session
        session_id = str(session.session_id)
        if ctx.system_prompt is not None and not ctx.isolated:
            # 常规路径的 AGENTS.md 在全局共享的配置目录里，不能为一轮改；只有隔离运行
            # 有自己的临时配置目录（见 ``PiProcessPool.acquire``）。
            raise BackendError(
                BackendErrorKind.UNAVAILABLE,
                "pi 只在隔离运行（isolated=True）时支持替换 system prompt",
            )

        pi_pool = await chat_pool.get_pool()
        # 本轮模型：``ctx.model`` 是用户逐栏显式指定的（多答时每栏可以不同），
        # 优先级高于平台默认；只有它为空才回落到 ``_resolve_model()``——
        # 回落分支逐字未变，老路径（不指定模型）行为与引入本字段前一致。
        # 不同模型不会串号：``PiProcessPool`` 是用完即毁的进程工厂（pool.py），
        # 不缓存进程，每次 acquire 都按本次传的 model 起新进程。
        #
        # ``_resolve_model()`` 的注释仍然成立：Admin 改了 LLMProvider 默认模型立即
        # 生效，且 --model 与 models.json 同源不会失配（池配置里的只是兜底）。
        model = ctx.model or await chat_pool._resolve_model()
        # 会话级 env：extension 靠 FACHUAN_SESSION_ID 把审批回调路由回本会话，
        # 靠 FACHUAN_RUN_ID 区分同会话并行的多个 agent。
        # 必须在启动 pi 之前注入，否则回调里 session_id 为空，前端收不到
        # approval_request，只能等超时走 fail-closed。
        session_env = env.session_env(session, ctx.user_id, user_token=ctx.user_token, run_id=ctx.run_id)
        # 本律师启用的技能目录（`--skill` 注入；偏好查询走同步 ORM，放线程里）。
        # 无用户身份（测试场景）时给空清单——不注入任何技能也能正常对话。
        # 隔离运行（综合结论等一次性任务）不注入：system prompt 已由调用方全量给定，
        # 律师个人技能会把与本任务无关的工作流带进来。
        if ctx.user_id is not None and not ctx.isolated:
            skill_paths = await sync_to_async(enabled_skill_paths, thread_sensitive=True)(ctx.user_id)
        else:
            skill_paths = []
        # 池满时先告知前端在排队（否则用户只能盯着转圈不知道发生了什么）。
        # 必须在 acquire 之前看：acquire 里会同步等执行位，事件发不出去。
        # 用 getattr 容错：测试与自定义池实现不一定带这两个属性。
        waiting = int(getattr(pi_pool, "waiting", 0) or 0)
        saturated = bool(getattr(pi_pool, "saturated", False))
        if waiting > 0 or saturated:
            yield {
                "type": "activity",
                "status": "queued",
                "agent": self.kind,
                "run_id": ctx.run_id,
                "position": waiting + 1,
            }

        context_used: int | None = None
        context_total: int | None = None
        # 隔离运行：池改用一次性临时目录 + 临时 pi session id（不碰本会话的 pi 历史）。
        # 只在隔离时才多传参数，常规路径的 acquire 参数与引入隔离前逐字一致。
        isolation_kwargs: dict[str, Any] = (
            {"isolated": True, "system_prompt": ctx.system_prompt} if ctx.isolated else {}
        )
        async with pi_pool.acquire(
            session_env=session_env,
            model=model,
            session_id=session_id,
            tool_selection=ctx.tool_selection,
            # 多栏并答时写类工具已从工具面摘掉（`--exclude-tools`）；单栏为 None，
            # pi 的启动参数与引入该参数前逐字一致。
            tool_exclude=ctx.tool_exclude,
            skill_paths=skill_paths,
            # 编排层按轮次分配的 key（见 ``key_scheduler``）：它会被写进本会话的
            # models.json。``None`` 时写函数仍走 ``_next_key`` 轮转（旧行为）。
            api_key=ctx.api_key,
            **isolation_kwargs,
        ) as pi_session:
            # 同时消费两个来源：pi 事件流 + 外部总线（审批请求）。
            # 不用「两个 get() task + asyncio.wait」—那个写法在 yield 让出控制权后
            # 容易丢掉已取出的事件（实测表现为只有 activity、无 delta）。
            # 改为：pi 事件流为主循环，审批事件用非阻塞轮询插队。
            stream = stream_events(pi_session, agent=self.kind)
            pending_next: asyncio.Task[dict[str, Any]] | None = None
            # 登记运行中会话：用户可在本轮跑到一半时 steer / follow_up。
            # 必须包在事件循环外面——登记后才有 prompt，否则插话会打空。
            # 隔离运行不登记：用户此刻对本会话的插话应当进 pi 那一栏，而不是综合进程。
            registry = get_live_registry()
            if not ctx.isolated:
                await registry.register(session_id, pi_session)
                # P2-3：跨 worker 路由注册（Redis 路由表）
                register_live_route(session_id, env._worker_id())
                # S47-05（2026-11-23 二轮审计）：路由 TTL 只有 120 秒且只在开跑时写一次，
                # 长对话（>2 分钟）会把路由丢掉 → 用户插话被转发到别的 worker → 「插话没生效」。
                # 下面在事件循环里按时续期（60s 一次，SET 带 EX，成本可忽略）。
                route_refresh_at = time.monotonic() + 60.0
            try:
                await pi_session.prompt(ctx.prompt)
                while True:
                    if not ctx.isolated and time.monotonic() >= route_refresh_at:
                        register_live_route(session_id, env._worker_id())
                        route_refresh_at = time.monotonic() + 60.0
                    if pending_next is None:
                        pending_next = asyncio.ensure_future(stream.__anext__())
                    await asyncio.wait({pending_next}, timeout=0.2)
                    if not pending_next.done():
                        # 这一轮暂时没有新事件：让出一个 tick，编排层借它把外部总线
                        # 里的审批事件推进来（后端不碰审批队列）。``None`` 是
                        # 「本 tick 无事件」的信号，不转发给前端。
                        #
                        # 注意 pending_next **不丢**：它还挂着一次 __anext__，下一
                        # 轮循环继续等它——这就是原实现的行为（既不重复取事件，
                        # 也不泄漏任务）。
                        yield None
                        continue
                    task, pending_next = pending_next, None
                    try:
                        event = task.result()
                    except StopAsyncIteration:
                        break
                    # pi 没有 max-turns 开关：按 ``turn_start`` 计数，超限就 abort 并报错。
                    # 超限的结论不可信（循环被掐断在半路），不能当正常结束。
                    if ctx.max_turns is not None and int(getattr(pi_session, "turns_started", 0) or 0) > ctx.max_turns:
                        await pi_session.abort()
                        raise BackendError(
                            BackendErrorKind.UNKNOWN,
                            f"pi 本轮超过 {ctx.max_turns} 轮模型循环上限，已中止",
                        )
                    # 统一补 ``agent`` / ``run_id``：两个 agent 同题并行时，前端靠
                    # 这两个字段把交错的事件分流到不同栏。
                    event = {**event, "agent": self.kind, "run_id": ctx.run_id}
                    if event.get("type") == "settled":
                        # **收尾事实必须在生成器结束前就位**，否则
                        # ``backend.result_for(run_id)`` 永远是 None，模型名与
                        # 上下文水位永远拿不到（症状：``/stats`` 的
                        # ``context_used_tokens`` 恒 null、分栏水位条从不亮）。
                        #
                        # ``settled`` 是 bridge 在 pi 的 ``agent_settled`` 处发的
                        # **内部标记**，不是线路事件：**不转发**。线上只能有一条
                        # ``done``，由编排层（``stream.py``）统一发——那里才知道
                        # 落库主键与会话级水位。两个都发会让前端收到两条 done，
                        # 多栏下还会把「每栏各一条」的计数打乱。
                        #
                        # 这一步仍在 ``async with`` 内：pi 进程还活着，stats 才拿得到。
                        try:
                            context_used, context_total = parse_context_usage(await pi_session.get_session_stats())
                        except Exception:
                            logger.warning("会话上下文水位获取失败（不影响对话）", exc_info=True)
                        self._results[ctx.run_id] = PiRunResult(
                            model=model, context_used=context_used, context_total=context_total
                        )
                        break
                    yield event
                    if event.get("type") == "done":
                        break
            finally:
                if not ctx.isolated:
                    await registry.unregister(session_id, pi_session)
                    unregister_live_route(session_id)
                if pending_next is not None:
                    # 提前退出（done / 取消）时可能还挂着一次 __anext__，必须收掉，
                    # 否则任务泄漏并在事件循环关闭时刷 "Task was destroyed" 警告。
                    pending_next.cancel()

        # 正常路径已在 done 分支里写过 result；这里只覆盖「事件流自然结束但没发
        # done」的截断路径（协议要求实现方显式发 done，真发生了也不编造水位）。
        if ctx.run_id not in self._results:
            self._results[ctx.run_id] = PiRunResult(model=model, context_used=context_used, context_total=context_total)
