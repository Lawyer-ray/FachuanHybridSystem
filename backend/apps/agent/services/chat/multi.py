"""stream_multi —— 同一个问题同时问 N 个 agent，所有回答都给律师看。

本模块是 v27.19 的 ``stream_dual`` 的**泛化版**（原来写死两个）。改名的原因：
「dual」这个词把 N 锁在了 2，未来加第 4、5 个 agent 时字面上就在对抗代码。

## 为什么不是「跑 N 次 stream_chat」

``stream_chat`` 是**整轮**编排：落用户消息、推标题、写 ``AgentRun``、入队记忆
抽取、发 ``done``。跑 N 次就会得到 N 个 ``done``、N 条用户消息、N 份运行记录，
前端与审计都得改造才能容忍重复。本模块把「同一轮共用的事实」留在这里做一次，
把「每个后端各自的事实」交给 ``stream_chat``：

    stream_multi
      ├─ record_user_message / bus.register        ← 一次
      ├─ N 个 stream_chat 并发（首个在此协程，其余走队列）
      └─ bus.unregister + 每栏一个 done             ← 收尾

每个 ``stream_chat`` 各自照常写 ``AgentRun``（成本必须分别归因到各自的模型）与
自己的助手消息（带 ``agent_kind``）。它们各自的 ``done`` 在这里被**吞掉**，
全部结束后由本模块按栏补发。

## 谁跑主、谁跑次

调用方显式给 ``kinds``（API 层解析 ``agents`` 字段）。不给时退回「会话自己的
``agent_kind`` 是主，注册表里第一个不等于主的 kind 是次」——与旧 ``stream_dual``
同口径，保证 ``dual=True`` 的旧前端行为不变。

**首个 kind 在调用方协程里直接迭代，其余全部走队列**。这不是随意选择：首个
（主答）的异常必须能原样上抛成取消语义，否则客户端断开时停不下来；其余的回答
失败只降级成本栏的 ``error``，不能把主答拖下水。

## 失败矩阵（本模块的核心设计）

| 情况 | 事件 | 收尾 |
|:--|:--|:--|
| 全部成功 | 各自完整的事件流（带 ``agent`` / ``run_id``） | **每栏一个** ``done`` |
| 部分失败 | 成功的照常输出；失败方**只**发一条带 ``agent`` 的 ``error`` | **每栏一个** ``done`` |
| 全部失败 | 只发**第一条** ``error``（不堆 N 条） | **每栏一个** ``done`` |
| 辅助配额已满 | 只跑主后端 + 一条 ``activity{status:"degraded", reason}`` | 一个 ``done``（agents 收窄为单栏） |

关于 ``done`` 的条数（2026-11-19 修正，教训保留在此）：早先的设计是「整轮只发
一个 done」，理由是「两个 done 会让前端在第一栏结束时收尾」。**那个理由站不住**
——前端 ``onDone`` 的契约就是「这个 done 属于哪个 agent，就收哪一栏」，只发一个
反而让其余栏永远收不了尾，界面上全是「(无内容)」。真实事故即由此而来，故改为
按栏发，字段与单后端路径同形。

关键取舍：**一个后端坏了不能把其他也拖下水**。律师要的是「至少有一个答案」，
所以每个后端的事件流被单独包住，异常就地转成一条 ``error``，其余继续转发。
也因此不用 ``gather(return_exceptions=False)``——那个会让第一个异常把整轮打死。

全部失败时为什么只发一条：N 条 ``error`` 在同一个气泡区渲染成 N 行，读起来像
「同一件事失败了 N 遍」。第一条已足够表达「本轮没跑成」，另一半的原因进日志与
它自己的 ``AgentRun.error_kind``（查用量时才看，不干扰主界面）。

## 落库

主后端那一半走 ``stream_chat`` 的常规落库；其余那一半用
``persist_assistant=False`` 把正文交回这里（``StreamMemo``），由本模块带着
``agent_kind`` 落库——否则次答在历史回放里会凭空消失，律师第二天再看只剩一份。

## 并发上限

``MAX_ANSWERS = 4``。理由是成本线性增长且四栏并排在 UI 上已接近可读性极限，
不是技术限制——``_pump_one`` 对 N 没有假设，调高这个常量即可。

## 轮次级 key 分配

网关对**每把 key** 限 3 并发（实测 429 + ``retry-after: 60``，那一栏表现为
「卡住 60 秒」）。后端自己的 ``_next_key`` 是全局轮转计数，**不保证**同一轮的
N 栏落在不同 key 上，也不知道哪把已经满了。所以分配在这里做一次：开流前从
``LLMProvider.api_keys`` 取出 key 池，由 ``key_scheduler.allocate`` 给**每一栏
各分一把互不相同**的 key，经 ``RunContext.api_key`` 传给后端。

归还的规则是「谁用谁还」：主答在自己的 ``finally`` 归还，非主答在 ``_pump_one``
的 ``finally`` 归还，整轮另挂一层兜底（被 cancel 后没再被调度到的栏跑不到
``finally``，而漏还一把 key 的代价是那一路并发额度永久少 1 → 越来越容易 429）。
拿不到 key 池（没有 provider / 读配置失败）时**不报错**，传 ``None`` 让后端走
它原来的轮转口径——与引入 key 分配前逐字一致。
"""

