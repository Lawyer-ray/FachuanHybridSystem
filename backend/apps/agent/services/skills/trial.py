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

## 注入的是「工作区全文」而不是索引

待审技能**还不在** `resolve_for_user` 的交付面里（这正是双轨发布的意义），所以模型
那一轮即使想调 `get_agent_skill` 也取不到它（会 404）。因此试跑把**工作区正文直接
内联**进 `skill_block_override`：审批人要验的是「这段正文被模型照做之后是什么效果」，
而「索引能不能命中」是另一件事，由已发布技能在日常使用中持续验证。

代价要说清楚：**试跑验不出「自主发现」那一层**（模型会不会在合适场景自己想到读这条
技能）。它验的是指令语义。别把一次通过的试跑当成「上线一定没问题」的证明。
"""

from __future__ import annotations

import logging
import time
import uuid
from dataclasses import dataclass, field
from typing import Any

from apps.agent.models import AgentSkill

from . import flags, permissions, render
from .constants import MAX_BODY_BYTES
from .errors import SkillForbidden, SkillInvalid, SkillNotFound

logger = logging.getLogger(__name__)

#: 试跑的默认问题。刻意包含「原样输出第一条要求」：只问「你会怎么做」的话，模型
#: 完全可能凭常识答得像模像样，而根本没读到这段正文——那就白试了。
DEFAULT_QUESTION = "请先原样输出这条技能里的第一条要求，再用一句话说明你接下来会按它怎么做。"

#: 单次试跑的硬超时。审批人点一下按钮，不该让他等满一次完整工具调用（200s）。
DEFAULT_TIMEOUT_S = 90.0

#: 试跑块的首行。带「试跑」字样，和正常索引块（`## 可用技能（法穿）`）区分开：
#: 万一这段内容出现在日志/会话里，一眼能认出是试跑而不是真实配置。
TRIAL_HEADING = "## 可用技能（法穿·试跑）"


@dataclass(frozen=True)
class TrialResult:
    """试跑回执。

    ``injected`` 是**实际注入给模型的那段文字**：审批人必须能看见「我们到底让模型
    看了什么」，否则一个奇怪的回答无法归因（是技能写得不好，还是注入时拼错了）。
    """

    ok: bool
    text: str
    backend: str
    model: str | None
    duration_ms: int
    skill: dict[str, Any]
    injected: str
    tool_calls: list[str] = field(default_factory=list)
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
    """把工作区正文渲染成试跑用的注入块（含来源声明，与线上交付同一套渲染）。"""
    body = render.render_skill_body(scope=str(skill.scope), name=skill.name, title=skill.title, body=skill.body)
    return (
        f"{TRIAL_HEADING}\n"
        f"以下是本轮必须遵守的一条**待审**技能全文（尚未发布，仅本次试跑可见）：\n"
        f'<skill name="{skill.name}" scope="{skill.scope}">\n'
        f"{body}"
        f"</skill>\n"
    )


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
    block: str
    prompt: str
    backend_kind: str


def prepare_trial(*, user_id: int, key: str, question: str = "", backend_kind: str = "") -> TrialPlan:
    """同步准备：权限 + 正文 + 注入块。**只能在同步上下文（或线程里）调用。**

    Raises:
        SkillNotFound: 技能不存在，或不在该律师可见范围内。
        SkillForbidden: 没有试跑权限（既不能编辑也不能审批），或运营开关关闭。
        SkillInvalid: 正文超限。
    """
    if not flags.writes_enabled():
        # 试跑要铸律师凭证、起子进程；运营开关关闭时整条技能链都该静默，别只留它一个入口。
        raise SkillForbidden("技能写入已被运营开关关闭，请联系管理员")
    lawyer = _lawyer(user_id)
    skill = _readable_skill(user_id, key, lawyer)
    if len((skill.body or "").encode("utf-8")) > MAX_BODY_BYTES:
        raise SkillInvalid([{"field": "body", "message": f"正文超过 {MAX_BODY_BYTES // 1024} KB，无法试跑"}])
    return TrialPlan(
        user_id=user_id,
        skill_key=f"skill:{skill.pk}",
        skill_name=skill.name,
        skill_scope=str(skill.scope),
        skill_version=skill.version,
        block=build_trial_block(skill),
        prompt=(question or "").strip() or DEFAULT_QUESTION,
        backend_kind=_resolve_backend_kind(backend_kind),
    )


def _resolve_backend_kind(requested: str) -> str:
    """校验客户端指定的后端；未指定则用 ``pi``。

    必须在**准备阶段**就挡掉非法值，不能留到 ``_run`` 里 ``get()``：未注册的 kind 抛的是
    ``LookupError``，它与领域错误无关、翻译层接不住，最终表现为整个端点 500 —— 一个把
    字段拼错的请求不该让服务端 500。

    允许客户端选，是因为「换个后端会不会不一样」是审批人的真实疑问；但只允许
    **能注入技能**的后端：``tool_only`` 的那种注不进系统提示，试跑只会得到假阴性。
    """
    from apps.agent.backends import available_kinds, get

    kind = (requested or "").strip() or _default_backend_kind()
    usable = [candidate for candidate in available_kinds() if _can_inject(get, candidate)]
    if kind not in usable:
        raise SkillInvalid(
            [
                {
                    "field": "backend",
                    "message": f"{kind} 不能试跑（未注册或不支持注入技能索引）；可选：{', '.join(usable) or '无'}",
                }
            ]
        )
    return kind


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
    timeout_s: float = DEFAULT_TIMEOUT_S,
) -> TrialResult:
    """跑一次试跑并返回模型回复。

    对外是 async（调用方直接 ``await``），内部把 ORM 部分扔进线程 —— 见
    ``TrialPlan`` 的说明。

    Raises:
        SkillNotFound: 技能不存在，或不在该律师可见范围内。
        SkillForbidden: 没有试跑权限（既不能编辑也不能审批），或运营开关关闭。
        SkillInvalid: 正文超限 / 后端不支持注入。
    """
    from asgiref.sync import sync_to_async

    plan = await sync_to_async(prepare_trial, thread_sensitive=True)(
        user_id=user_id, key=key, question=question, backend_kind=backend_kind
    )
    return await _run(plan=plan, timeout_s=timeout_s)


async def _run(*, plan: TrialPlan, timeout_s: float) -> TrialResult:
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
        model=_resolved_model(backend, ctx.run_id),
        duration_ms=duration_ms,
        skill={
            "key": plan.skill_key,
            "name": plan.skill_name,
            "scope": plan.skill_scope,
            "version": plan.skill_version,
        },
        injected=plan.block,
        tool_calls=tool_calls,
        error=error,
    )
    # 只记规模，不记正文：试跑回答里可能出现律师没打算外传的业务表述。
    logger.info(
        "agent.skill_trial key=%s backend=%s ok=%s ms=%s chars=%s tools=%s",
        result.skill["key"],
        kind,
        result.ok,
        duration_ms,
        len(text),
        ",".join(tool_calls) or "-",
    )
    return result


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
