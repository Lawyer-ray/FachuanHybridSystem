"""stream_dual —— 同一个问题同时问两个 agent，两边的回答都给律师看。

## 为什么不是「跑两次 stream_chat」

``stream_chat`` 是**整轮**编排：落用户消息、推标题、写 ``AgentRun``、入队记忆
抽取、发 ``done``。跑两次就会得到两个 ``done``、两条用户消息、双份运行记录，
前端与审计都得改造才能容忍重复。本模块把「同一轮共用的事实」留在这里做一次，
把「每个后端各自的事实」交给 ``stream_chat``：

    stream_dual
      ├─ record_user_message / bus.register       ← 一次
      ├─ asyncio.gather(stream_chat(主), stream_chat(次))  ← 并发
      └─ bus.unregister + 唯一一个 done            ← 一次

两个 ``stream_chat`` 各自照常写 ``AgentRun``（成本必须分别归因到各自的模型）与
自己的助手消息（带 ``agent_kind``）。它们各自的 ``done`` 在这里被**吞掉**，
两边都结束后由本模块补发唯一一个。

## 谁跑主、谁跑次

会话自己的 ``agent_kind`` 是主（沿用会话选定的后端），注册表里第一个不等于主
的 kind 是次。顺序由 ``available_kinds()`` 给定，本模块不另排一次。

## 失败矩阵（本模块的核心设计）

| 情况 | 事件 | 收尾 |
|:--|:--|:--|
| 两个都成功 | 各自完整的事件流（带 ``agent`` / ``run_id``） | 一个 ``done`` |
| 一成一败 | 成功的照常输出；失败方**只**发一条带 ``agent`` 的 ``error`` | 一个 ``done`` |
| 两个都失败 | 只发**第一条** ``error``（不堆两条） | 一个 ``done`` |
| 辅助配额已满 | 只跑主后端 + 一条 ``activity{status:"degraded", reason}`` | 一个 ``done`` |

关键取舍：**一个后端坏了不能把另一个也拖下水**。律师要的是「至少有一个答案」，
所以每个后端的事件流被单独包住，异常就地转成一条 ``error``，另一个继续转发。
也因此不用 ``gather(return_exceptions=False)``——那个会让第一个异常把整轮打死。

两个都失败时为什么只发一条：两条 ``error`` 在同一个气泡区渲染成两行，读起来
像「同一件事失败了两遍」。第一条已足够表达「本轮没跑成」，另一半的原因进日志与
它自己的 ``AgentRun.error_kind``（查用量时才看，不干扰主界面）。

## 落库

主后端那一半走 ``stream_chat`` 的常规落库；次后端那一半用
``persist_assistant=False`` 把正文交回这里（``StreamMemo``），由本模块带着
``agent_kind`` 落库——否则次答在历史回放里会凭空消失，律师第二天再看只剩一份。
"""

from __future__ import annotations

import asyncio
import logging
from collections.abc import AsyncIterator
from dataclasses import dataclass, field
from typing import Any

from ...backends import available_kinds
from ...backends.builtin import ensure_registered
from ...models import AgentMessage, AgentSession
from ..event_bus import get_bus
from . import budget
from .stream import record_user_message, stream_chat

logger = logging.getLogger(__name__)

#: 配额不足时告知前端的 ``activity.status``。用**单独一个状态值**而不是
#: ``error``：主后端照常给出了答案，本轮是成功的，只是少了一栏对比。
ACTIVITY_DEGRADED = "degraded"


@dataclass
class StreamMemo:
    """一个后端那一半「交给外部收尾」的事实（正文 / 运行 id / metadata）。

    为什么需要可变容器：``stream_chat`` 是异步生成器，它的 ``return`` 值调用方
    拿不到（见 ``persist.py`` 对 ``result_for`` 的同款说明）。次答的正文必须先
    交回本模块，才能在落库时带上 ``agent_kind``。

    ``run_id`` 由 ``stream_chat`` 在取到后端后写入：事件里的 ``run_id`` 也在那里
    拼（见 ``stream.py``），本模块不重复推导——两处拼法一漂移，前端就按错误的
    键分栏。
    """

    parts: list[str] = field(default_factory=list)
    run_id: str = ""
    metadata: dict[str, Any] = field(default_factory=dict)