from __future__ import annotations

import asyncio
import logging
from collections.abc import AsyncIterator, Mapping, Sequence
from contextlib import AsyncExitStack, asynccontextmanager
from dataclasses import dataclass, field
from typing import Any

from ...backends import available_kinds
from ...backends.builtin import ensure_registered
from ...backends.gateway_cache import load_api_keys
from ...backends.key_scheduler import KeyLease, get_key_scheduler
from ...models import AgentMessage, AgentSession
from ..event_bus import get_bus
from . import budget, profile
from .stream import ContextPrep, prepare_context, record_user_message, stream_chat

logger = logging.getLogger(__name__)

#: 配额不足时告知前端的 ``activity.status``。用**单独一个状态值**而不是
#: ``error``：主后端照常给出了答案，本轮是成功的，只是少了几栏对比。
ACTIVITY_DEGRADED = "degraded"

#: 一轮最多同时问几个 agent。超出的由 API 层挡掉（400），本模块不静默截断——
#: 静默截断会让用户以为选中的都跑了，实际少跑了几个还看不出来。
MAX_ANSWERS = 4


@dataclass(frozen=True)
class AgentSpec:
    """本轮一个参与方：哪个后端 + 用哪个模型。

    ``model`` 为空 = 用平台默认模型（与引入本字段前行为一致）。多答的核心价值
    就是「同题不同模型」的对比，所以模型必须跟着参与方走，而不是会话级属性。
    """

    kind: str
    #: 空/None = 由后端按自身默认策略选（``pi`` 回落 ``_resolve_model()``）。
    model: str | None = None


def normalize_agents(raw: Sequence[Any] | None) -> list[AgentSpec]:
    """把三种形态的「本轮参与方」输入归一成 ``AgentSpec`` 列表。

    接受的形态（可混用）：

    - 纯字符串 kind —— 老前端的口径，等价于「只有 kind、模型走平台默认」；
    - 字典 ``{"kind": ..., "model": ...}`` —— JSON 请求体的自然形态（Ninja 把
      ``AgentSpecIn`` 解析成 dict 还是 schema 对象取决于版本，两种都认）；
    - ``AgentSpec`` 实例——服务层调用方直接给的对象。

    兼容老客户端的口径与 ``resolve_kinds`` 一致：空 kind 丢弃、空列表视同 ``None``、
    同一 kind 只跑一次（保留**第一个**，即先出现的那栏的模型）——同一 kind 跑两遍
    既花双倍钱，又会让两栏共用同一个 ``run_id`` 前缀而串栏。

    未知 kind 不在这里拒绝：交给 ``stream_chat`` 抛 ``LookupError``，由失败矩阵
    降级成该栏的 ``error``——那样其他栏照常出答案，而这里拒绝会整轮不通。

    Args:
        raw: 参与方清单；``None`` / 空列表返回空列表（由调用方回落到「主 + 次」）。

    Returns:
        去重后的 ``AgentSpec`` 列表（顺序按首次出现）。
    """
    specs: list[AgentSpec] = []
    seen: set[str] = set()
    for item in raw or []:
        spec = _as_agent_spec(item)
        if spec is None or not spec.kind or spec.kind in seen:
            continue
        seen.add(spec.kind)
        specs.append(spec)
    return specs


