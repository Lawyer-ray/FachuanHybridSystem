"""发布前试跑：把一条**尚未发布**的技能真跑一轮，把模型的实际回复交给审批人。

## 为什么不能只给「预览」

`preview` 解决的是「这段文字渲染出来长什么样」，但审批人真正要判断的是**另一件事**：
模型读到这段指令之后会不会照着做、会不会把它误读成别的要求。这两件事只有真跑一轮
才能回答，而审批是这条链路上唯一「人挡在中间」的关口——让他闭眼点通过，前面所有
的双轨设计就白做了。

## 三个必须守住的性质

1. **不写会话历史**。试跑不是对话，落进 `AgentMessage` 会污染会话回放与审计；
   所以这里**不走 `stream_chat`**，直接消费后端事件流，一条 DB 写都没有。
2. **不碰真实会话的运行时历史**。`isolated=True` 让 pi 池用一次性临时目录 + 临时
   session，本轮结束即整体删除（见 `pi/pool.py` 的隔离根目录说明）。
3. **不可能触发写操作**。工具面钉死为 `readonly_tool_selection()`（`get_/list_/
   search_/read_/preview_` 前缀），与只读子 agent 同一份白名单——试跑绝不能在审批人
   不知情的时候真的改了东西。

## 两种注入模式（`mode`）：验「指令语义」还是验「自主发现」

- `inline`：把**工作区正文直接内联**进 `skill_block_override`。待审技能还不在
  `resolve_for_user` 的交付面里（这正是双轨发布的意义），模型那一轮就算去调
  `get_agent_skill` 也取不到（会 404）——所以块里必须明说「全文已给出，不要再去取」，
  否则模型会自作主张去读，试跑得到的是一个 404 而不是「这段指令跑起来什么效果」。
- `index`：注入**真实索引块**（`prompt_block.render_skill_block`，只放这一条），
  模型必须自己调 `get_agent_skill` 取全文。这条才验得出「自主发现」那一层，但它
  要求技能**已经可交付**（在 `resolve_for_user` 里按 key 找得到），否则 422。
- `auto`（缺省）：可交付 → `index`，否则 → `inline`。实际用了哪一层必须回传前端：
  审批人要知道自己刚才验的是哪一层，否则「通过了」这句话的含义是含糊的。

一次通过的 `inline` 试跑只说明「这段指令被模型照做了」，不说明「上线一定没问题」。
"""

from __future__ import annotations

import logging
import os
import time
import uuid
from dataclasses import dataclass, field
from typing import Any

from apps.agent.models import AgentSkill, AgentSkillTrial

from . import flags, permissions, prompt_block, render, resolve, trial_ledger
from .constants import MAX_BODY_BYTES, USER_PREFIX
from .errors import SkillForbidden, SkillInvalid, SkillNotFound

logger = logging.getLogger(__name__)

#: 试跑的默认问题。刻意包含「原样输出第一条要求」：只问「你会怎么做」的话，模型
#: 完全可能凭常识答得像模像样，而根本没读到这段正文——那就白试了。
DEFAULT_QUESTION = "请先原样输出这条技能里的第一条要求，再用一句话说明你接下来会按它怎么做。"

#: 单次试跑的默认硬超时（秒），可由 ``FACHUAN_SKILL_TRIAL_TIMEOUT_S`` 覆盖。
#:
#: **45 是给网关留余量的上限，不是拍脑袋的数字**：公网 nginx 默认
#: ``proxy_read_timeout`` 是 60 秒，服务端超时若贴着 60，网关会先一步掐断连接——
#: 审批人看到的是一个网络错误，而不是这里返回的「试跑超时」可读回执。要调到 60
#: 以上必须**同时**调网关，否则只是把「可读超时」换成「网关 504」。
DEFAULT_TIMEOUT_S = 45.0

#: 超时覆盖用的环境变量（注意与网关 ``proxy_read_timeout`` 的联动，见上）
TIMEOUT_ENV = "FACHUAN_SKILL_TRIAL_TIMEOUT_S"

#: 允许试跑的后端白名单（逗号分隔，缺省只有 ``pi``）。
#: 默认不放开的理由：「审批人真的想换个后端看看」是合理需求，但一个拼出来的
#: kind 不该能把 claude-agent / qoder / antigravity / opencode 这些可能要额外鉴权、
#: 或要另起账号的运行时拉起来。要放开就显式配这个变量。
BACKENDS_ENV = "FACHUAN_SKILL_TRIAL_BACKENDS"
DEFAULT_BACKENDS: tuple[str, ...] = ("pi",)