def pick_secondary(session: AgentSession) -> str | None:
    """挑本轮「次答」的后端 kind；没有可配对的返回 ``None``。

    主后端是会话自己选的那个（未设置时为 pi）。次后端取注册表里**第一个不等于
    主**的 kind。返回 ``None`` 表示这个部署只有一个后端在跑，双答无从谈起，
    调用方应退回单后端路径——那不是错误，「一个答案」仍比「一句报错」有用。
    """
    primary = _primary_kind(session)
    for kind in available_kinds():
        if kind != primary:
            return kind
    return None


def _primary_kind(session: AgentSession) -> str:
    """会话主后端 kind（未设置 / 未识别时回落 pi，与 ``stream_chat`` 同口径）。"""
    return getattr(session, "agent_kind", "") or "pi"


def _tag(event: dict[str, Any], agent: str, memo: StreamMemo) -> dict[str, Any]:
    """确保事件带 ``agent``；缺 ``run_id`` 时用本轮已确定的那个补上。

    两条路径对这两个字段的补齐口径不同（后端在中间事件上补、``stream_chat`` 只在
    ``meta`` / ``activity`` 上补），前端却要按它们无条件分流——所以在合并边界
    统一口径，而不是让前端猜「哪种事件可能没有 agent」。
    """
    tagged = dict(event)
    tagged.setdefault("agent", agent)
    if memo.run_id and not tagged.get("run_id"):
        tagged["run_id"] = memo.run_id
    return tagged


async def _pump_secondary(
    *,
    session: AgentSession,
    user_message: str,
    user_id: int | None,
    tool_selection: str | None,
    secondary_kind: str,
    memo: StreamMemo,
    queue: asyncio.Queue[dict[str, Any] | None],
) -> None:
    """次答：包住 aux 配额，事件进队列，结束时放一个 ``None`` 让消费者收尾。

    ``budget.reserve`` 必须在**整个流**期间持有：它是准入计数，提前释放等于
    允许第三个对比请求在第一个还没跑完时就进来。

    ``BudgetExceeded`` 不在这里转成 ``error``：配额是**降级**（少一栏对比），
    不是失败。它由调用方在消费侧识别并发 ``degraded`` 事件。
    """
    try:
        async with budget.reserve("aux"):
            async for event in stream_chat(
                session=session,
                user_message=user_message,
                user_id=user_id,
                tool_selection=tool_selection,
                # 用户消息已由 stream_dual 落库一次（两个后端共用同一条提问）
                user_message_recorded=True,
                # 正文交回本模块落库：只有这里知道该带哪个 agent_kind
                persist_assistant=False,
                memo=memo,
                # 关键：不能落到会话自己的 agent_kind，否则两次调用都取主后端
                agent_kind=secondary_kind,
            ):
                if event.get("type") == "done":
                    continue  # done 由 stream_dual 统一发，见模块 docstring
                await queue.put(event)
    except (GeneratorExit, asyncio.CancelledError):
        raise
    except budget.BudgetExceeded:
        raise
    except Exception:
        logger.exception("双答：次答这一轮失败 session=%s", session.session_id)
        await queue.put(_backend_error("", "该 agent 本轮运行失败，另一个回答不受影响（详见服务端日志）"))
    finally:
        await queue.put(None)


def _backend_error(agent: str, message: str) -> dict[str, Any]:
    """失败方唯一的一条 ``error``（带 ``agent``，前端据此挂到对应栏）。"""
    return {"type": "error", "message": message, "agent": agent}