def _as_agent_spec(item: Any) -> AgentSpec | None:
    """单个参与方归一成 ``AgentSpec``；认不出形态就返回 ``None``（由调用方丢弃）。"""
    if isinstance(item, AgentSpec):
        return item
    if isinstance(item, str):
        return AgentSpec(kind=item.strip())
    if isinstance(item, Mapping):
        kind = str(item.get("kind") or "").strip()
        model = item.get("model")
        return AgentSpec(kind=kind, model=_clean_model(model))
    # 其它对象的自然形态（``AgentSpecIn`` 实例 / 带同名属性的 DTO）
    kind = str(getattr(item, "kind", "") or "").strip()
    if not kind:
        return None
    return AgentSpec(kind=kind, model=_clean_model(getattr(item, "model", None)))


def _clean_model(model: Any) -> str | None:
    """模型名的规范化：空白串视同未指定（``""`` 会让 pi 的 ``--model`` 报错）。"""
    name = str(model or "").strip()
    return name or None


@dataclass
class StreamMemo:
    """一个后端那一半「交给外部收尾」的事实（正文 / 运行 id / metadata）。

    为什么需要可变容器：``stream_chat`` 是异步生成器，它的 ``return`` 值调用方
    拿不到（见 ``persist.py`` 对 ``result_for`` 的同款说明）。非主答的正文必须先
    交回本模块，才能在落库时带上 ``agent_kind``。

    ``run_id`` 由 ``stream_chat`` 在取到后端后写入：事件里的 ``run_id`` 也在那里
    拼（见 ``stream.py``），本模块不重复推导——两处拼法一漂移，前端就按错误的
    键分栏。
    """

    parts: list[str] = field(default_factory=list)
    run_id: str = ""
    metadata: dict[str, Any] = field(default_factory=dict)


def primary_kind(session: AgentSession) -> str:
    """会话主后端 kind（未设置 / 未识别时回落 pi，与 ``stream_chat`` 同口径）。"""
    return getattr(session, "agent_kind", "") or "pi"


def pick_secondary(session: AgentSession) -> str | None:
    """挑本轮「次答」的后端 kind；没有可配对的返回 ``None``。

    保留这个函数是为了 ``dual=True`` 的旧前端契约（两个 agent 同题并答）：
    主后端是会话自己选的那个（未设置时为 pi），次后端取注册表里**第一个不等于
    主**的 kind。返回 ``None`` 表示这个部署只有一个后端在跑，双答无从谈起，
    调用方应退回单后端路径——那不是错误，「一个答案」仍比「一句报错」有用。

    想要三个以上时请直接用 ``stream_multi(kinds=[...])``，不要在这里加逻辑。
    """
    primary = primary_kind(session)
    for kind in available_kinds():
        if kind != primary:
            return kind
    return None


def resolve_specs(
    session: AgentSession,
    specs: Sequence[AgentSpec] | None = None,
    kinds: Sequence[str] | None = None,
) -> list[AgentSpec]:
    """确定本轮参与方（含每栏模型）：显式 ``specs`` > ``kinds`` > 「主 + 次」。

    ``kinds`` 是引入逐栏模型前的旧入口（``stream_multi(kinds=[...])`` 与
    ``stream_dual``）：它不知道模型，所以转成 ``AgentSpec(kind, None)``（= 走平台
    默认）。两处都给时 ``specs`` 优先——显式 >= 隐式。

    空列表视同 ``None``（前端传 ``[]`` 与不传同义）；去重与回落规则分别见
    ``normalize_agents`` / ``resolve_kinds``。
    """
    explicit = normalize_agents(specs)
    if explicit:
        return explicit
    return [AgentSpec(kind=kind) for kind in resolve_kinds(session, kinds)]


