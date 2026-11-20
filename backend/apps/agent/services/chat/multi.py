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
      ├─ N 个 stream_chat 各一条 task（共用有界队列，交错上线）
      └─ bus.unregister + 每栏一个 done             ← 收尾

每个 ``stream_chat`` 各自照常写 ``AgentRun``（成本必须分别归因到各自的模型）与
自己的助手消息（带 ``agent_kind``）。它们各自的 ``done`` 在这里被**吞掉**，
全部结束后由本模块按栏补发。

## 谁跑主、谁跑次

调用方显式给 ``kinds``（API 层解析 ``agents`` 字段）。不给时退回「会话自己的
``agent_kind`` 是主，注册表里第一个不等于主的 kind 是次」——与旧 ``stream_dual``
同口径，保证 ``dual=True`` 的旧前端行为不变。

「主 / 次」只决定两件事：主答的正文由 ``stream_chat`` 自己落库；配额不足时只保留
主答。**事件通路上一视同仁**——每栏（含主答）都是独立 task，产出的帧先进同一个
有界队列，再由一个纯消费者按到达顺序 ``yield`` 出去。

## 公平交错合并（2026-11-20 修正，教训见 ``docs/harness/pitfalls.md`` PIT-020）

早先的形态是「主答在调用方协程里内联迭代 + 其余栏各一个**无界**队列，且只在
主答结束后按栏**串行**抽干」。后果是**左列永远最快**：左列恒为 ``agents[0]``，
右列的帧被后端扣住，等左列跑完才整批刷出，第 3 列还要等第 2 列的 task 结束。
前端本来就逐帧按 ``agent`` / ``run_id`` 分流（见
``frontend/src/features/copilot/streaming.ts``），所以这是纯后端缺陷。

现在的形态是「N 个 task + 一个共享**有界**队列（``_LANE_QUEUE_MAXSIZE``，背压
上限：无界队列会把整篇回答压在 RAM 里）+ 纯消费者」，每栏结束时往队列里放一个
``_LANE_DONE`` 哨兵。**谁先产出谁先上线**，没有任何「主栏优先」的隐式顺序。

## 失败矩阵（本模块的核心设计）

| 情况 | 事件 | 收尾 |
|:--|:--|:--|
| 全部成功 | 各自完整的事件流（带 ``agent`` / ``run_id``） | **每栏一个** ``done`` |
| 部分失败 | 成功的照常输出；失败方**只**发一条带 ``agent`` 的 ``error`` | **每栏一个** ``done`` |
| 全部失败 | 每栏**各自**一条 ``error``（带 ``agent``） | **每栏一个** ``done`` |
| 辅助配额已满 | 只跑主后端 + 一条 ``activity{status:"degraded", reason}`` | 一个 ``done``（agents 收窄为单栏） |

关于 ``done`` 的条数（2026-11-19 修正，教训保留在此）：早先的设计是「整轮只发
一个 done」，理由是「两个 done 会让前端在第一栏结束时收尾」。**那个理由站不住**
——前端 ``onDone`` 的契约就是「这个 done 属于哪个 agent，就收哪一栏」，只发一个
反而让其余栏永远收不了尾，界面上全是「(无内容)」。真实事故即由此而来，故改为
按栏发，字段与单后端路径同形。

关键取舍：**一个后端坏了不能把其他也拖下水**。律师要的是「至少有一个答案」，
所以每个后端的事件流被单独包住，异常就地转成一条 ``error``，其余继续转发。
也因此不用 ``gather(return_exceptions=False)``——那个会让第一个异常把整轮打死。

**每栏各发一条** ``error``（2026-11-20 修正）：早先的写法是「只发第一条」，理由是
「N 条 ``error`` 会渲染成 N 行，读起来像同一件事失败了 N 遍」。公平交错之后那个
写法连正确性都保不住：谁先到谁才是「第一条」，主栏的 ``error`` 可能被次栏占位而
**静默不发**——最左栏出错了却没有错误行。前端 ``onError`` 是单字段覆盖写
（``lastError``，不会堆 N 条横幅）并按 ``origin.kind`` 把**那一栏**标成「本轮
未做」，所以正确做法是每栏各发一条、各自带 ``agent``。

## 落库