#: ``mode`` 三档（见模块 docstring）
MODE_AUTO = "auto"
MODE_INLINE = "inline"
MODE_INDEX = "index"
MODES: tuple[str, ...] = (MODE_AUTO, MODE_INLINE, MODE_INDEX)

#: ``inline`` 块里的一句硬话：不说它，模型会去调 ``get_agent_skill`` 取一条还没发布的
#: 技能，得到一个 404，然后交出一段与技能无关的回答。
INLINE_NO_FETCH_LINE = (
    "本技能全文已在上方给出，**不要**调用 `get_agent_skill` 去取它（它还没发布，取会失败）。"
)

#: 试跑块的首行。带「试跑」字样，和正常索引块（`## 可用技能（法穿）`）区分开：
#: 万一这段内容出现在日志/会话里，一眼能认出是试跑而不是真实配置。
TRIAL_HEADING = "## 可用技能（法穿·试跑）"

#: 工具报错只回传原因的前这么多字（正文既不落库也不回前端）
TOOL_ERROR_MESSAGE_MAX = 200

_warned: set[str] = set()


@dataclass(frozen=True)
class TrialResult:
    """试跑回执。

    ``injected`` 是**实际注入给模型的那段文字**：审批人必须能看见「我们到底让模型
    看了什么」，否则一个奇怪的回答无法归因（是技能写得不好，还是注入时拼错了）。

    ``mode`` 是**实际**用了哪一层（``auto`` 已解析成 ``inline`` / ``index``）：不
    回传它，审批人无法知道自己刚才验的是指令语义还是自主发现。``tool_errors`` 收
    失败的工具调用（如模型去取全文但 404）——没有它，审批人只能面对一个莫名其妙
    短的回复去猜原因。``trial_id`` 指向入账行（成本账）。
    """

    ok: bool
    text: str
    backend: str
    mode: str
    model: str | None
    duration_ms: int
    skill: dict[str, Any]
    injected: str
    trial_id: str
    tool_calls: list[str] = field(default_factory=list)
    tool_errors: list[dict[str, str]] = field(default_factory=list)
    error: str = ""


class _TrialSession:
    """试跑用的假会话：只为让后端拿到一个 ``session_id``。

    为什么不用真实 ``AgentSession``：试跑没有「这是哪个会话」的语义，随手挑一个会话
    会把它的 id 写进审批回调路由（`FACHUAN_SESSION_ID`）；而且试跑不该因为「你当前
    没开会话」而失败。只读工具面下没有审批回调，假 id 不会被任何人当成真会话使用。
    """

    def __init__(self) -> None:
        self.session_id = f"skill-trial-{uuid.uuid4().hex[:12]}"


def build_trial_block(skill: AgentSkill) -> str:
    """把工作区正文渲染成 ``inline`` 模式的注入块（含来源声明，与线上交付同一套渲染）。"""
    body = render.render_skill_body(scope=str(skill.scope), name=skill.name, title=skill.title, body=skill.body)
    return (
        f"{TRIAL_HEADING}\n"
        f"以下是本轮必须遵守的一条**待审**技能全文（尚未发布，仅本次试跑可见）：\n"
        f"{INLINE_NO_FETCH_LINE}\n"
        f'<skill name="{skill.name}" scope="{skill.scope}">\n'
        f"{body}"
        f"</skill>\n"
    )


def _index_block(entry: dict[str, Any]) -> str:
    """``index`` 模式的注入块：真实索引块，只放这一条。

    为什么原样用 ``render_skill_block`` 的输出、不加「试跑」前缀：这一层要验的正是
    「线上那份索引块能不能让模型自主发现并读取这条技能」。加一句话就换了被验对象，
    验过的东西便不再是线上那份。

    Raises:
        SkillInvalid: 索引块渲染为空（索引开关关闭或预算不足），这一层无从验起。
    """
    block, _not_injected = prompt_block.render_skill_block([entry])
    if not block:
        raise SkillInvalid(
            [{"field": "mode", "message": "索引块渲染为空（索引开关已关闭或预算不足），无法用 index 模式试跑"}]
        )
    return block


