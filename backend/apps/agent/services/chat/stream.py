"""stream_chat —— 一轮对话的 SSE 编排（原 chat_service.py 主体）。

本层是**编排层**：准入（铸凭证）、落库（消息 / 标题 / ``AgentRun``）、事件总线、
会话收尾都归它；「跑一轮」本身交给 ``backends`` 注册表里按 kind 取到的后端。
后端只吐事件，本层把事件先入账再转发，保证「客户端断开时已送达的增量已经在落库
缓冲里」。

## 错误文案从哪来

本层不再手写 ``{"type": "error", "message": ...}``：所有错误帧都经
``errors.project`` 投影成 ``code`` / ``scope`` / ``detail`` / ``message``。按异常
类型分 ``except`` 只剩一个用途——**运维账本的 ``AgentRun.error_kind``**
（``pi_unavailable`` / ``queue_timeout`` …，DB 里的历史短串，改名等于历史数据
对不上）。给律师看的措辞与给前端分支的 ``code`` 一律由 ``errors.py`` 决定：
两套词汇各为各的目的存在，混用会让其中一方被迫冻结。
"""

from __future__ import annotations

import asyncio
import contextlib
import logging
import time
from collections.abc import AsyncIterator
from dataclasses import dataclass
from typing import Any

from asgiref.sync import sync_to_async
from django.core.cache import cache
from django.db import DatabaseError
from django.utils import timezone

from ...backends import RunContext
from ...backends import get as get_backend
from ...backends.builtin import ensure_registered
from ...errors import AuthFailedError, project
from ...models import AgentMessage, AgentSession
from ...pi.pool import PoolQueueTimeoutError
from ...pi.rpc_client import PiError, PiNotAvailableError
from ...sse_types import FinishReason
from ..event_bus import get_bus, redis_cache_enabled
from ..history import render_transcript
from ..memory_tasks import enqueue_extraction
from ..session_cleanup import has_pi_session
from ..skills.expand import expand_skill_prompt
from . import env, persist, profile
from .citations import CitationCollector

logger = logging.getLogger(__name__)

#: 会话标题缺省取首条用户消息的前若干字（侧边栏会话列表用）
AUTO_TITLE_LIMIT = 30

#: 轮次计数键前缀（Redis INCR）：``agent:run:seq:{session_id}`` → 1, 2, 3 …
_RUN_SEQ_KEY_PREFIX = "agent:run:seq:"
#: 计数键的存活窗口（秒）。7 天：够覆盖同一会话的连续追问，又不会给每个会话
#: 永久留一个键（会话数量只增不减）。窗口内不复位 = ``run_id`` 在同一会话内
#: 单调递增；键过期后从 1 重新开始，旧 run 早已跑完，不会混淆。
_RUN_SEQ_TTL = 7 * 24 * 3600


def _next_turn_sync(session_id: str) -> int | None:
    """本会话的下一轮次号；拿不到（无 Redis / 调用失败）返回 ``None``。

    同步函数：Redis 的 IO 不能占着事件循环（``cache.incr`` 在网关/网络抖动时
    可能阻塞到 socket 超时，那会把**所有**并发会话的 SSE 一起拖住）。调用方经
    ``sync_to_async(thread_sensitive=False)`` 放到线程里跑。
    """
    if not redis_cache_enabled():
        # 非 Redis 缓存（开发环境的 LocMem / 测试的 Dummy）里计数器是**进程内**的：
        # 两个 worker 各自从 1 开始，反而会造出跨 worker 的重复 run_id——那比
        # 固定 ``:1`` 更危险（前端把两个 run 的事件归成一个）。所以直接不计数。
        return None
    key = f"{_RUN_SEQ_KEY_PREFIX}{session_id}"
    try:
        # ``add`` 只负责建档（键已存在时是 no-op，不会把计数打回 0），
        # ``incr`` 才是原子的 INCRBY。
        cache.add(key, 0, _RUN_SEQ_TTL)
        turn = int(cache.incr(key))
        # 滑动窗口：只 touch 不支持就算了（部分后端没有），计数本身仍然正确。
        with contextlib.suppress(Exception):
            cache.touch(key, _RUN_SEQ_TTL)
        return turn
    except Exception:
        # Redis 挂了**不能**让对话失败：run_id 退回 ``:1``（引入本能力之前的行为），
        # 审批回调与 ``result_for`` 仍按整串归因，只是跨轮不再唯一。
        logger.warning("轮次计数失败，run_id 回落为 :1 session=%s", session_id, exc_info=True)
        return None


async def next_run_turn(session_id: str) -> int:
    """本会话的下一轮次号（Redis ``INCR``；不可用时恒 ``1`` = 旧行为）。

    为什么轮次必须真递增：``run_id = {session}:{kind}:{turn}`` 是前端按 run
    归集用量的唯一键。恒为 ``1`` 时同一会话的第二轮与第一轮共用一个 run_id，
    用量、审批与 ``backend.result_for`` 全归到同一格里——多轮一跑就串账。

    **同一轮的多栏必须共用同一个 turn**：多答（``multi.py``）在开流前调一次，
    把结果逐栏传下去（``stream_chat(turn=...)``）。各栏各自 INCR 会让「同一轮」
    的三栏拿到 1/2/3，前端再也无法把三条 run 认成一次提问。
    """
    turn = await sync_to_async(_next_turn_sync, thread_sensitive=False)(session_id)
    return turn if turn is not None else 1