def resolve_kinds(session: AgentSession, kinds: Sequence[str] | None) -> list[str]:
    """确定本轮参与方：显式 ``kinds`` 优先，否则退回「主 + 次」。

    - 去重（同一 kind 问两遍没有意义，还会让两栏共用 ``run_id`` 前缀而串栏）
    - 空列表视同 ``None``（前端传 ``[]`` 与不传同义）
    - 不做存在性校验：未知 kind 交给 ``stream_chat`` 抛 ``LookupError``，
      由失败矩阵降级成该栏的 ``error``——这比在这里因为它一个人就把整轮拒掉好
    """
    chosen = [k for k in dict.fromkeys(kinds or []) if k]
    if chosen:
        return chosen
    primary = primary_kind(session)
    secondary = pick_secondary(session)
    return [primary, secondary] if secondary else [primary]


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


def _backend_error(agent: str, message: str) -> dict[str, Any]:
    """失败方唯一的一条 ``error``（带 ``agent``，前端据此挂到对应栏）。"""
    return {"type": "error", "message": message, "agent": agent}


async def _round_api_keys(model_hint: str | None, *, session_id: str) -> tuple[str, ...]:
    """本轮的 key 池；拿不到时返回空元组（各栏退回后端自己的轮转）。

    实现已提到 :func:`gateway_cache.load_api_keys` —— 压缩上下文
    （``services/compact_service``）也要用同一份口径，两处各写一遍会漂移。
    """
    return await load_api_keys(model_hint)


def _lease_key(lease: KeyLease) -> str | None:
    """租约 → ``RunContext.api_key`` 的取值。

    空串（没有任何 key 可分配）转成 ``None``：两者对后端的含义不同——``None``
    是「你自己轮转」，空串会被当成「这就是本轮指定的那把」直接发出去。
    """
    return lease.key or None


async def _allocate_round_leases(
    *, kinds: Sequence[str], model_hint: str | None, session_id: str
) -> dict[str, KeyLease]:
    """给本轮每一栏各分一把 key（互不相同），返回 ``kind -> 租约``。

    调用时机是「参与方已定、各栏还没启动」：早于它分不出要几把；晚于它，主答
    已经开始跑，那一栏就只能捡后端自己的轮转。

    分配本身在 ``key_scheduler`` 里已兜底（key 不够时循环复用、全部饱和时
    best-effort + WARNING，永不报错），所以这里不重复判空。
    """
    async with profile.timed("multi.allocate_keys", session=session_id):
        keys = await _round_api_keys(model_hint, session_id=session_id)
        leases = get_key_scheduler().allocate(keys, len(kinds))
    # 只打指纹（``KeyLease.label`` 走 ``fingerprint``）：明文 key 不得进日志。
    logger.info(
        "多答：本轮 key 分配 session=%s 栏数=%d keys=%s",
        session_id,
        len(kinds),
        [lease.label for lease in leases],
    )
    return dict(zip(kinds, leases, strict=True))


async def _persist_answer(session: AgentSession, agent: str, memo: StreamMemo) -> None:
    """落库非主答正文（带 ``agent_kind``）；失败只记日志，不影响已流出的回答。"""
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
        logger.warning("多答：非主答正文落库失败 session=%s agent=%s", session.session_id, agent, exc_info=True)