@dataclass(frozen=True)
class TrialPlan:
    """试跑前的只读事实（**全部从同步 ORM 取得**，见 ``prepare_trial``）。

    为什么单独做成一个值：本模块对外是 ``async`` 的，而 Django 的同步 ORM 在事件循环
    里调用会直接抛 ``SynchronousOnlyOperation``。把「查库 + 渲染」挤进一个同步函数、
    由异步入口一次性扔进线程（``sync_to_async(..., thread_sensitive=True)``），才能既
    保持公开签名是 async（调用方不用关心线程），又不把 ORM 带进事件循环。

    这个坑是**实测**出来的：写成「async 函数里直接查库」时，单元测试与真机请求都会
    500；而 ``sync_to_async`` 包一个 async 函数并不会把它挪到线程里——它只是把协程
    原样返回，于是照样在事件循环里跑同步 ORM。
    """

    user_id: int
    skill_key: str
    skill_name: str
    skill_scope: str
    skill_version: int
    #: 实际要注入的块（``inline`` 或 ``index``，见模块 docstring）
    block: str
    #: 实际用的模式（``auto`` 已解析；原样回传给前端，见 ``TrialResult.mode``）
    mode: str
    prompt: str
    backend_kind: str
    #: ORM 行：只为入账时拿外键（``reserve`` 只用它的 pk，不触发任何查询）
    skill: AgentSkill


def prepare_trial(
    *, user_id: int, key: str, question: str = "", backend_kind: str = "", mode: str = MODE_AUTO
) -> TrialPlan:
    """同步准备：权限 + 正文 + 注入块 + 后端与模式校验。**只能在同步上下文（或线程里）调用。**

    这一步**只读**：入账与限流在 ``run_trial`` 里单独做（见 ``trial_ledger``），因为
    准备失败（没权限 / 正文超限 / 后端不在白名单）不该消耗一次试跑配额。

    Raises:
        SkillNotFound: 技能不存在，或不在该律师可见范围内。
        SkillForbidden: 没有试跑权限（既不能编辑也不能审批），或运营开关关闭。
        SkillInvalid: 正文超限 / 后端不在白名单 / ``mode`` 非法或与交付状态不符。
    """
    if not flags.writes_enabled():
        # 试跑要铸律师凭证、起子进程；运营开关关闭时整条技能链都该静默，别只留它一个入口。
        raise SkillForbidden("技能写入已被运营开关关闭，请联系管理员")
    from .library import builtin_names

    lawyer = _lawyer(user_id)
    # 内置技能随代码发布、**不走审批**，本来就没有「发布前试跑」这个场景。给它一个
    # 404 会让前端以为「技能不存在」（它明明就在列表里），所以显式说清楚。
    raw = (key or "").strip()
    if raw.startswith("builtin:") or raw in builtin_names():
        raise SkillInvalid(
            [{"field": "key", "message": "内置技能随代码发布、不走审批，无需试跑（只有待发布的技能才需要）"}]
        )
    skill = _readable_skill(user_id, key, lawyer)
    if len((skill.body or "").encode("utf-8")) > MAX_BODY_BYTES:
        raise SkillInvalid([{"field": "body", "message": f"正文超过 {MAX_BODY_BYTES // 1024} KB，无法试跑"}])
    entry = _deliverable_entry(user_id, skill)
    resolved_mode = _resolve_mode(mode, entry)
    return TrialPlan(
        user_id=user_id,
        skill_key=f"{USER_PREFIX}{skill.pk}",
        skill_name=skill.name,
        skill_scope=str(skill.scope),
        skill_version=skill.version,
        block=_build_block(resolved_mode, skill, entry),
        mode=resolved_mode,
        prompt=(question or "").strip() or DEFAULT_QUESTION,
        backend_kind=_resolve_backend_kind(backend_kind),
        skill=skill,
    )


def _deliverable_entry(user_id: int, skill: AgentSkill) -> dict[str, Any] | None:
    """该技能现在是否已在**交付面**里（``resolve_for_user`` 按 key 能找到）。

    不自己判 ``status`` / ``published_revision``：影子级联会让一条 active 的技能因为
    被同名的高优先级技能顶掉而不被交付，那时 ``index`` 模式验的其实是另一条技能。
    """
    wanted = f"{USER_PREFIX}{skill.pk}"
    for entry in resolve.resolve_for_user(user_id):
        if entry["key"] == wanted:
            return entry
    return None