def _lane_finish_reason(*, cancelled: bool, follow_ok: bool) -> FinishReason:
    """单栏视角的「这轮怎么结束的」（与 ``done.finish_reason`` 同一枚举）。

    ``cancelled`` 只在落库 metadata 里出现：客户端断开时生成器已被关闭，没有
    通道发 ``done``（见 ``sse_types.WIRE_UNREACHABLE``）。
    """
    if cancelled:
        return "cancelled"
    return "ok" if follow_ok else "error"


@dataclass(frozen=True)
class ContextPrep:
    """一轮开流前**与栏无关**的事实：律师凭证 + 本轮 prompt。

    为什么捆成一个值：三 agent 同答时 ``stream_chat`` 会被调用 N 次，而这两件
    事对 N 栏是**同一个答案**（同一个律师、同一个会话、同一条提问）。各栏各算
    一次不只是白跑：``mint_user_token`` / ``_recent_history`` 都走
    ``sync_to_async(thread_sensitive=True)``，即在同一线程上排队，重复 N 次就是
    串行 N 次；``has_pi_session`` 每次还会把会话目录 ``mkdir`` + ``chmod`` 一遍。
    所以 ``stream_multi`` 算一次，N 个 ``stream_chat`` 共用（见 ``prepare_context``）。

    不能跨轮复用：凭证每轮重铸（寿命说明见 ``pi/user_token.py``），pi session
    是否已存在、历史有几条每轮都在变。
    """

    #: 律师本人的 access token（``user_id`` 为空时是空串，工具面回退服务账号）
    user_token: str
    #: 本轮实际发给后端的 prompt：正常情况下就是用户消息；无 pi session 但有
    #: 历史时是补上了 transcript 的那份（见 ``prepare_context``）。
    prompt_text: str
    #: 本轮技能索引块（``prompt_block.render_skill_block`` 的产物）；空串 = 不注入
    #: （无用户身份 / 总开关 off·dry / 渲染失败降级）。
    #:
    #: 为什么捆进 ``ContextPrep`` 而不是各栏自己算：索引块是**每用户**的事实，
    #: 与栏无关——N 栏问的是同一个律师，各算一次只会把同一条 ``resolve_for_user``
    #: 查询排队 N 遍（那是同步 ORM，``thread_sensitive=True`` 下就是串行 N 次）。
    #: 它也不能在 ``stream_chat`` 里判 ``isolated``：隔离与否是后端的运行参数，
    #: 由后端消费 ``RunContext`` 时决定，编排层替它抹掉就再也测不出违反不变量。
    skill_block: str = ""
    #: 本轮被展开的 ``/skill:`` 留痕（``{key, name, scope, version}``）；未点名时为
    #: ``None``。它要落进**这一轮 user 消息**的 ``metadata["expanded_skill"]``：
    #: ``content`` 必须保持原文（审计看到的是律师原话），而「模型当时到底读了哪条
    #: 技能、哪个版本」只有这份留痕能回答——前端也靠它显示「已引用选段」式的提示。
    expanded_skill: dict[str, Any] | None = None


async def probe_pi_session(session_id: str) -> bool:
    """该会话是否已有 pi 原生 session（决定续写还是 transcript 回退）。

    单独成函数是因为 ``stream_multi`` 要用**同一口径**在整轮外面探一次：两处
    各写一份 ``sync_to_async(..., thread_sensitive=True)`` 迟早会漂移，而漂移的
    表现是「有的栏补了历史、有的没补」，极难看出来。
    """
    return await sync_to_async(has_pi_session, thread_sensitive=True)(session_id)


def _skill_index(user_id: int | None) -> tuple[str, list[str], list[str]]:
    """同步渲染技能索引块 → ``(block, names, not_injected)``。

    必须在 worker 线程里调：``resolve_for_user`` 是同步 ORM，直接在异步上下文跑会
    抛 ``SynchronousOnlyOperation``（而这条路径在**每轮**对话上，不能出一次错）。

    ``user_id is None`` 时空块：没有用户身份就没有个人/团队/所内技能，而索引块
    里只剩内置几条的意义也不大——与「不凭无身份去查库」的口径一致。
    """
    if user_id is None:
        return "", [], []
    # 延迟 import：``render_skill_block`` 走 ``flags``，模块缺失/导入异常时由调用方
    # 降级为空块，而不是让整轮对话 import 失败。
    from ..skills.prompt_block import render_skill_block
    from ..skills.resolve import resolve_for_user

    entries = resolve_for_user(user_id)
    block, not_injected = render_skill_block(entries)
    not_injected_names = [str(ref.get("name") or "") for ref in not_injected]
    if not block:
        # 空块（总开关 ``off`` / ``dry``，或预算连标题都装不下）：一条都没注进去，
        # 名字清单必须为空——否则日志会把「已解析出来」读成「已送达」。
        return "", [], not_injected_names
    skipped = set(not_injected_names)
    names = [str(entry.get("name") or "") for entry in entries if str(entry.get("name") or "") not in skipped]
    return block, names, not_injected_names