async def _pump_one(
    *,
    session: AgentSession,
    user_message: str,
    user_id: int | None,
    tool_selection: str | None,
    agent_kind: str,
    model: str | None,
    lease: KeyLease,
    memo: StreamMemo,
    queue: asyncio.Queue[dict[str, Any] | None],
    context: ContextPrep | None,
) -> None:
    """一个非主答后端：事件进队列，结束时放一个 ``None`` 收尾。

    ``lease`` 是这一栏自己的 key 租约：**本函数负责归还**（在 ``finally`` 里，
    异常与取消路径同样跑）。漏还一把 key 的代价是那一路并发额度永久少 1，
    之后越来越容易 429，而且没有任何报错。

    ## aux 席位为什么由调用方统一持（而不是这里各抢一个）

    实测：``aux_slots() = 总席位(4) × 0.25 = 1``。若每个非主答各自
    ``reserve("aux")``，三栏时第二、三个必然被挡——界面上「选了三个只出两个」，
    且被挡的那栏连一句原因都没有。**这个坑真踩过**：v27.20 的三栏用例实测
    ``third-agent outcome=[BudgetExceeded('辅助 agent 并发已满（1/1）')]``。

    语义上也站不住：``aux`` 闸门防的是「一个用户同时开太多对比请求」，而同一轮
    的 N 栏是**同一个人的一次请求**，当成 N 个独立请求去抢闸是错的。

    所以席位由 ``stream_multi`` 在整轮外面持有一个（见 ``_hold_aux``），本函数
    只管跑。``BudgetExceeded`` 不再可能从这里冒出来。

    ``CancelledError`` 原样上抛：客户端断开时这是「按停止」的语义，不是失败。
    """
    try:
        async for event in stream_chat(
            session=session,
            user_message=user_message,
            user_id=user_id,
            tool_selection=tool_selection,
            # 用户消息已由 stream_multi 落库一次（N 个后端共用同一条提问）
            user_message_recorded=True,
            # 正文交回本模块落库：只有这里知道该带哪个 agent_kind
            persist_assistant=False,
            memo=memo,
            # 凭证与 prompt 已由 stream_multi 算好：N 栏同一个律师、同一条提问，
            # 每栏各铸一次只是把同一条 user 查询排队 N 遍（见 ContextPrep）
            context=context,
            # 关键：不能落到会话自己的 agent_kind，否则每次调用都取主后端
            agent_kind=agent_kind,
            # 这一栏自己的模型（None = 平台默认）。不传的话三栏会全部落到
            # 平台默认，界面上「三栏三模型」实际是三栏同模型，且没有任何报错。
            model=model,
            # 这一栏自己的 key（None = 后端自己轮转）：三栏抢同一把会撞上
            # 网关每 key 3 并发的限流，表现为「某一栏卡 60 秒」。
            api_key=_lease_key(lease),
        ):
            if event.get("type") == "done":
                continue  # done 由 stream_multi 按栏统一发，见模块 docstring
            await queue.put(event)
    except (GeneratorExit, asyncio.CancelledError):
        raise
    except Exception:
        logger.exception("多答：agent=%s 这一轮失败 session=%s", agent_kind, session.session_id)
        # agent 留空由调用方补（这里拿不到调用方统一后的写法）
        await queue.put(_backend_error("", "该 agent 本轮运行失败，其他回答不受影响（详见服务端日志）"))
    finally:
        # 先还 key 再收尾：归还只是字典计数，不会被打断；而漏还的代价是永久的。
        lease.release()
        await queue.put(None)


@asynccontextmanager
async def _hold_aux() -> AsyncIterator[bool]:
    """整轮持有**一个** aux 席位；抢不到就 ``yield False``（不抛）。

    为什么是「整轮一个」而不是「每栏一个」：实测默认配置
    ``aux_slots() = 总席位(4) × 0.25 = 1``。若每栏各抢一个，三栏时后两栏必然
    被挡，界面上「选了三个只出两个」且被挡的栏连原因都看不到（真踩过）。

    语义上也站不住：``aux`` 闸门防的是「一个用户同时开太多对比请求」，而同一轮
    的 N 栏是**同一个人的一次请求**，当成 N 个独立请求去抢闸是错的。

    为什么用上下文管理器而不是「试进即出再真进」：那种写法在两段之间有一瞬
    空隙，别的请求可以插进来把席位占走，于是预检说可以、真跑却降级——现象是
    「有时能跑三条，有时只能跑两条」的随机行为。一次持有到位。
    """
    try:
        async with budget.reserve("aux"):
            yield True
    except budget.BudgetExceeded:
        yield False