def _resolve_mode(requested: str, entry: dict[str, Any] | None) -> str:
    """把 ``mode`` 定成实际要用的那一层（语义见模块 docstring）。

    ``auto`` 的判据只有一条：**可交付就用 index，否则 inline**。可交付不是「已保存」，
    而是「这一轮真的会被交付给模型」——待审稿永远不是，那也正是最需要试跑的那一种。

    Raises:
        SkillInvalid: ``mode`` 非法，或在不该用 ``index`` 的时候要求 ``index``。
    """
    wanted = (requested or "").strip().lower() or MODE_AUTO
    if wanted not in MODES:
        raise SkillInvalid([{"field": "mode", "message": f"mode 只能是 {' / '.join(MODES)}"}])
    if wanted == MODE_AUTO:
        return MODE_INDEX if entry is not None else MODE_INLINE
    if wanted == MODE_INDEX and entry is None:
        # 不回退成 inline 而报 422：审批人点名要验的是「自主发现」，静默换层等于
        # 给了他一份自己没要求的证据。
        raise SkillInvalid([{"field": "mode", "message": "该技能尚未发布，无法用 index 模式试跑（改用 inline）"}])
    return wanted


def _build_block(mode: str, skill: AgentSkill, entry: dict[str, Any] | None) -> str:
    """按模式产出注入块（``index`` 只可能在 ``entry`` 非空时走到，见 ``_resolve_mode``）。"""
    if mode == MODE_INLINE or entry is None:
        return build_trial_block(skill)
    return _index_block(entry)


def _resolve_backend_kind(requested: str) -> str:
    """校验客户端指定的后端；未指定则用 ``pi``。

    必须在**准备阶段**就挡掉非法值，不能留到 ``_run`` 里 ``get()``：未注册的 kind 抛的是
    ``LookupError``，它与领域错误无关、翻译层接不住，最终表现为整个端点 500 —— 一个把
    字段拼错的请求不该让服务端 500。

    允许客户端选，是因为「换个后端会不会不一样」是审批人的真实疑问；但只允许同时
    满足三个条件的：**已注册 ∧ 能注入技能 ∧ 在 ``FACHUAN_SKILL_TRIAL_BACKENDS``
    白名单里**。``tool_only`` 的后端注不进系统提示，试跑只会得到假阴性；不在白名单
    的（默认只有 ``pi``）可能会去要另一套鉴权、甚至拉不起进程，那不是一个按钮该
    触发的事故。
    """
    from apps.agent.backends import available_kinds, get

    kind = (requested or "").strip() or _default_backend_kind()
    usable = [candidate for candidate in available_kinds() if _can_inject(get, candidate)]
    allowed = [candidate for candidate in allowed_backends() if candidate in usable]
    if kind not in allowed:
        raise SkillInvalid(
            [
                {
                    "field": "backend",
                    "message": (
                        f"{kind} 不能试跑（未注册、不支持注入技能索引，或不在试跑白名单 {BACKENDS_ENV}）；"
                        f"可选：{', '.join(allowed) or '无'}"
                    ),
                }
            ]
        )
    return kind


def allowed_backends() -> list[str]:
    """试跑白名单：``FACHUAN_SKILL_TRIAL_BACKENDS``（逗号分隔），缺省只放 ``pi``。

    缺省收紧是刻意的：把一个 kind 拼进请求不该能把 claude-agent / qoder /
    antigravity / opencode 这些要额外鉴权、或要另起账号的运行时拉起来。真要放开，
    配一个 env 即可（每个所可以自己决定信任哪些运行时）。
    """
    raw = (os.environ.get(BACKENDS_ENV) or "").strip()
    if not raw:
        return list(DEFAULT_BACKENDS)
    return [item.strip() for item in raw.split(",") if item.strip()]


def trial_timeout_s() -> float:
    """本次试跑的超时（秒）：缺省 45，``FACHUAN_SKILL_TRIAL_TIMEOUT_S`` 可覆盖。

    非法值（非数字、0、负数）回落 45 并**只告警一次**：超时值会被每一条试跑读到，
    写错一个字就会把日志刷满。调到 60 以上还要同时调网关，理由见
    ``DEFAULT_TIMEOUT_S`` 的注释。
    """
    raw = (os.environ.get(TIMEOUT_ENV) or "").strip()
    if not raw:
        return DEFAULT_TIMEOUT_S
    try:
        value = float(raw)
    except ValueError:
        _warn_once(f"{TIMEOUT_ENV}={raw!r} 不是数字，按 {DEFAULT_TIMEOUT_S} 秒处理")
        return DEFAULT_TIMEOUT_S
    if value <= 0:
        _warn_once(f"{TIMEOUT_ENV}={raw!r} 必须为正数，按 {DEFAULT_TIMEOUT_S} 秒处理")
        return DEFAULT_TIMEOUT_S
    return value