主后端那一半走 ``stream_chat`` 的常规落库；其余那一半用
``persist_assistant=False`` 把正文交回这里（``StreamMemo``），由本模块带着
``agent_kind`` 落库——否则次答在历史回放里会凭空消失，律师第二天再看只剩一份。

补落必须**按 ``agents`` 顺序**，不能按完成顺序：历史回放按 ``-created_at,-id``
排序、前端用 assistant 行序决定栏的左右，谁先跑完谁先落库会让刷新后栏序随机。

客户端断开（按停止）**也要落库**：被取消的 ``stream_chat`` 会跑完自己的
``finally`` 把已流出的正文写进 ``StreamMemo``，本模块在那之后补写还没落过的栏。
不做这一步的话，用户在次栏说到一半按停止，下次打开会话就只剩主栏。

## 并发上限

``MAX_ANSWERS = 4``。理由是成本线性增长且四栏并排在 UI 上已接近可读性极限，
不是技术限制——``_pump_lane`` 对 N 没有假设，调高这个常量即可。

## 轮次级 key 分配

网关对**每把 key** 限 3 并发（实测 429 + ``retry-after: 60``，那一栏表现为
「卡住 60 秒」）。后端自己的 ``_next_key`` 是全局轮转计数，**不保证**同一轮的
N 栏落在不同 key 上，也不知道哪把已经满了。所以分配在这里做一次：开流前从
``LLMProvider.api_keys`` 取出 key 池，由 ``key_scheduler.allocate`` 给**每一栏
各分一把互不相同**的 key，经 ``RunContext.api_key`` 传给后端。