async def prepare_context(*, session: AgentSession, user_id: int | None, user_message: str) -> ContextPrep:
    """算出本轮开流前与栏无关的事实：凭证 + prompt（含展开与上下文回退）+ 索引块。

    顺序是**铸造 → 展开 ``/skill:`` → 探 session → 补历史 → 算索引块**。前两步的
    顺序是硬的：展开必须在 ``render_transcript`` **之前**，否则历史回退路径会把
    ``<skill>`` 块包进「用户历史」段落里（模型会当成上一轮说过的话），而 pi 原生
    展开也会因为 transcript 前缀继续静默失效。

    Raises:
        用户被删 / 停用时 ``mint_user_token`` 抛错——怎么拒由调用方决定：
        ``stream_chat`` 逐栏发 ``error``，``stream_multi`` 回退到逐栏铸造
        （多答时凭证只该铸一次，但失败语义必须与逐栏一致）。
    """
    session_id = str(session.session_id)
    async with profile.timed("prepare.mint_user_token", session=session_id):
        user_token = await env.mint_user_token(user_id)

    # 显式点名展开：``/skill:<name>`` → ``<skill>`` 块。展开要读 DB（``resolve_for_user``
    # 同步 ORM），放线程里跑；``user_id is None`` 时只认内置（后台任务/单测）。
    expanded = await sync_to_async(expand_skill_prompt, thread_sensitive=True)(user_id=user_id, text=user_message)

    prompt_text = expanded.prompt
    async with profile.timed("prepare.has_pi_session", session=session_id):
        resumed = await probe_pi_session(session_id)
    if not resumed:
        async with profile.timed("prepare.recent_history", session=session_id):
            history = await persist._recent_history(session)
        if history:
            # 无 pi session 但有历史 → 一次性补齐上下文，之后交给 pi 自己管。
            # 传**展开后**的文本：历史在前、本轮指令（含 <skill> 块）在后。
            prompt_text = render_transcript(history, expanded.prompt)
            logger.info("pi session 缺失，本轮以 transcript 回退 session=%s 历史=%s 条", session_id, len(history))

    skill_block = ""
    skill_names: list[str] = []
    not_injected: list[str] = []
    try:
        skill_block, skill_names, not_injected = await sync_to_async(_skill_index, thread_sensitive=True)(user_id)
    except (ImportError, RuntimeError):
        # 索引块是增强能力，不是准入：渲染失败不能把整轮对话弄挂（一次事故就会
        # 让律师在此期间完全无法提问）。降级为空块 + 告警，下一轮重试。
        logger.warning("技能索引块渲染失败，本轮不注入 session=%s", session_id, exc_info=True)
    if user_id is not None:
        # 每轮一行、只记名字不记正文：技能正文可能含律师的业务细节，日志不该是它的副本。
        # backend 取会话默认后端：索引块是**每用户**事实，多栏混合后端时各栏拿到的
        # 是同一块（见 ``ContextPrep.skill_block``），逐栏再记 N 行只是噪声。
        logger.info(
            "agent.skills_injected backend=%s count=%s names=%s not_injected=%s",
            getattr(session, "agent_kind", "") or "pi",
            len(skill_names),
            skill_names,
            not_injected,
        )
    return ContextPrep(
        user_token=user_token,
        prompt_text=prompt_text,
        skill_block=skill_block,
        expanded_skill=expanded.skill,
    )


async def _stamp_expanded_skill(session: AgentSession, expanded_skill: dict[str, Any]) -> None:
    """把本轮展开留痕合进**本会话最近一条 user 消息**的 ``metadata``。

    为什么要读-合并-写而不是整段覆盖：``metadata`` 里已经有评分、引用等键，直接
    ``aupdate(metadata={"expanded_skill": …})`` 会把它们全抹掉。落库失败只告警：
    留痕缺失不影响这一轮回答，更不该把已跑完的对话变成错误。
    """
    try:
        message = (
            await AgentMessage.objects.filter(session=session, role=AgentMessage.Role.USER)
            .order_by("-turn_no", "-created_at")
            .afirst()
        )
        if message is None:
            return
        metadata = dict(message.metadata or {})
        metadata["expanded_skill"] = expanded_skill
        await AgentMessage.objects.filter(pk=message.pk).aupdate(metadata=metadata)
    except DatabaseError:
        logger.warning("技能展开留痕落库失败 session=%s", session.pk, exc_info=True)


def auto_title(user_message: str) -> str:
    """会话标题候选：用户消息剥掉锚点块后的前若干字。

    侧边栏会话列表默认靠标题区分；首条消息前 30 字是最低成本的近似。
    先剥掉前端注入的锚点行（[当前业务：…]/[当前页面：…]/[已引用…：…]
    块）——否则标题变成「[当前业务：本委托] xx公司诉…」，锚点对标题
    没有信息量还挤掉正文。

    独立成函数是因为双答路径（``dual.py``）也要用它，而那条路径不经过
    ``stream_chat``——两处各抄一份必然漂移，标题口径一旦分叉就很难发现。
    """
    title_src = user_message.strip()
    for lead in ("[当前业务：", "[当前页面：", "[已引用文件：", "[已引用目录：", "[已引用选段："):
        if title_src.startswith(lead):
            title_src = title_src.split("\n", 1)[1].strip() if "\n" in title_src else ""
            break
    return title_src[:AUTO_TITLE_LIMIT]


async def record_user_message(session: AgentSession, user_message: str, *, turn_no: int = 0) -> None:
    """落库本轮用户消息（并在首轮补会话标题）。

    归编排层而不是后端（见 ``backends/base.py`` 的分工边界）：双答模式下两个
    后端跑的是**同一条**用户消息，必须只落一条——各写一次会让历史回放里出现
    两个一模一样的提问。
    """
    await AgentMessage.objects.acreate(
        session=session,
        role=AgentMessage.Role.USER,
        content=user_message,
        turn_no=turn_no,
    )
    updates: dict[str, Any] = {"updated_at": timezone.now()}
    if not session.title:
        updates["title"] = auto_title(user_message)
    await AgentSession.objects.filter(pk=session.pk).aupdate(**updates)