def _warn_once(message: str) -> None:
    """同一个非法配置只喊一次（理由见 ``trial_timeout_s``）。"""
    if message in _warned:
        return
    _warned.add(message)
    logger.warning("%s", message)


def _can_inject(get: Any, kind: str) -> bool:
    """该后端能不能把技能块拼进系统提示（``tool_only`` 就是不能）。"""
    try:
        return getattr(get(kind).capabilities, "skill_delivery", "tool_only") != "tool_only"
    except LookupError:  # pragma: no cover - available_kinds 已经保证在册
        return False


async def run_trial(
    *,
    user_id: int,
    key: str,
    question: str = "",
    backend_kind: str = "",
    mode: str = MODE_AUTO,
    timeout_s: float | None = None,
) -> TrialResult:
    """跑一次试跑并返回模型回复（入账顺序：``reserve`` → 跑 → ``finish``）。

    对外是 async（调用方直接 ``await``），内部把 ORM 部分扔进线程 —— 见
    ``TrialPlan`` 的说明。``timeout_s`` 缺省取 ``trial_timeout_s()``（env 可覆盖），
    显式传入则是测试与真机排障用的旁路。

    Raises:
        SkillNotFound: 技能不存在，或不在该律师可见范围内。
        SkillForbidden: 没有试跑权限（既不能编辑也不能审批），或运营开关关闭。
        SkillInvalid: 正文超限 / 后端不在试跑白名单 / ``mode`` 非法或与交付状态不符。
        SkillQuotaExceeded: 今日试跑次数已用完（429）。
    """
    from asgiref.sync import sync_to_async

    plan = await sync_to_async(prepare_trial, thread_sensitive=True)(
        user_id=user_id, key=key, question=question, backend_kind=backend_kind, mode=mode
    )
    trial = await sync_to_async(_reserve, thread_sensitive=True)(plan)
    effective_timeout = timeout_s if timeout_s is not None else trial_timeout_s()
    result: TrialResult | None = None
    try:
        result = await _run(plan=plan, timeout_s=effective_timeout, trial_id=str(trial.pk))
        return result
    finally:
        # 失败也要落：那一轮同样起了进程、烧了一次模型调用（见 ``trial_ledger``）。
        await sync_to_async(_settle, thread_sensitive=True)(trial, result)


def _reserve(plan: TrialPlan) -> AgentSkillTrial:
    """跑之前先落一行（并发点击也要计数）；超限抛 ``SkillQuotaExceeded`` → 429。"""
    return trial_ledger.reserve(user_id=plan.user_id, skill=plan.skill, backend=plan.backend_kind, mode=plan.mode)


def _settle(trial: AgentSkillTrial, result: TrialResult | None) -> None:
    """把本轮事实回填到入账行；``result is None`` 表示跑的过程中抛了未被接住的错。"""
    if result is None:
        trial_ledger.finish(
            trial,
            ok=False,
            duration_ms=0,
            response_chars=0,
            tool_calls_count=0,
            error="试跑中断（未产出回执）",
            model=None,
        )
        return
    trial_ledger.finish(
        trial,
        ok=result.ok,
        duration_ms=result.duration_ms,
        response_chars=len(result.text),
        tool_calls_count=len(result.tool_calls),
        error=result.error,
        model=result.model,
    )