归还的规则是「谁用谁还」：每一栏都在 ``_pump_lane`` 的 ``finally`` 归还，
整轮另挂一层兜底（被 cancel 后没再被调度到的栏跑不到
``finally``，而漏还一把 key 的代价是那一路并发额度永久少 1 → 越来越容易 429）。
拿不到 key 池（没有 provider / 读配置失败）时**不报错**，传 ``None`` 让后端走
它原来的轮转口径——与引入 key 分配前逐字一致。
"""

from __future__ import annotations

import asyncio
import contextlib
import logging
from collections.abc import AsyncGenerator, AsyncIterator, Mapping, Sequence
from contextlib import AsyncExitStack, asynccontextmanager
from dataclasses import dataclass, field
from typing import Any, cast

from ...backends import available_kinds
from ...backends import get as get_backend
from ...backends.builtin import ensure_registered
from ...backends.gateway_cache import load_api_keys
from ...backends.key_scheduler import KeyLease, get_key_scheduler
from ...errors import AgentError, project
from ...models import AgentMessage, AgentSession
from ...sse_types import FinishReason
from ..event_bus import EventBus, get_bus
from . import budget, persist, profile
from .stream import ContextPrep, next_run_turn, prepare_context, record_user_message, stream_chat

logger = logging.getLogger(__name__)

#: 配额不足时告知前端的 ``activity.status``。用**单独一个状态值**而不是
#: ``error``：主后端照常给出了答案，本轮是成功的，只是少了几栏对比。
ACTIVITY_DEGRADED = "degraded"

#: 一轮最多同时问几个 agent。超出的由 API 层挡掉（400），本模块不静默截断——
#: 静默截断会让用户以为选中的都跑了，实际少跑了几个还看不出来。
MAX_ANSWERS = 4

#: 所有栏共用的那个队列的容量上限。**有界是为了背压**：
#: 无界队列在慢客户端下会把 N 栏的全部 delta（一整篇回答）压在进程内存里，
#: 而它们本来只需要「生产者稍微慢一点」。256 与 ``event_bus.MAX_QUEUED``
#: 同量级——超过这个数说明前端已经跟不上，让后端等一下才是对的。
_LANE_QUEUE_MAXSIZE = 256

#: 一栏「帧已全部产出」的哨兵（单例，消费者用 ``is`` 判等）。
#:
#: 为什么不用 ``{"type": "done"}``：``done`` 是后端的帧类型，本模块自己也要
#: 按栏补发真正的 ``done``；拿它当内部收尾信号会让消费者分不清「要转发的帧」
#: 与「这一栏结束了」。
_LANE_DONE = object()


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
    #: 本栏已落库的助手消息主键（``None`` = 没落库 / 落库失败 / 取消时还未完成）。
    #:
    #: 为什么需要它：整轮结束后要用**轮级** ``finish_reason`` 回写这一行
    #: （部分失败时整轮是 ``degraded``，而单栏视角只会说 ``ok``）。拿不到主键
    #: 就只能在服务层按「本条消息之后创建的 assistant 行」反猜，那会写到下一轮
    #: 的头上。
    message_id: int | None = None


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


def _backend_error(agent: str, exc: BaseException | None = None, *, message: str = "") -> dict[str, Any]:
    """失败方唯一的一条 ``error``（带 ``agent``，前端据此挂到对应栏）。

    帧由 ``errors.project`` 投影（不手写）：多答的失败方可能是限流/超时/未知
    kind，前端要的是 ``code`` 而不是一句统一的中文——否则「三栏里有一栏只是被
    限流」会被读成「那一栏坏了」。
    """
    return project(exc or AgentError(message or "该 agent 本轮运行失败"), agent=agent, message=message or None)


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
        message = await AgentMessage.objects.acreate(
            session=session,
            role=AgentMessage.Role.ASSISTANT,
            content=text,
            metadata=metadata,
            agent_kind=agent,
        )
    except Exception:
        logger.warning("多答：非主答正文落库失败 session=%s agent=%s", session.session_id, agent, exc_info=True)
        return
    # 主键回交：整轮结束时要用轮级 finish_reason 回写这一行（见 ``StreamMemo.message_id``）。
    memo.message_id = message.pk


async def _pump_lane(
    *,
    session: AgentSession,
    user_message: str,
    user_id: int | None,
    tool_selection: str | None,
    agent_kind: str,
    model: str | None,
    lease: KeyLease,
    memo: StreamMemo,
    queue: asyncio.Queue[Any],
    context: ContextPrep | None,
    turn: int,
    persist_assistant: bool,
) -> None:
    """**一栏**后端：帧补齐 ``agent`` / ``run_id`` 后进共享队列，结束时放哨兵。

    主答与其他栏走同一个函数。早先主答是在 ``stream_multi`` 里内联迭代的，
    其余栏各走一个无界队列、只在主答结束后串行抽干——于是左列（恒为
    ``agents[0]``）永远最快、右列整批后到（``docs/harness/pitfalls.md`` PIT-020）。

    ``lease`` 是这一栏自己的 key 租约：**本函数负责归还**（在 ``finally`` 里，
    异常与取消路径同样跑）。漏还一把 key 的代价是那一路并发额度永久少 1，
    之后越来越容易 429，而且没有任何报错。

    ## aux 席位为什么由调用方统一持（而不是这里各抢一个）

    实测：``aux_slots() = 总席位(4) × 0.25 = 1``。若每栏各自
    ``reserve("aux")``，三栏时第二、三个必然被挡——界面上「选了三个只出两个」，
    且被挡的那栏连一句原因都没有。**这个坑真踩过**：v27.20 的三栏用例实测
    ``third-agent outcome=[BudgetExceeded('辅助 agent 并发已满（1/1）')]``。

    语义上也站不住：``aux`` 闸门防的是「一个用户同时开太多对比请求」，而同一轮
    的 N 栏是**同一个人的一次请求**，当成 N 个独立请求去抢闸是错的。

    所以席位由 ``stream_multi`` 在整轮外面持有一个（见 ``_hold_aux``），本函数
    只管跑。``BudgetExceeded`` 不再可能从这里冒出来。

    ``GeneratorExit`` / ``CancelledError`` 原样上抛：客户端断开时这是「按停止」
    的语义，不是失败，不该变成一条 ``error`` 帧。
    """
    # 生成器先取到手：`async for` 提前退出时**不会**替你关它（见下面 finally）。
    #
    # ``cast``：``stream_chat`` 的返回标注是 ``AsyncIterator``（调用方只该迭代它），
    # 而关闭生成器需要 ``AsyncGenerator`` 上的 ``aclose``。用 cast 而不是把
    # ``stream_chat`` 的签名改成 ``AsyncGenerator``：那会把「也可以传一个普通
    # 异步迭代器进来」的余地收窄，而本函数只关心「能迭代 + 能关」这两件事。
    agen = cast(
        "AsyncGenerator[dict[str, Any], None]",
        stream_chat(
            session=session,
            user_message=user_message,
            user_id=user_id,
            tool_selection=tool_selection,
            # 用户消息已由 stream_multi 落库一次（N 个后端共用同一条提问）
            user_message_recorded=True,
            # 主答由 stream_chat 自己落库（栏级 usage / ttft 都在它手里）；
            # 非主答的正文交回本模块，只有那里知道该带哪个 agent_kind
            persist_assistant=persist_assistant,
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
            # 与主答**同一个**轮次号（本轮只取一次号，见 ``stream.next_run_turn``）
            turn=turn,
        ),
    )
    try:
        async for event in agen:
            if event.get("type") == "done":
                continue  # done 由 stream_multi 按栏统一发，见模块 docstring
            # 进队列前就补齐 ``agent`` / ``run_id``：消费者是哑的（只按到达顺序
            # 转发），而前端无条件按这两个字段分流——口径必须在这里统一，不能
            # 让前端猜「哪种事件可能没有 agent」。
            await queue.put(_tag(event, agent_kind, memo))
    except (GeneratorExit, asyncio.CancelledError):
        raise
    except Exception as exc:
        logger.exception("多答：agent=%s 这一轮失败 session=%s", agent_kind, session.session_id)
        # ``agent`` 带上：**每栏各发一条** error，前端靠它把那一栏标成「本轮
        # 未做」（只发一条会让主栏的失败被次栏占位而静默消失，见模块 docstring）
        await queue.put(
            _backend_error(
                agent_kind,
                exc,
                message="该 agent 本轮运行失败，其他回答不受影响（详见服务端日志）",
            )
        )
    finally:
        # **必须显式关掉这一栏的生成器**：`async for` 提前退出（最典型的是被
        # 取消在 ``queue.put`` 上——队列有界之后这一路才成为可能）不会替你
        # ``aclose()``（PEP 525），而 ``stream_chat`` 的 finally 才是唯一把已
        # 流出的正文写进 ``memo.parts``、把已花的 token 记进 ``AgentRun`` 的
        # 地方。不关的后果是断连时次栏半截正文静默丢失，且主栏那条助手行改由
        # 事件循环的 asyncgen finalizer 异步补写——它会晚于这里同步写的次栏行，
        # 回放时栏序反转（``docs/harness/pitfalls.md`` PIT-021：这一整段就是那条坑
        # 的根治点，它的症状是「按了停止右侧几栏的回答凭空消失 / 刷新后左右栏反了」）。
        #
        # 吞掉 Exception 但不吞取消：``aclose()`` 自己会吞 GeneratorExit；真正的
        # 取消要继续上抛（那是「按停止」的语义，不是失败）。
        with contextlib.suppress(Exception):
            await agen.aclose()
        # 先还 key 再收尾：归还只是字典计数，不会被打断；而漏还的代价是永久的。
        lease.release()
        # 哨兵只能走 ``await queue.put()``，**不能** ``put_nowait``：队列满时丢了
        # 哨兵，消费者就永远等不到这一栏收尾。这里不会白等——消费者唯一的中途
        # 退出路径是收尾阶段的 ``task.cancel()``，而它会继续抽干队列（见
        # ``_join_lanes``）。
        await queue.put(_LANE_DONE)


async def _pump_external(external: asyncio.Queue[dict[str, Any]], queue: asyncio.Queue[Any]) -> None:
    """把事件总线（审批 / 提问）的帧搬进共享队列。

    审批不走后端事件流（见 ``event_bus`` 模块说明），所以它需要自己的搬运协程。
    早先的写法是「主答每产一个帧就顺手 ``get_nowait()`` 一次」捎带出来，但公平
    交错之后主答不再有「间隙」这个概念（它和别栏一样只是一条 task）。

    收尾交给取消：本协程不丢 ``_LANE_DONE``——它不是一栏，不该计入栏数。
    """
    while True:
        await queue.put(await external.get())


async def _join_lanes(tasks: Sequence[asyncio.Task[None]], queue: asyncio.Queue[Any]) -> None:
    """等这些 task 真正收尾；期间继续把共享队列抽干（取到的条目直接丢掉）。

    为什么要边等边抽干：被取消的栏会在 ``_pump_lane`` 的 ``finally`` 里
    ``await queue.put(_LANE_DONE)``，而 ``task.cancel()`` 只打断**一次** await
    （当时挂着的那个）。若那一栏是在 ``queue.put(帧)`` 上被取消的，队列多半还
    是满的——它接着在 ``finally`` 里放哨兵就会一直挂着，于是「等它收尾」变成
    死等，SSE 连接再也关不掉。这里腾出队列位置即可，收尾阶段已经没有人要看
    这些帧了。
    """
    pending = {task for task in tasks if not task.done()}
    while pending:
        getter: asyncio.Task[Any] = asyncio.ensure_future(queue.get())
        done, _ = await asyncio.wait({*pending, getter}, return_when=asyncio.FIRST_COMPLETED)
        pending.difference_update(done)
        if not getter.done():
            getter.cancel()
    for task in tasks:
        # 取走异常：``_pump_lane`` 只该抛取消，真抛出来是缺陷——记一条日志，
        # 别让它变成「Task exception was never retrieved」这种没有上下文的噪声。
        if not task.done() or task.cancelled():
            continue
        exc = task.exception()
        if exc is not None:
            logger.warning("多答：某一栏的 task 异常收尾", exc_info=exc)


async def _close_round(
    *,
    session: AgentSession,
    agents: Sequence[str],
    memos: Mapping[str, StreamMemo],
    persisted: set[str],
    tasks: Mapping[str, asyncio.Task[None]],
    external_task: asyncio.Task[None] | None,
    queue: asyncio.Queue[Any],
    stack: AsyncExitStack,
    bus: EventBus,
    session_id: str,
    external_queue: asyncio.Queue[dict[str, Any]],
) -> None:
    """收尾：停掉仍在跑的栏、补落断连时未落库的栏、释放席位与订阅。

    由 ``stream_multi`` 的 ``finally`` 通过 ``ensure_future`` + ``shield`` 调用：
    真取消（客户端断开）时若让 ``CancelledError`` 直接打断，已经流出的次栏正文
    就永久丢了（下次打开会话只剩主栏）。与 ``stream.py`` 的取消落库路径同一口径。

    补落按 ``agents`` 顺序，**不是**按完成顺序（见模块 docstring 的「落库」）。
    ``persisted`` 是正常路径已经落过的栏，这里只补没落过的。
    """
    for task in tasks.values():
        if not task.done():
            task.cancel()
    if external_task is not None and not external_task.done():
        external_task.cancel()
    # 等它们真正收尾：被取消的 ``stream_chat`` 要跑完自己的 ``finally`` 才会把
    # 已流出的正文写进 ``memo.parts``（见 ``stream.py`` 的落库块）；不等的话
    # 下面拿到的是空正文，等于没落。
    await _join_lanes([*tasks.values(), *([external_task] if external_task is not None else [])], queue)
    for kind in agents[1:]:  # 主答由 ``stream_chat`` 自己落库，不重复落
        if kind in persisted:
            continue
        await _persist_answer(session, kind, memos[kind])
    await stack.aclose()
    await bus.unregister(session_id, external_queue)


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
    # 本轮轮次号只取**一次**：N 栏必须共用同一个 turn。各栏各自 INCR 会让
    # 「同一次提问」的三栏拿到 1/2/3，前端按 run 归集用量时把一轮拆成三轮。
    turn = await next_run_turn(session_id)

    # 用户消息与标题只写一次：N 个后端跑的是同一条提问，各写一次会让回放里出现
    # N 条一模一样的提问。
    async with profile.timed("multi.record_user_message", session=session_id):
        await record_user_message(session, user_message)
    # 事件总线也只订阅一次：``stream_chat`` 订阅的是「本轮会话的外部事件」
    # （审批等），多次订阅会让一条审批只被其中一个消费、其余永远收不到。
    bus = get_bus()
    async with profile.timed("multi.bus_register", session=session_id):
        external_queue = await bus.register(session_id)

    # 每栏一个 memo（含主答）：主答的正文由 stream_chat 自己落库，但收尾时仍要
    # 从它身上取 run_id / 水位 / 助手行主键，口径与非主答一致。
    memos: dict[str, StreamMemo] = {kind: StreamMemo() for kind in agents}
    # 所有栏**共用**这一个队列：每栏各一个队列、只按 agents 顺序按栏抽干正是
    # 本次要废除的设计（左列永远最快，PIT-020）。有界 = 背压（见常量注释）。
    queue: asyncio.Queue[Any] = asyncio.Queue(maxsize=_LANE_QUEUE_MAXSIZE)
    tasks: dict[str, asyncio.Task[None]] = {}
    external_task: asyncio.Task[None] | None = None
    # 失败矩阵的状态：谁失败谁被记成 False（每栏各自一条 error）
    ok: dict[str, bool] = dict.fromkeys(agents, True)
    # 已经落过库的栏：收尾时只补没落过的（断连路径靠它避免重复落库）
    persisted: set[str] = set()
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
        # 整轮兜底归还：每一栏都在 ``_pump_lane`` 的 finally 还；被 cancel 且之后
        # 没再被调度到的协程跑不到 finally，而漏还一把 key 会让那一路并发额度
        # 永久少 1（之后越来越容易 429，且无任何报错）。
        # ``KeyLease.release`` 幂等，重复归还无害。
        for lease in leases.values():
            stack.callback(lease.release)

        # ── 非主答：整轮抢一个 aux 席位，抢不到就全部降级 ────────────────
        #
        # 「整轮一个」而不是「每栏一个」：默认 aux_slots() = 4 × 0.25 = 1，每栏
        # 各抢一个会让三栏掉两栏（实测踩过）。同一轮的 N 栏是**同一个人的一次
        # 请求**，把它当 N 个独立请求去抢闸既跑不动、语义也不对。
        #
        # 用 ExitStack 而不是 `async with`：下面任何一个 ``yield`` 都可能抛
        # GeneratorExit（客户端断开），那条路径同样必须把席位还回去。
        aux_permit = await stack.enter_async_context(_hold_aux())
        if not aux_permit:
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

        # ── 一栏一条 task，全部往同一个有界队列里放 ──────────────────────
        #
        # 主答也在其中：内联迭代会让它独占「实时上线」的位置，别的栏再好也只能
        # 等它跑完（docs/harness/pitfalls.md PIT-020）。谁先产出谁先上线。
        for kind in agents:
            tasks[kind] = asyncio.create_task(
                _pump_lane(
                    session=session,
                    user_message=user_message,
                    user_id=user_id,
                    tool_selection=tool_selection,
                    agent_kind=kind,
                    model=models[kind],
                    # 一栏一把：每栏拿到的 lease 就是它自己那把 key
                    lease=leases[kind],
                    memo=memos[kind],
                    queue=queue,
                    context=context,
                    # 与主答**同一个**轮次号
                    turn=turn,
                    # 主答由 stream_chat 自己落库（栏级 usage / ttft 在它手里）；
                    # 非主答的正文交回本模块才能带上 agent_kind
                    persist_assistant=kind == primary,
                )
            )
        # 审批 / 提问走事件总线，不是后端事件流：它们也需要自己的搬运协程
        # （原先靠「主答每产一个帧就 get_nowait 一次」捎带，现在没有那个间隙了）。
        external_task = asyncio.create_task(_pump_external(external_queue, queue))

        # ── 纯消费者：谁先产出谁先上线 ──────────────────────────────────
        #
        # 公平交错就是本次修复本身（docs/harness/pitfalls.md PIT-020）：消费者
        # 只做三件事——转发、数哨兵、按帧自己的 ``agent`` 记录哪一栏失败；这里
        # **刻意**没有任何「主栏优先」的排序。
        finished = 0
        while finished < len(agents):
            event = await queue.get()
            if event is _LANE_DONE:
                finished += 1
                continue
            if event.get("type") == "error":
                # 哪一栏失败由这一帧自己的 ``agent`` 说（``_pump_lane`` 已补齐）：
                # 整轮结论要据此算 degraded / error，否则「部分失败」在收尾事件
                # 与落库 metadata 里都看不见（律师看不出这一轮没跑全）。
                #
                # 用 ``get`` + 成员判定而不是直接下标：外部总线（审批 / 提问）
                # 的帧也走这个队列，它的契约不保证带 ``agent``；真出现一条
                # ``type="error"`` 的外部帧，``KeyError`` 会把整个生成器打死，
                # 四栏一条 ``done`` 都发不出去。
                agent = event.get("agent")
                if agent in ok:
                    ok[agent] = False
            yield event

        # ── 正常收尾：等所有栏真正结束，再按 agents 顺序落非主答正文 ────
        #
        # 顺序是硬的：此刻各栏 ``stream_chat`` 都已跑完自身的 ``finally``
        # （``memo.parts`` / ``memo.metadata`` 已填好），落库才拿得到正文。
        await _join_lanes(list(tasks.values()), queue)
        for kind in agents[1:]:  # 主答由 ``stream_chat`` 自己落库，不重复落
            # 记账提到 await **之前**：取消若正好落在 ``acreate`` 里，asgiref
            # 的线程写仍会提交，而 ``memo.message_id`` 还是 None —— 留在后面
            # 记账会让收尾路径再写一条内容一样的行。
            persisted.add(kind)
            await _persist_answer(session, kind, memos[kind])
    finally:
        # 提前退出（客户端断开 / 被取消）的收尾：停掉仍在跑的栏，并按栏补落库。
        #
        # 这一段**屏蔽外层取消**：真取消时若让 ``CancelledError`` 直接打断，
        # 已流出的次栏正文就永久丢了（下次打开会话只剩主栏）。做法与
        # ``stream.py`` 的取消落库路径同一口径（ensure_future + shield）。
        #
        # finally 里**不能 yield**（GeneratorExit 路径上会抛 RuntimeError，
        # 表现为 SSE 被截断），收尾只做 await。
        closing = asyncio.ensure_future(
            _close_round(
                session=session,
                agents=agents,
                memos=memos,
                persisted=persisted,
                tasks=tasks,
                external_task=external_task,
                queue=queue,
                stack=stack,
                bus=bus,
                session_id=session_id,
                external_queue=external_queue,
            )
        )
        closing.add_done_callback(persist._log_task_failure)
        with contextlib.suppress(asyncio.CancelledError):
            await asyncio.shield(closing)

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
    # 收尾原因：全部失败才是 error，部分失败是 degraded（律师需要知道「另外几栏
    # 没跑成」而不是看到几个空白栏头）。前端靠 ``finish_reason`` 决定是否把栏
    # 标成「本轮未做」，不靠「有没有正文」去猜。
    finish_reason: FinishReason = "error" if failed and len(failed) == len(agents) else "degraded" if failed else "ok"
    # 轮级结论回写本轮已落库的助手行：历史回放（客户端刷新 / 第二天再看）拿不到
    # 这条 done，只有消息 metadata 能告诉前端「这轮是部分失败还是正常结束」。
    # 单栏视角只会写 ok/error（见 ``stream._lane_finish_reason``），「另外几栏
    # 没跑成」是**整轮**才知道的事实，只能在这里补。
    #
    # 位置在 done 之前：前端收到 done 往往会立即拉一次消息列表（拿 message_id /
    # 可续写状态），回写晚于它就会读到旧值，然后本轮的「继续生成」按钮是灰的。
    await persist._stamp_finish_reason(
        message_ids={kind: memos[kind] for kind in agents},
        finish_reason=finish_reason,
    )
    # 逐栏水位：多答时前端按栏写 ``contextUsage``。不填每栏的 ``context_*``
    # 会让水位条停在上一轮的旧值——那比不显示更糟（显示的是错的数）。
    # 收尾事实按 ``run_id`` 存在各后端实例上（与单后端路径同源：
    # ``stream.py`` 也是从 ``backend.result_for(run_id)`` 取）。
    for kind in agents:
        run_id = memos[kind].run_id
        context_used: int | None = None
        context_total: int | None = None
        if run_id:
            # 取不到就保持 None（前端隐藏水位），**不能**因为水位取不到而
            # 把 done 吞掉：done 是前端收栏的唯一信号，缺一条那一栏就永远转圈。
            try:
                result_for = getattr(get_backend(kind), "result_for", None)
                result = result_for(run_id) if result_for is not None else None
                if result is not None:
                    context_used, context_total = result.context_used, result.context_total
            except Exception:
                logger.warning("多答：%s 栏水位获取失败（不影响收栏）", kind, exc_info=True)
        yield {
            "type": "done",
            "session_id": session_id,
            "agent": kind,
            "agents": agents,
            "run_id": run_id,
            "finish_reason": finish_reason,
            "context_used_tokens": context_used,
            "context_total_tokens": context_total,
        }


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