async def stream_multi(
    *,
    session: AgentSession,
    user_message: str,
    user_id: int | None = None,
    tool_selection: str | None = None,
    specs: Sequence[AgentSpec] | None = None,
    kinds: Sequence[str] | None = None,
) -> AsyncIterator[dict[str, Any]]:
    """同时问 N 个 agent，产出合并后的 SSE 事件流。

    事件按到达顺序交错产出，前端靠 ``agent`` / ``run_id`` 把每个事件分流到各自
    的栏（契约见 ``sse_types.py``）。除转发外本函数负责：

    - 流开头声明本轮参与方：``meta{agents}`` / ``activity{thinking, agents}``；
    - 配额不足时发 ``activity{status:"degraded", reason}`` 并退回只跑主后端；
    - 失败矩阵（模块 docstring）与**每栏一个** ``done``（带 ``agents`` 清单）。

    只有一个 kind 时直接透传 ``stream_chat``（不重复落库、不发两次 done）。

    Args:
        specs: 本轮参与方及其模型（``normalize_agents`` 的产物）。
        kinds: 旧入口（只有 kind，模型走平台默认）；给 ``specs`` 时被忽略。
            保留是为了不一次性改动所有调用点（``stream_dual`` 等）。

    客户端断开时原样上抛 ``GeneratorExit`` / ``CancelledError``（按停止不是错误）。
    """
    ensure_registered()

    session_id = str(session.session_id)
    resolved = resolve_specs(session, specs, kinds)
    # 栏目清单（事件里的 ``agent`` / ``agents`` 仍是 kind）：同一轮里 kind 已去重，
    # 所以 ``specs`` 与 ``agents`` 一一对应，可以直接按下标取模型。
    agents = [spec.kind for spec in resolved]
    models = {spec.kind: spec.model for spec in resolved}

    # 单栏：透传给 stream_chat，不经过合并逻辑。这不是优化，是**语义**——
    # 合并路径会吞掉 stream_chat 自己的 done 再补发，单栏时那样做只是多绕一圈，
    # 徒增两处「done 长什么样」的分歧。
    if len(agents) == 1:
        # 单栏也要分配（1 把）：不分的话这一栏走的是后端自己的全局轮转，与
        # 同时在跑的另一个人撞在同一把 key 上照样 429。
        single = agents[0]
        lease = (await _allocate_round_leases(kinds=agents, model_hint=models[single], session_id=session_id))[single]
        try:
            async for event in stream_chat(
                session=session,
                user_message=user_message,
                user_id=user_id,
                tool_selection=tool_selection,
                agent_kind=single,
                model=models[single],
                api_key=_lease_key(lease),
            ):
                yield event
        finally:
            # 客户端断开（GeneratorExit）也走这里：不还就会在之后每一轮里
            # 永久占掉这一路并发额度。
            lease.release()
        return

    primary, secondaries = agents[0], agents[1:]

    # 用户消息与标题只写一次：N 个后端跑的是同一条提问，各写一次会让回放里出现
    # N 条一模一样的提问。
    async with profile.timed("multi.record_user_message", session=session_id):
        await record_user_message(session, user_message)
    # 事件总线也只订阅一次：``stream_chat`` 订阅的是「本轮会话的外部事件」
    # （审批等），多次订阅会让一条审批只被其中一个消费、其余永远收不到。
    bus = get_bus()
    async with profile.timed("multi.bus_register", session=session_id):
        external_queue = await bus.register(session_id)

    primary_memo = StreamMemo()
    memos: dict[str, StreamMemo] = {kind: StreamMemo() for kind in secondaries}
    queues: dict[str, asyncio.Queue[dict[str, Any] | None]] = {kind: asyncio.Queue() for kind in secondaries}
    tasks: dict[str, asyncio.Task[None]] = {}

    # 失败矩阵的状态：全部失败时只转发第一条 error（见模块 docstring）
    errors: list[dict[str, Any]] = []
    ok: dict[str, bool] = dict.fromkeys(agents, True)
    # 整轮的辅助席位与资源都挂在它上面：客户端断开时 finally 统一释放。
    stack = AsyncExitStack()

    try:
        yield {"type": "meta", "session_id": session_id, "agent": primary, "agents": agents}
        yield {"type": "activity", "status": "thinking", "agent": primary, "agents": agents}

        # ── 开流前的事实（律师凭证 + prompt）：N 栏同一个答案，算一次共用 ────
        #
        # 放在两个首帧**之后**：先让前端看到 meta/thinking 再干这些活，与引入
        # 参数前的观感一致（那时这些活在各栏 stream_chat 里做）。
        #
        # 铸不出凭证时回退到「每栏自己铸」（context=None）：失败语义必须与逐栏
        # 铸造一致——那时是每栏各发一条 error，而不是整轮一条。
        async with profile.timed("multi.prepare_context", session=session_id):
            try:
                context = await prepare_context(session=session, user_id=user_id, user_message=user_message)
            except Exception:
                logger.info("多答：预铸凭证失败，回退到每栏各自铸造 session=%s", session_id, exc_info=True)
                context = None

        # ── 轮次级 key 分配：一栏一把互不相同的 key（见模块 docstring） ────
        #
        # 位置是硬的：参与方已定（知道要几把）、各栏还没启动（第一栏已经开跑就
        # 晚了，它只能用后端自己的全局轮转）。
        leases = await _allocate_round_leases(kinds=agents, model_hint=models[primary], session_id=session_id)
        # 整轮兜底归还：主答在自己下面的 finally 还、非主答在 ``_pump_one`` 的
        # finally 还；被 cancel 且之后没再被调度到的协程跑不到 finally，而漏还
        # 一把 key 会让那一路并发额度永久少 1（之后越来越容易 429，且无任何报错）。
        # ``KeyLease.release`` 幂等，重复归还无害。
        for lease in leases.values():
            stack.callback(lease.release)

        # ── 非主答：整轮抢一个 aux 席位，抢不到就全部降级 ────────────────
        #
        # 「整轮一个」而不是「每栏一个」：默认 aux_slots() = 4 × 0.25 = 1，每栏
        # 各抢一个会让三栏掉两栏（实测踩过）。同一轮的 N 栏是**同一个人的一次
        # 请求**，把它当 N 个独立请求去抢闸既跑不动、语义也不对。
        #
        # 用 ExitStack 而不是 `async with`：下面主答迭代里可能抛 GeneratorExit
        # （客户端断开），那条路径同样必须把席位还回去。
        aux_permit = await stack.enter_async_context(_hold_aux())
        if aux_permit:
            for kind in secondaries:
                tasks[kind] = asyncio.create_task(
                    _pump_one(
                        session=session,
                        user_message=user_message,
                        user_id=user_id,
                        tool_selection=tool_selection,
                        agent_kind=kind,
                        model=models[kind],
                        # 一栏一把：每栏拿到的 lease 就是它自己那把 key
                        lease=leases[kind],
                        memo=memos[kind],
                        queue=queues[kind],
                        context=context,
                    )
                )
        else:
            logger.info("多答降级为只跑主答 session=%s（aux 席位已满或关闭）", session_id)
            # 降级后那几栏一次请求都不会发：把它们的 key **立刻**还回去，别让
            # 本轮白占着并发额度（主答要跑多久，它们就会占多久）。
            for kind in secondaries:
                leases[kind].release()
            # **收窄 agents**：降级后本轮确实只有一个后端在跑。不收窄的话末尾会
            # 按 agents 给每一栏都发 done，而那些栏从未产出任何内容 —— 前端会
            # 多渲染空栏并在那里收尾（实测就是「(无内容)」）。
            agents = [primary]
            yield {
                "type": "activity",
                "status": ACTIVITY_DEGRADED,
                "agent": primary,
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
                agent_kind=primary,
                model=models[primary],
                api_key=_lease_key(leases[primary]),
                context=context,
            ):
                if event.get("type") == "done":
                    continue  # done 由本模块按栏统一发
                tagged = _tag(event, primary, primary_memo)
                if tagged.get("type") == "error":
                    errors.append(tagged)
                    if len(errors) > 1:
                        continue  # 全部失败：只发第一条，不堆 N 条
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
            # 主答的异常同样只降级成本栏的错误，不吞掉其他回答（失败矩阵第 2 条）
            ok[primary] = False
            logger.exception("多答：主答这一轮失败 session=%s", session_id)
            errors.append(_backend_error(primary, "主后端本轮运行失败，其他回答不受影响"))
            if len(errors) == 1:
                yield errors[0]
        finally:
            # 主答跑完（含客户端断开）即归还它那把 key：剩下的几栏可能还要跑一
            # 会儿，它们各自持有自己的租约，不需要跟主答同进同出。
            leases[primary].release()

        # ── 其余答案：把剩余事件全部转发给前端 ──────────────────────────
        for kind in secondaries:
            task = tasks.get(kind)
            if task is None:
                continue
            while True:
                event = await queues[kind].get()
                if event is None:
                    break
                tagged = _tag(event, kind, memos[kind])
                if tagged.get("type") == "error":
                    errors.append(tagged)
                    if len(errors) > 1:
                        continue
                yield tagged
            # 等任务收尾。``_pump_one`` 不抛 BudgetExceeded（席位由本轮统一持），
            # 这里的 exception 只可能是它内部的真实故障——那已经转成 error 事件
            # 进了队列，所以结果本身不需要再分支。
            await asyncio.gather(task, return_exceptions=True)
            await _persist_answer(session, kind, memos[kind])
    finally:
        # 提前退出（客户端断开）时把仍在跑的后端停掉：``stream_chat`` 内部靠
        # finally 把已流出的部分落库，取消它就是「用户按停止」的语义。
        for task in tasks.values():
            if not task.done():
                task.cancel()
        # finally 里**不能 yield**（GeneratorExit 路径上会抛 RuntimeError，
        # 表现为 SSE 被截断），收尾只做 await。
        await stack.aclose()
        await bus.unregister(session_id, external_queue)

    failed = [kind for kind, is_ok in ok.items() if not is_ok]
    if failed and len(failed) == len(agents):
        logger.warning("多答：全部后端都失败 session=%s kinds=%s", session_id, agents)
    # **每栏各发一个 done**，而不是只发一个「会话级 done」。
    #
    # 真实事故（2026-11-19）：只发一个 ``agent=primary`` 的 done 时，前端拿到它
    # 只收得了主栏；其余栏的光标永远转着、内容被当成「还在流」而丢弃，界面上
    # 全是「(无内容)」。
    #
    # 前端 `turn-handlers.onDone` 的契约就是「这个 done 属于哪个 agent，就收哪
    # 一栏」，全部栏收完才算整轮结束。所以这里按 agents 逐栏发，字段与单后端
    # 路径同形（`stream_chat` 也是每轮一个 done）。
    #
    # `agents` 仍然带着，前端/日志据它知道本轮有谁参与。
    for kind in agents:
        yield {"type": "done", "session_id": session_id, "agent": kind, "agents": agents}


async def stream_dual(
    *,
    session: AgentSession,
    user_message: str,
    user_id: int | None = None,
    tool_selection: str | None = None,
) -> AsyncIterator[dict[str, Any]]:
    """``stream_multi`` 的两栏薄包装（``dual=True`` 旧前端契约）。

    保留它只为不一次性改动调用点；内部只剩一份实现，没有第二套「双答」逻辑。
    两个 kind 的挑选规则见 ``pick_secondary``。
    """
    async for event in stream_multi(
        session=session,
        user_message=user_message,
        user_id=user_id,
        tool_selection=tool_selection,
        kinds=None,
    ):
        yield event


__all__ = [
    "ACTIVITY_DEGRADED",
    "MAX_ANSWERS",
    "AgentSpec",
    "StreamMemo",
    "normalize_agents",
    "pick_secondary",
    "primary_kind",
    "resolve_kinds",
    "resolve_specs",
    "stream_dual",
    "stream_multi",
]