async def _persist_secondary(session: AgentSession, agent: str, memo: StreamMemo) -> None:
    """落库次答正文（带 ``agent_kind``）；失败只记日志，不影响已经流出的回答。"""
    text = "".join(memo.parts).strip()
    if not text:
        return
    metadata = dict(memo.metadata)
    metadata.setdefault("model", "")
    try:
        await AgentMessage.objects.acreate(
            session=session,
            role=AgentMessage.Role.ASSISTANT,
            content=text,
            metadata=metadata,
            agent_kind=agent,
        )
    except Exception:
        logger.warning("双答：次答正文落库失败 session=%s agent=%s", session.session_id, agent, exc_info=True)


async def stream_dual(
    *,
    session: AgentSession,
    user_message: str,
    user_id: int | None = None,
    tool_selection: str | None = None,
) -> AsyncIterator[dict[str, Any]]:
    """同时问两个 agent，产出合并后的 SSE 事件流。

    事件按到达顺序交错产出，前端靠 ``agent`` / ``run_id`` 把每个事件分流到各自
    的栏（契约见 ``sse_types.py``）。除转发外本函数负责：

    - 流开头声明本轮参与方：``meta{agents}`` / ``activity{thinking, agents}``；
    - 配额不足时发 ``activity{status:"degraded", reason}`` 并退回只跑主后端；
    - 失败矩阵（模块 docstring）与**唯一一个** ``done``（带 ``agents`` 清单）。

    客户端断开时原样上抛 ``GeneratorExit`` / ``CancelledError``（按停止不是错误）。
    """
    ensure_registered()

    session_id = str(session.session_id)
    primary_kind = _primary_kind(session)
    secondary_kind = pick_secondary(session)

    if secondary_kind is None:
        async for event in stream_chat(
            session=session, user_message=user_message, user_id=user_id, tool_selection=tool_selection
        ):
            yield event
        return

    # 用户消息与标题只写一次：两个后端跑的是同一条提问，各写一次会让回放里出现
    # 两个一模一样的提问。
    await record_user_message(session, user_message)
    # 事件总线也只订阅一次：``stream_chat`` 订阅的是「本轮会话的外部事件」
    # （审批等），两次订阅会让一条审批只被其中一个消费、另一个永远收不到。
    bus = get_bus()
    external_queue = await bus.register(session_id)

    primary_memo = StreamMemo()
    secondary_memo = StreamMemo()
    secondary_events: asyncio.Queue[dict[str, Any] | None] = asyncio.Queue()

    agents = [primary_kind, secondary_kind]
    # 失败矩阵的状态：两个都失败时只转发第一条 error（见模块 docstring）
    errors: list[dict[str, Any]] = []
    primary_ok = True
    secondary_ok = True
    secondary_task: asyncio.Task[None] | None = None

    try:
        yield {"type": "meta", "session_id": session_id, "agent": primary_kind, "agents": agents}
        yield {"type": "activity", "status": "thinking", "agent": primary_kind, "agents": agents}

        # ── 次要后端：先抢 aux 配额，抢不到就降级 ──────────────────────
        # 用「试进即出」而不是把整个流包在 reserve 里：降级必须在发出任何次答
        # 事件之前就决定，而 reserve 的持有期要覆盖整个流（见 _pump_secondary
        # 里的第二次 reserve）。两次 reserve 之间有一瞬空隙，但那个空隙里 aux
        # 计数刚被我们减掉、随即又被自己加回，其他请求占位只会让第二次 reserve
        # 抛 BudgetExceeded —— 结果仍是降级，语义安全。
        aux_allowed = await _aux_available()
        if aux_allowed:
            secondary_task = asyncio.create_task(
                _pump_secondary(
                    session=session,
                    user_message=user_message,
                    user_id=user_id,
                    tool_selection=tool_selection,
                    secondary_kind=secondary_kind,
                    memo=secondary_memo,
                    queue=secondary_events,
                )
            )
        else:
            logger.info("双答降级为只跑主答 session=%s（aux 席位已满或关闭）", session_id)
            yield {
                "type": "activity",
                "status": ACTIVITY_DEGRADED,
                "agent": primary_kind,
                "reason": "对比执行位已满，本轮只跑了主后端",
            }

        # ── 主答：直接在此协程里迭代（它的异常要能原样上抛取消语义） ────
        try:
            async for event in stream_chat(
                session=session,
                user_message=user_message,
                user_id=user_id,
                tool_selection=tool_selection,
                user_message_recorded=True,
                memo=primary_memo,
            ):
                if event.get("type") == "done":
                    continue  # done 由本模块统一发
                tagged = _tag(event, primary_kind, primary_memo)
                if tagged.get("type") == "error":
                    errors.append(tagged)
                    if len(errors) > 1:
                        continue  # 两个都失败：只发第一条，不堆两条
                yield tagged
                # 借主答事件的间隙把外部总线（审批）里的事件推进来：审批不走
                # 后端事件流，见 pi_backend 模块说明。
                while True:
                    try:
                        yield external_queue.get_nowait()
                    except asyncio.QueueEmpty:
                        break
        except (GeneratorExit, asyncio.CancelledError):
            raise
        except Exception:
            # 主答的异常同样只降级成本栏的错误，不吞掉次答（失败矩阵第 2 条）
            primary_ok = False
            logger.exception("双答：主答这一轮失败 session=%s", session_id)
            errors.append(_backend_error(primary_kind, "主后端本轮运行失败，另一个回答不受影响"))
            if len(errors) == 1:
                yield errors[0]

        # ── 次答事件：主答跑完后把所有剩余事件转发给前端 ─────────────────
        if secondary_task is not None:
            while True:
                event = await secondary_events.get()
                if event is None:
                    break
                tagged = _tag(event, secondary_kind, secondary_memo)
                if tagged.get("type") == "error":
                    errors.append(tagged)
                    if len(errors) > 1:
                        continue
                yield tagged
            # 等任务收尾：BudgetExceeded 在这里被 _pump_secondary 原样上抛
            outcome = await asyncio.gather(secondary_task, return_exceptions=True)
            if outcome and isinstance(outcome[0], budget.BudgetExceeded):
                secondary_ok = False
                logger.info("双答降级为只跑主答 session=%s（进入时 aux 席位已被占）", session_id)
                yield {
                    "type": "activity",
                    "status": ACTIVITY_DEGRADED,
                    "agent": primary_kind,
                    "reason": "对比执行位已满，本轮只跑了主后端",
                }
            else:
                await _persist_secondary(session, secondary_kind, secondary_memo)
    finally:
        # 提前退出（客户端断开）时把仍在跑的后端停掉：``stream_chat`` 内部靠
        # finally 把已流出的部分落库，取消它就是「用户按停止」的语义。
        if secondary_task is not None and not secondary_task.done():
            secondary_task.cancel()
        # finally 里**不能 yield**（GeneratorExit 路径上会抛 RuntimeError，
        # 表现为 SSE 被截断），收尾只做 await。
        await bus.unregister(session_id, external_queue)

    if not primary_ok and not secondary_ok:
        logger.warning("双答：两个后端都失败 session=%s", session_id)
    yield {"type": "done", "session_id": session_id, "agent": primary_kind, "agents": agents}


async def _aux_available() -> bool:
    """预检 aux 席位：能进就立刻退（真正的长时间持有在 ``_pump_secondary``）。

    单独一个函数是为了把「降级判定」写成可读的一步。判定逻辑与 ``reserve``
    同源（都走 ``budget``），不复制阈值——否则环境变量改了之后两处判断分叉，
    表现是「预检说可以，真跑却抛 BudgetExceeded」。
    """
    try:
        async with budget.reserve("aux"):
            return True
    except budget.BudgetExceeded:
        return False


__all__ = ["ACTIVITY_DEGRADED", "StreamMemo", "pick_secondary", "stream_dual"]