async def _run(*, plan: TrialPlan, timeout_s: float, trial_id: str) -> TrialResult:
    import asyncio

    from apps.agent.backends import BackendError, RunContext, get
    from apps.agent.backends.builtin import ensure_registered
    from apps.agent.services.chat.env import mint_user_token
    from apps.agent.services.subtask import readonly_tool_selection

    ensure_registered()
    kind = plan.backend_kind
    backend = get(kind)
    token = await mint_user_token(plan.user_id)
    ctx = RunContext(
        run_id=f"skill-trial:{plan.skill_key}:{uuid.uuid4().hex[:8]}",
        session=_TrialSession(),
        user_id=plan.user_id,
        prompt=plan.prompt,
        user_token=token,
        model=None,
        tool_selection=readonly_tool_selection(),
        api_key=None,
        isolated=True,
        skill_block_override=plan.block,
    )

    started = time.perf_counter()
    chunks: list[str] = []
    tool_calls: list[str] = []
    tool_errors: list[dict[str, str]] = []
    error = ""
    try:
        async with asyncio.timeout(timeout_s):
            async for frame in backend.stream(ctx):
                if frame is None:
                    continue
                if frame.get("type") == "delta":
                    content = frame.get("content")
                    if isinstance(content, str):
                        chunks.append(content)
                elif frame.get("type") == "tool_call":
                    name = frame.get("name") or frame.get("toolName")
                    if name:
                        tool_calls.append(str(name))
                elif frame.get("type") == "tool_result" and frame.get("is_error"):
                    # 「模型去取了全文但失败」是审批人最需要看见的一类事实：没有它，
                    # 他只能面对一个莫名其妙短的回复去猜。
                    tool_errors.append(_tool_error(frame))
                elif frame.get("type") == "error":
                    error = str(frame.get("message") or frame.get("content") or "后端报错")
                    break
    except TimeoutError:
        error = f"试跑超过 {int(timeout_s)} 秒未完成，已中止"
    except BackendError as exc:
        error = str(exc)
    duration_ms = int((time.perf_counter() - started) * 1000)

    text = "".join(chunks).strip()
    result = TrialResult(
        ok=not error and bool(text),
        text=text,
        backend=kind,
        mode=plan.mode,
        model=_resolved_model(backend, ctx.run_id),
        duration_ms=duration_ms,
        skill={
            "key": plan.skill_key,
            "name": plan.skill_name,
            "scope": plan.skill_scope,
            "version": plan.skill_version,
        },
        injected=plan.block,
        trial_id=trial_id,
        tool_calls=tool_calls,
        tool_errors=tool_errors,
        error=error,
    )
    # 只记规模，不记正文：试跑回答里可能出现律师没打算外传的业务表述。
    logger.info(
        "agent.skill_trial key=%s backend=%s mode=%s ok=%s ms=%s chars=%s tools=%s tool_errors=%s",
        result.skill["key"],
        kind,
        plan.mode,
        result.ok,
        duration_ms,
        len(text),
        ",".join(tool_calls) or "-",
        len(tool_errors),
    )
    return result


def _tool_error(frame: dict[str, Any]) -> dict[str, str]:
    """一条工具报错的最小投影：工具名 + 结果前 200 字（正文既不落库也不入回执）。"""
    message = str(frame.get("result") or "").strip()[:TOOL_ERROR_MESSAGE_MAX]
    return {"tool": str(frame.get("name") or ""), "message": message or "工具执行失败（未返回错误详情）"}


def _resolved_model(backend: Any, run_id: str) -> str | None:
    """本轮实际用的模型（后端的 ``result_for`` 收尾事实里）；取不到就 ``None``，不编造。"""
    getter = getattr(backend, "result_for", None)
    if getter is None:
        return None
    try:
        result = getter(run_id)
    except (AttributeError, TypeError, ValueError):
        return None
    return getattr(result, "model", None) if result is not None else None


def _default_backend_kind() -> str:
    """试跑默认用哪个后端：``pi``（唯一一个既有审批又有完整技能注入的默认运行时）。"""
    return "pi"


def _lawyer(user_id: int) -> object:
    from apps.organization.models import Lawyer

    lawyer = Lawyer.objects.select_related("law_firm").prefetch_related("lawyer_teams").filter(pk=user_id).first()
    if lawyer is None:
        raise SkillNotFound("技能不存在")
    return lawyer


def _readable_skill(user_id: int, key: str, lawyer: object) -> AgentSkill:
    """取要试跑的那一行，并校验「能编辑或能审批」。

    作者能试跑自己的稿子，审批人能试跑待审稿——这两类之外的人没有理由让服务器替他
    起一个 LLM 进程。
    """
    from .user_skills import _resolve_skill_row

    skill = _resolve_skill_row(user_id, key)
    if not permissions.can_view(lawyer, skill):
        raise SkillNotFound("技能不存在")
    if not (permissions.can_edit(lawyer, skill) or permissions.can_review(lawyer, skill)):
        raise SkillForbidden("只有作者或审批人可以试跑")
    return skill