async def stream_chat(
    *,
    session: AgentSession,
    user_message: str,
    user_id: int | None = None,
    tool_selection: str | None = None,
    user_message_recorded: bool = False,
    persist_assistant: bool = True,
    memo: Any | None = None,
    agent_kind: str = "",
    model: str | None = None,
    api_key: str | None = None,
    context: ContextPrep | None = None,
    turn: int | None = None,
    multi_lane: bool = False,
    tool_exclude: frozenset[str] | None = None,
    subscribe_external: bool = True,
    skill_block_override: str | None = None,
) -> AsyncIterator[dict[str, Any]]:
    """跑一轮对话，产出 SSE 事件。

    ## 多轮上下文归谁管

    正常路径交给 **pi 原生 session**（``--session-dir`` + ``--session-id``）：
    pi 自己裁剪上下文并做自动 compaction，prompt cache 也能命中，长会话不再
    受 30 条 / 24000 字符的硬截断。

    **回退路径**只在一个场景触发：这个会话已有历史消息，但没有对应的 pi
    session 文件（旧数据 / 目录被清理 / 换了部署节点）。此时把历史渲染成
    transcript 附在 prompt 前，保证用户不会突然失忆；一旦这轮跑完，pi 就有了
    自己的 session 文件，下一轮自动回到正常路径。

    两种情况下本轮的助手文本与工具结果都会回写 ``AgentMessage``，那是审计与
    会话回放的权威来源。

    Args:
        user_message_recorded: 用户消息**已经**由调用方落库（双答路径
            ``dual.py`` 一次落库、两个后端共用）。``True`` 时本函数不再写用户
            消息与标题，只跑后端那一半。
        persist_assistant: 是否由本函数把助手正文写进 ``AgentMessage``。
            默认 ``True``。双答路径的**次答**传 ``False``：它的正文要带回调用方
            才能带上 ``agent_kind`` 落库，否则两条 assistant 消息里有一条永远
            缺来源标注，历史回放分不出哪条是谁。其余落库（工具结果、压缩留痕、
            ``AgentRun``）仍照旧由本函数做——那些不区分栏，必须有且只有一份。
        memo: 与 ``persist_assistant=False`` 配套的可变容器（``dual.StreamMemo``）。
            本函数把本轮 ``run_id``、已流出的正文与 metadata 写进去，供调用方
            自行落库。类型用 ``Any`` 是为了不让编排层 import 调用方模块。
        agent_kind: 本轮**用哪个后端**跑。默认空串 = 用会话自己的
            ``session.agent_kind``（单后端路径的唯一口径）。双答路径必须显式
            传：同一个会话要同时跑主/次两个后端，靠会话字段选后端会让两次调用
            都取到主后端——表现是「两栏内容一模一样」，且不会报任何错。
        model: 本轮**显式指定**的模型（用户逐栏选的）。``None`` = 由后端按自身
            默认策略选，与引入本字段前的行为逐字一致。多答时每栏各传各的，
            所以它不能是会话级属性。
        api_key: 本轮**指定**的网关 key（由 ``stream_multi`` 的轮次级分配给出）。
            ``None`` = 后端按自己的轮转口径（``_next_key``）选，与引入本参数前
            逐字一致——拿不到 key 池时就是这条路径，不能报错。多答时每栏各传
            各的，所以它也不能是会话级属性。**不得写进日志**（见 ``RunContext.api_key``）。
        context: 本轮开流前的事实（凭证 + prompt）。``None`` = 由本函数自己算，
            与引入本参数前逐字一致。多答路径传 ``stream_multi`` 算好的那一份：
            N 栏问的是同一个律师、同一个会话、同一条提问，这些事只该做一次
            （见 ``ContextPrep``）。
        turn: 本轮轮次号（:func:`next_run_turn` 的产物）。``None`` = 本函数自己
            取一次（单栏路径）。多答路径**必须**传入算好的同一个值：各栏各自
            取号会让同一轮的三栏拿到不同 turn，前端无法把它们认成一次提问。
        skill_block_override: 发布前试跑用的技能块：非 ``None`` 时后端只注它，
            连 ``isolated=True`` 的强制空块也绕过（见 ``RunContext.skill_block_override``）。
            常规对话恒为 ``None``，行为与引入本参数前逐字一致。
    """
    # 先确保内置后端已注册（幂等）：注册表是进程内全局状态，可能被清空过；
    # 取后端之前补一次，比依赖「app 启动时那一次」稳得多（见 builtin 模块说明）。
    ensure_registered()

    # 后端按会话的 ``agent_kind`` 选（模型字段已在 AgentSession 上，历史数据回填为
    # ``pi``）。未设置 / 未识别时回落到 ``pi``：引入多后端前只有一个后端在跑，
    # 空串必须等价于引入前的行为。
    # 会话级兜底保持 pi：已有会话的 agent_kind 是历史事实，不能因为「默认后端」改了
    # 就换脑子（换了上下文就断，而且是静默的）。新会话的默认见 session_service。
    backend = get_backend(agent_kind or getattr(session, "agent_kind", "") or "pi")

    prep_started = time.perf_counter()
    # 先铸身份凭证再接受消息：铸不出（用户被删/停用）就整轮拒绝，
    # 不能让工具退回超管服务账号执行。
    #
    # 多答路径由调用方把算好的那份传进来（``context``）：同一轮 N 栏是同一个
    # 律师的同一条提问，各铸一次只是把同一条 user 查询排队 N 遍。
    if context is None:
        try:
            context = await prepare_context(session=session, user_id=user_id, user_message=user_message)
        except Exception as exc:
            logger.exception("为用户 %s 铸造 agent 凭证失败，拒绝本轮对话", user_id)
            # 投影而不是手写：这个 code（``auth_failed``）是前端「该重新登录还是
            # 找管理员」的唯一依据，手写一份就多一处拼写会漂。
            # 不把 ``str(exc)`` 塞进 reason：异常原文可能内嵌堆栈/上游 HTML 错误页，
            # 顺着 SSE 推给浏览器就是 py/stack-trace-exposure（本仓库门禁阈值 0）。
            # 分类由 ``code=auth_failed`` 承载（前端只认它），原文由上一行 logger.exception 留档。
            yield project(AuthFailedError(reason="准备执行身份时失败，详见服务端日志"), agent=backend.kind)
            return

    session_id = str(session.session_id)
    user_token = context.user_token
    prompt_text = context.prompt_text

    # 轮次号必须**先于**用户消息落库算出来：用户消息也要带本轮号，否则转录分组
    # 只能回到「一段连续非 user 算一轮」的推断（PIT 级脆弱判据）。
    # 一轮只 INCR 一次，run_id 复用同一个值。
    turn_no = turn if turn is not None else await next_run_turn(session_id)
    if not user_message_recorded:
        async with profile.timed("stream.record_user_message", agent=backend.kind, session=session_id):
            await record_user_message(session, user_message, turn_no=turn_no)
    # 展开留痕：紧跟在 user 消息落库之后（已验证该行存在）——提前到
    # ``prepare_context`` 里写会写错行（那时本轮 user 消息还没建，最近一条是上一轮的）。
    # 留痕不改 ``content``：审计要看到律师原话，而不是展开后的 <skill> 块。
    if context.expanded_skill is not None:
        await _stamp_expanded_skill(session, context.expanded_skill)

    bus = get_bus()
    # 多栏并答时**只有编排层**订阅总线（``subscribe_external=False``）：
    # 各栏再各订阅一次的话，同一条 ``approval_request`` 会被投进 4 个队列
    # （3 栏 + 编排层），前端就收到 4 张一模一样的审批卡（真机实测。
    # 2026-11-21）。单栏与直接调用方保持原行为。
    external_queue: asyncio.Queue[dict[str, Any]] | None = None
    if subscribe_external:
        async with profile.timed("stream.bus_register", agent=backend.kind, session=session_id):
            external_queue = await bus.register(str(session.session_id))
    profile.since("stream.pre_stream_total", prep_started, agent=backend.kind, session=session_id)

    # 本轮运行 id：``{session_id}:{agent_kind}:{轮次}``，审批回调与运行记录都靠它归因。
    #
    # 轮次由 ``next_run_turn`` 取（Redis INCR，按会话）：以前恒 ``:1``，同一会话
    # 的第二轮与第一轮共用一个 run_id，前端按 run 归集用量时两轮混成一格。
    #
    # 改这个后缀是安全的，已核查全部消费者：``FACHUAN_RUN_ID`` 只被
    # ``pi/approval-gate.ts`` 原样回填进审批请求体（不做分段解析），后端
    # ``approval.py`` 按整串存库，``backend.result_for(run_id)`` / ``live_sessions``
    # 用整串做字典键。全仓没有按 ``endswith(':1')`` / ``split(':')[2]`` 的匹配，
    # 所以「后缀必须是 1」从来不是契约的一部分——真正的契约是**同一轮各栏共享
    # 一个 turn、不同轮不同 turn**。
    run_id = f"{session_id}:{backend.kind}:{turn_no}"
    if memo is not None:
        # 事件里的 run_id 与这里同源：调用方靠它把事件归到正确的栏（见 dual.py
        # 的 StreamMemo 说明），不要在两处各推导一遍。
        memo.run_id = run_id

    follow_ok = True
    cancelled = False
    # 实际使用的模型：先用**本轮显式指定**的那个（``model`` 入参），跑完若有后端
    # 回报的真实模型则覆盖它（见下方 ``result_for``）。不要在这里重新置 None——
    # 那会让「用户选了模型」在成本记录 / 助手消息 metadata 里全部变空，界面上
    # 看不到这一栏到底用了什么。
    used_model: str | None = model
    assistant_parts: list[str] = []
    output_tokens_total = 0
    input_tokens_total = 0
    # 缓存 token 单独累加，**不能**并进 input（cacheRead 是每轮重读的累计
    # 前缀，累加会严重虚高）。详情见 AgentRun.cache_read_tokens 注释。
    cache_read_total = 0
    cache_write_total = 0
    tool_calls_total = 0
    # 上下文水位（轮结束、pi 关闭前取一次；拿不到保持 None，不编造 0）
    context_used: int | None = None
    context_total: int | None = None
    error_kind = ""
    started = time.monotonic()
    # 本轮引用的分配器（检索类工具结果 → ``[Kn]`` 来源）。每栏各持一个：多答时
    # 三栏的正文各自编号，互不干扰（前端也按栏渲染角标）。
    citations = CitationCollector()
    # 首个 token 的时刻（TTFT 的分子）。取 ``delta`` 或 ``thinking`` 中**先到的
    # 那一个**：思考 token 已经开始计费、也在等它，只算正文会把「模型先想了 8 秒」
    # 藏起来——而那正是律师最常抱怨的「半天没反应」。
    first_token_at: float | None = None
    try:
        yield {"type": "meta", "session_id": str(session.session_id), "agent": backend.kind, "run_id": run_id}
        # 开流即告知「正在思考」：后台进程启动、排队、建连都要时间，这段时间前端
        # 只有一个静态界面。这是编排层的状态播报（与具体后端无关），所以不走后端事件。
        yield {"type": "activity", "status": "thinking", "agent": backend.kind, "run_id": run_id}
        # 直接用注册表里那个后端实例：收尾事实按 ``run_id`` 归集在它身上
        # （``result_for(run_id)``），并发会话各取各的，不会互相覆盖。
        ctx = RunContext(
            run_id=run_id,
            session=session,
            user_id=user_id,
            prompt=prompt_text,
            user_token=user_token,
            # 模型与 key 都是**本轮逐栏**的取值：前者是用户选的模型，后者是
            # ``stream_multi`` 轮次级分配的结果（None = 后端自己轮转）。两处都
            # 只透传，不在这里重新推导——重新推导会把「三栏三把 key」变成
            # 「三栏各自轮转」，撞在同一把上时只有『某栏卡 60 秒』这一个症状。
            model=model,
            api_key=api_key,
            tool_selection=tool_selection,
            # 多栏并答的写降级：本栏属于多栏时，写类工具已被从工具面摘掉
            # （``--exclude-tools``），审批层还会再拒一次。单栏两个值保持默认，
            # 与本函数引入这两个参数前的行为逐字一致。
            multi_lane=multi_lane,
            tool_exclude=tool_exclude,
            # 技能索引（本轮每用户事实，见 ``ContextPrep.skill_block``）。隔离与否
            # 不在这里判：后端拿到 ctx 后自己决定（``base.py`` 的不变量）。
            skill_block=context.skill_block,
            # 发布前试跑：绕过 isolated 的强制空块（常规路径恒 None）。
            skill_block_override=skill_block_override,
        )
        stream = backend.stream(ctx)
        # 收到 done 就别再 aclose：后端在 done 之前已经写好 ``result``（见
        # ``pi_backend`` 的 done 分支），aclose 只会白跑一遍关闭流程。
        stream_exhausted = False
        try:
            async for event in stream:
                # ``None`` 是后端「本 tick 无事件」的让出信号：借这个 tick 把外部总线
                # 里的审批事件推进来（审批不走后端事件流，见 pi_backend 模块说明）。
                while external_queue is not None:
                    try:
                        yield external_queue.get_nowait()
                    except asyncio.QueueEmpty:
                        break
                if event is None:
                    continue

                # delta 先入账再 yield：生成器停在 yield 点被打断（客户端断开）
                # 时，已送达的最后一段增量必须已经在落库缓冲里
                if event.get("type") == "delta":
                    assistant_parts.append(str(event.get("content") or ""))
                    if first_token_at is None:
                        first_token_at = time.monotonic()
                elif event.get("type") == "thinking":
                    if first_token_at is None:
                        first_token_at = time.monotonic()
                elif event.get("type") == "usage":
                    # pi 的精确计数：一轮里工具循环会产出多段 assistant，逐段累加
                    output_tokens_total += int(event.get("output_tokens") or 0)
                    input_tokens_total += int(event.get("input_tokens") or 0)
                    cache_read_total += int(event.get("cache_read_tokens") or 0)
                    cache_write_total += int(event.get("cache_write_tokens") or 0)
                elif event.get("type") == "tool_call":
                    tool_calls_total += 1
                elif event.get("type") == "compaction" and event.get("phase") == "end":
                    # 自动压缩完成：Django 消息表是回放权威，必须留痕；
                    # 否则律师重开会话只看到 AI「失忆」，没有任何解释。
                    await persist._persist_compaction_message(session, "自动压缩上下文")
                yield event
                if event.get("type") == "tool_result":
                    # 工具结果也带 agent_kind：双答时两栏的证据必须能对回各自的栏
                    await persist._persist_tool_message(session, event, backend.kind, turn_no=turn_no)
                    # 检索类工具结果 → 本轮新增引用（一次工具调用一帧，只带新增）。
                    # ``is_error`` 的结果不产引用：失败调用的 result 是错误文案，
                    # 里面不会有命中，强行解析只会造出没有来源的角标。
                    if not event.get("is_error"):
                        new_refs = citations.ingest(
                            tool_name=str(event.get("name") or ""),
                            result=event.get("result"),
                        )
                        if new_refs:
                            yield {
                                "type": "citations",
                                "citations": citations.wire(new_refs),
                                "agent": backend.kind,
                                "run_id": run_id,
                            }
                if event.get("type") == "done":
                    # 记下「已见过 done」，但**不 break**：后端生成器在 done 之后还有
                    # 代码（finally 里注销 live session、收掉挂起的 __anext__；再退
                    # 出 async with 归还进程），break 会让它永远停在 yield 点、这
                    # 些收尾一次也不会跑（表现为注册表泄漏、进程不归还）。
                    # 后端保证 done 是最后一个事件（见 ``base.py`` 契约），所以下一
                    # 轮 async for 就结束。
                    stream_exhausted = True
        finally:
            # 客户端断开 / 取消时本生成器停在 ``yield`` 点收到 GeneratorExit。后端那侧
            # 必须被关掉：它的 finally 要注销 live session、收掉挂起的 ``__anext__``，
            # ``pool.acquire`` 的退出路径才走得到取消分支
            # （close(abort_running=True) → 先 clear_queue + abort 再关进程）。
            #
            # **不能在这里 await ``stream.aclose()``**：真实 pi 进程的关闭要屏蔽外层
            # 取消、跑完整套 abort 流程（可能耗时数百毫秒），而 GeneratorExit 路径上
            # 的 await 会把「用户按停止」变成「等半天没反应」——原实现在这里也不
            # await，取消语义由 ``pool.acquire.__aexit__`` 自己担。改成派一个后台
            # 任务去关：既不会卡住前端，也不会因 GC 时机不确定而泄漏子进程。
            if not stream_exhausted:
                task = asyncio.ensure_future(stream.aclose())
                task.add_done_callback(persist._log_task_failure)

        # 收尾事实（实际模型、上下文水位）按 run_id 向后端取——异步生成器的 return
        # 值取不到，而后端在 done 之前就已把它写好。后端没实现 ``result_for`` 时
        # 保持上面的缺省值（模型 = 本轮显式指定的那个，可能为 ``None``；水位
        # ``None``），不编造数据。
        result_for = getattr(backend, "result_for", None)
        result = result_for(run_id) if result_for is not None else None
        if result is not None:
            # 实际用的模型与水位都要回写：SessionOut 如实回报（客户端不再传模型），
            # done 事件与 AgentRun 也要用同一个值（两处不一致会让成本对不上账）。
            used_model = result.model
            context_used, context_total = result.context_used, result.context_total
            if used_model and used_model != session.llm_model:
                await AgentSession.objects.filter(pk=session.pk).aupdate(llm_model=used_model)

    except (GeneratorExit, asyncio.CancelledError):
        # 客户端断开/中止：已流出的部分回答也要落库（见 finally），再按生成器语义上抛。
        # 真正把「停」传递给 pi 的动作在 ``pool.acquire`` 的取消分支（
        # close(abort_running=True) → 先 clear_queue + abort 再关进程），
        # 那里能屏蔽外层取消、保证 abort 真写得进 stdin。
        cancelled = True
        logger.info("用户中止本轮对话 session=%s，已流出的 %s 段将落库", session.pk, len(assistant_parts))
        raise
    except PiNotAvailableError as exc:
        follow_ok = False
        error_kind = "pi_unavailable"
        logger.error("pi 不可用: %s", exc)
        yield project(exc, agent=backend.kind, run_id=run_id)
    except PoolQueueTimeoutError as exc:
        # 排队超时是「忙」，不是故障：给出可读提示，不要把堆栈吐给律师
        follow_ok = False
        error_kind = "queue_timeout"
        logger.warning("agent 进程池排队超时: %s", exc)
        yield project(exc, agent=backend.kind, run_id=run_id)
    except PiError as exc:
        follow_ok = False
        error_kind = "pi_error"
        logger.error("pi 运行失败: %s", exc)
        yield project(exc, agent=backend.kind, run_id=run_id)
    except Exception as exc:
        follow_ok = False
        error_kind = "unexpected"
        logger.exception("Agent runtime 未预期错误")
        # 兜底分支也要投影：上游 SDK 的异常可能是限流/超时/上下文超限（dsh /
        # openai-agents 抛的 ``BackendError`` 就落在这里），一律说成「运行失败」
        # 会让前端丢掉「等一会儿就好」这个可执行结论。
        yield project(exc, agent=backend.kind, run_id=run_id)
    finally:
        # 注意：生成器的 finally 里**不能 yield**。客户端断开时本协程会收到
        # GeneratorExit，此时再 yield 会抛 RuntimeError（"async generator ignored
        # GeneratorExit"），表现为 SSE 被截断、curl 返回 CURLE_PARTIAL_FILE(18)。
        if external_queue is not None:
            await bus.unregister(str(session.session_id), external_queue)

        # 运行记录落库（成功 / 取消 / 出错三态都记）。
        # 只记成功等于把最贵的失败藏起来：用户按停止时模型可能已跑了大半
        # token，网关超时重试三次也是真金白银。
        await persist._record_run(
            session=session,
            user_id=user_id,
            model=used_model,
            # 这一轮**实际**用的后端（不是会话默认的那个）：多答一轮会同时落 N 条
            # 记录，缺了它账上只能按模型名反猜哪条属于哪一栏。
            agent_kind=backend.kind,
            cancelled=cancelled,
            error_kind=error_kind,
            turn_no=turn_no,
            input_tokens=input_tokens_total,
            output_tokens=output_tokens_total,
            cache_read_tokens=cache_read_total,
            cache_write_tokens=cache_write_total,
            tool_calls=tool_calls_total,
            duration_ms=int((time.monotonic() - started) * 1000),
            context_used_tokens=context_used,
            context_total_tokens=context_total,
        )

        # 助手文本落库放在 finally：取消/出错路径已流出的部分回答同样要保住
        # （用户看着三段回答按停止，重开会话不能全没）。取消路径里允许 await
        # （禁止的只是 yield）；若外层任务仍在取消中，await 会立刻抛
        # CancelledError——用 shield 保住写入，外层继续上抛、内层后台完成。
        assistant_text = "".join(assistant_parts).strip()
        # metadata 两条路径都要（落库 / 交回调用方），放在 if 外面算
        assistant_metadata: dict[str, Any] = {}
        if assistant_text:
            assistant_metadata = {"model": used_model or ""}
            if output_tokens_total > 0:
                assistant_metadata["output_tokens"] = output_tokens_total
            if cancelled or not follow_ok:
                assistant_metadata["truncated"] = True
            # “这轮怎么结束的”落库：历史回放（重开会话 / 第二天再看）拿不到 SSE，
            # 只有这一份记录。前端 ``turn-actions.canContinue`` 靠它判断「能不能
            # 继续生成」，旧实现只能看 ``truncated``，而「降级」与「取消」在
            # ``truncated`` 里长得一模一样。
            #
            # 值是 ``FinishReason``（与 ``done.finish_reason`` 同一枚举）：
            # ``cancelled`` 只可能出现在这里——客户端断开时生成器已被关闭，
            # 根本没有通道发 ``done``（见 ``sse_types.WIRE_UNREACHABLE``）。
            #
            # 多答路径（``multi.py``）会在整轮结束后用**轮级**结论覆盖这个值：
            # 单栏视角说 ok 的那一栏，可能同轮的另一栏已经炸了（轮级 = degraded）。
            # 这里先写栏级值是取消/中途失败时的兜底（那时 multi 的收尾代码跑不到）。
            assistant_metadata["finish_reason"] = _lane_finish_reason(cancelled=cancelled, follow_ok=follow_ok)
            # 分栏用量落库：``turnStatsByLane`` 原本只在内存、每轮清空，于是
            # 「哪一栏更贵更慢」这个多答的核心卖点刷新就没了。键是后端 kind
            # （多答时每栏各存自己那条消息，单栏也存一条）。
            # 四个键名与前端 ``usageByLane`` 的读取口径一致（snake_case）。
            assistant_metadata["usage_by_lane"] = {
                backend.kind: {
                    "output": output_tokens_total,
                    "input": input_tokens_total,
                    "cache_read": cache_read_total,
                    "cache_write": cache_write_total,
                }
            }
            # TTFT：拿不到（后端一个 token 事件都没发：出错 / 秒退）就不写这个键，
            # **不编造 0**——0ms 首字是一个不可能的数，写进去会污染性能对比。
            if first_token_at is not None:
                assistant_metadata["ttft_ms"] = max(0, int((first_token_at - started) * 1000))
            # 本轮全部引用落库：历史回放（刷新 / 第二天再看）拿不到 SSE 的
            # ``citations`` 帧，只有这份 metadata 能重建正文里的角标与来源卡。
            if citations.all:
                assistant_metadata["citations"] = citations.wire()
        if memo is not None:
            # 交回调用方落库（persist_assistant=False）：正文与 metadata 都要给，
            # 否则调用方只能自己重算一遍 token 与截断标记，两处必然漂移。
            memo.parts = list(assistant_parts)
            memo.metadata = assistant_metadata
        if assistant_text and not persist_assistant:
            logger.debug("助手正文交由调用方落库 session=%s run=%s", session_id, run_id)
        elif assistant_text:
            metadata = assistant_metadata
            persist_coro = AgentMessage.objects.acreate(
                session=session,
                role=AgentMessage.Role.ASSISTANT,
                content=assistant_text,
                metadata=metadata,
                # 单后端轮次也标注来源：历史回放要靠它区分双答轮次的两栏与
                # 普通轮次的一条（空串 = 引入本字段前的旧数据）。
                agent_kind=backend.kind,
                turn_no=turn_no,
            )
            if cancelled:
                task = asyncio.ensure_future(persist_coro)
                task.add_done_callback(persist._log_task_failure)
                with contextlib.suppress(asyncio.CancelledError):
                    message = await asyncio.shield(task)
                    if memo is not None:
                        memo.message_id = message.pk
            else:
                try:
                    message = await persist_coro
                    if memo is not None:
                        # 主键交回调用方：多答要用它把**轮级** finish_reason 写进
                        # 这一行（见 ``multi._stamp_turn_finish_reason``）。
                        memo.message_id = message.pk
                except Exception:
                    logger.warning("助手消息落库失败", exc_info=True)

        # 会话收尾后异步抽取个人记忆（→ pending，等律师确认）。
        #
        # 为什么在这里而不是 pi 扩展里：本系统每请求起一个 pi 进程、用完即关，
        # 取消路径走 ``abort_running=True``，``session_shutdown`` 不保证干净触发；
        # 且 pi core 等 shutdown handler 无超时，同步调 LLM 会把关闭拖死。
        # 取消的运行同样入队：用户按停止不代表前面说的偏好不值得记。
        try:
            await asyncio.shield(sync_to_async(enqueue_extraction, thread_sensitive=False)(str(session.session_id)))
        except Exception:
            logger.warning("记忆抽取入队失败（不影响对话）", exc_info=True)

    if follow_ok:
        # 线上**唯一**的那条 done（每栏各一条）。三个字段不能省：
        # - ``agent`` / ``run_id``：多栏时前端靠它们把 done 挂到正确的栏；
        # - ``finish_reason``：没有它前端只能把「正常结束」「降级」混为一谈。
        #   ``stream.py`` 只会走到这条路径（error 分支在 ``if follow_ok`` 之前),
        #   所以这里恒 ``"ok"``；``degraded`` / ``error`` 由 ``multi.py`` 发。
        #   ``cancelled`` **不可达**（``WIRE_UNREACHABLE``）：客户端断开时生成器
        #   已被关闭，根本没有通道发 done——它只出现在落库 metadata 里。
        yield {
            "type": "done",
            "session_id": str(session.session_id),
            "agent": backend.kind,
            "run_id": run_id,
            "finish_reason": "ok",
            "context_used_tokens": context_used,
            "context_total_tokens": context_total,
        }
