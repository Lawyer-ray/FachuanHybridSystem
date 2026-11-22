"""Agent 综合结论 API —— 按需触发 MoA aggregator，并支持刷新后回放。

端点前缀：``/api/v1/agent``（综合结论子域）。

## 为什么是独立请求，不塞进 SSE

一轮对话的收尾是按栏 ``done`` 判定的；综合要等所有栏的正文都落库之后才能开始，
而且要输出上千字（一次长调用，可能几十秒）。塞进 SSE 会让"晚到的结论"错过 turn
的收尾帧，前端只能等一个可能永远不来的事件。独立请求的语义更干净：律师点"综合
结论"，拿到一份完整结果；失败就是失败，不拖累对话。

## 为什么不落成 assistant 消息

转录里的 assistant 消息**等于"某一栏的回答"**（多答轮次按 ``agent_kind`` 分栏
渲染），凭空多一条会让律师以为多跑了第四个 agent。落 ``AgentSynthesis`` 独立表
（快照 + 可回放），理由与 ``AgentReview`` 相同。

## 错误口径

- 会话不存在 / 不归属当前用户 / session_id 不是 UUID：一律 404（不区分，避免
  变成"这个 id 存在"的探针）；
- 该轮次不存在：404；
- 请求没指定模型且本轮各栏都没留下模型名：422（**不猜模型名**）。
"""

from __future__ import annotations

import logging
import uuid
from typing import Any

from ninja import Router, Schema
from ninja.errors import HttpError
from pydantic import Field

from apps.core.security.auth import JWTOrSessionAuth

from ..models import AgentSynthesis
from ..services.adjudication.contracts import DroppedCandidate, Review, Synthesis, SynthesisCitation
from ..services.chat.aggregate import MAX_CANDIDATES, extract_citations, partition_candidates
from ..services.session_service import get_session as get_session_record
from ..services.synthesis.agent_runner import DEFAULT_SYNTHESIS_KIND, build_synthesis_prompt, run_synthesis_agent
from ..services.synthesis.store import (
    SYNTHESIS_AGENT_KIND,
    latest_synthesis,
    load_turn_candidates,
    resolve_model,
    save_synthesis,
    save_synthesis_message,
)
from ..services.synthesis.verify import verify_synthesis_citations
from ._helpers import _user_id

logger = logging.getLogger(__name__)

router = Router(tags=["Agent 综合结论"], auth=JWTOrSessionAuth())


class SynthesisIn(Schema):
    """触发一次综合结论所需的上下文。"""

    #: 会话内第几轮（从 1 起，按 user 消息顺序计数）。
    turn: int = Field(ge=1)
    #: 参与综合的栏（``agent_kind``）；正文从 AgentMessage 里按栏回读。
    agents: list[str] = Field(min_length=1, max_length=MAX_CANDIDATES)
    #: 执行合成的模型；空串 = 交给所选 agent 按平台默认解析。
    model: str = Field(default="", max_length=200)
    #: 用哪个 agent 运行时做综合（注册表 kind）。默认 ``pi``（见 agent_runner）。
    kind: str = Field(default=DEFAULT_SYNTHESIS_KIND, max_length=64)
    #: 是否先跑一轮评审，把"哪栏更可靠"作为取舍依据喂给综合（默认跑）。
    #:
    #: 评审一轮约 5 万 token，但它产出的分数与分歧点正是综合最需要的信息；
    #: 关掉后综合只能自己猜谁更有理。
    review: bool = True
    #: 威科凭证 ID。**可以省略**：省略时服务端自动挑本所的威科凭证
    #: （见 ``legal_research.services.credential_resolver``）。凭证 ID 是实现细节
    #: ——一张表里混着法院/OA/工商/邮箱/威科，让律师去猜 6 和 7 的区别没有意义。
    credential_id: int | None = Field(default=None, ge=1)


def _normalize_lanes(agents: list[str]) -> list[str]:
    """去重并保持请求顺序；空串栏直接丢弃（不存在的 lane 综合不出任何东西）。

    与 ``review_api._normalize_lanes`` **同口径**：``lanes_used`` 与 ``dropped``
    的并集必须等于"请求的 agents"，重复栏会让并集里出现两条同名记录。
    """
    lanes = [lane.strip() for lane in dict.fromkeys(agents) if lane.strip()]
    if not lanes:
        raise HttpError(422, "agents 不能为空")
    return lanes


def _to_synthesis(record: AgentSynthesis) -> Synthesis:
    """把落库快照还原成契约对象（``latest_synthesis`` 已 ``select_related`` 会话）。"""
    return Synthesis(
        synthesis_id=record.synthesis_id,
        session_id=str(record.session.session_id),
        turn=record.turn,
        text=record.text,
        model=record.model,
        lanes_used=list(record.lanes_used),
        dropped=[DroppedCandidate.model_validate(item) for item in record.dropped],
        citations=[SynthesisCitation.model_validate(item) for item in record.citations],
        unverified=list(record.unverified),
        tokens=dict(record.tokens),
    )


@router.post("/sessions/{session_id}/synthesize", response=Synthesis)
async def synthesize_session(request: Any, session_id: str, payload: SynthesisIn) -> Synthesis:
    """对指定轮次跑一次综合结论（独立请求，不进 SSE）。

    流程：**(可选)评审 → 组 prompt → 跑指定 agent → 核验引用 → 落 AgentSynthesis**。

    不写 assistant 消息、不写 AgentRun（口径见模块 docstring 与
    ``services/synthesis/agent_runner``）：综合是"律师点一次"的动作，不属于任何一栏。
    """
    user_id = _user_id(request)
    session = await get_session_record(session_id=session_id, user_id=user_id)
    if session is None:
        raise HttpError(404, "会话不存在")

    lanes = _normalize_lanes(payload.agents)
    try:
        task, candidates = await load_turn_candidates(session, payload.turn, lanes)
    except LookupError as exc:
        raise HttpError(404, "该轮次不存在") from exc

    # 丢弃口径与裸调用同源（empty / failed）；没有可用候选时不调模型——省一次
    # 无意义的钱，也让律师看到"这份综合是空的、原因是什么"。
    used, dropped = partition_candidates(candidates)
    if not used:
        raise HttpError(422, "没有可综合的候选：全部为空或失败")

    review_summary = ""
    if payload.review:
        review_summary = await _run_review_summary(session=session, turn=payload.turn, lanes=lanes)

    model = (payload.model or "").strip()
    if not model:
        # 没指定就交给所选 agent 按平台默认解析；解析不出也不报 422——
        # 运行时会给出它自己的可读错误。
        try:
            model = await resolve_model(session, payload.turn, "")
        except ValueError:
            model = ""

    prompt = build_synthesis_prompt(task, used, review_summary=review_summary)
    run = await run_synthesis_agent(
        session=session,
        user_id=user_id,
        kind=payload.kind,
        model=model or None,
        prompt=prompt,
        # 归因串与多答同构：会话:综合:轮次。综合不写 AgentRun，但审批与日志仍用它。
        run_id=f"{session.session_id}:synthesis:{payload.turn}",
    )

    unverified, verify_note = await verify_synthesis_citations(
        text=run.text,
        credential_id=payload.credential_id,
        user=getattr(request, "user", None),
    )
    # 有逐条未核验项时 note 是冗余的（它就是"共 N 条未通过"）；没有逐条项时
    # note 才是唯一信息（"未提供凭证" / "核验未执行：…"），必须留给前端。
    if verify_note and not unverified:
        unverified = [verify_note]

    synthesis = Synthesis(
        synthesis_id=uuid.uuid4().hex,
        session_id=str(session.session_id),
        turn=payload.turn,
        text=run.text,
        model=run.model or model,
        lanes_used=[candidate.lane for candidate in used],
        dropped=dropped,
        citations=extract_citations(used),
        unverified=unverified,
        # 不记成本（业务方口径）：综合是一次点击动作，成本归因价值低，
        # 而多一张运行记录会让「本轮几栏 / 多少钱」的统计口径变复杂。
        tokens={},
    )
    await save_synthesis(session=session, user_id=user_id, synthesis=synthesis)
    # 转录里的"第 6 栏"：写 ``agent_kind="synthesis"``，既能在历史回放/检索/后续追问里
    # 被看到，又不会被算成某一栏的回答（口径见 store.SYNTHESIS_AGENT_KIND）。
    # 失败只降级为"检索不到"，不影响已经拿到的结论——所以单独 try。
    try:
        await save_synthesis_message(session=session, synthesis=synthesis)
    except (KeyboardInterrupt, SystemExit, GeneratorExit):
        raise
    except BaseException:
        # 转录写入失败只降级为"检索不到"，不影响已经拿到的结论（见上）。
        logger.warning("综合结论写入转录失败（结论本身已落快照）session=%s", session.session_id, exc_info=True)
    return synthesis


async def _run_review_summary(*, session: Any, turn: int, lanes: list[str]) -> str:
    """跑一轮评审并把结论压成一段给综合看的文字；跑不成返回空串。

    **不阻断综合**：评审是"更准"的手段，不是前置条件。判官模型没配、评审报错，
    综合照样跑（只是少了取舍依据），这与"点了综合结果什么都没出"是两种体验。
    """
    from ..services.review.judge_models import configured_judge_models, resolve_judge_models
    from ..services.review.jury import run_jury
    from ..services.review.rubric import DEFAULT_RUBRIC_ID, load_rubric
    from ..services.review.store import load_turn_answers, load_turn_models

    try:
        rubric = load_rubric(DEFAULT_RUBRIC_ID)
        task, answers = await load_turn_answers(session, turn, lanes)
        turn_models = await load_turn_models(session, turn, lanes)
        judge_models = resolve_judge_models(requested=[], configured=configured_judge_models(), turn_models=turn_models)
        if not judge_models:
            return ""
        review = await run_jury(
            session_id=str(session.session_id),
            turn=turn,
            task=task,
            answers=answers,
            rubric=rubric,
            judge_models=judge_models,
            rubric_id=DEFAULT_RUBRIC_ID,
        )
    except (KeyboardInterrupt, SystemExit, GeneratorExit):
        raise
    except BaseException:
        # 评审失败不阻断综合（见 docstring）。用 ``BaseException`` 而非 ``Exception``
        # 是为了显式放行上面三类控制流异常；同时也是仓库棘轮的要求。
        logger.warning("综合前置评审失败（不阻断综合）session=%s turn=%s", session.session_id, turn, exc_info=True)
        return ""
    return _format_review(review)


def _format_review(review: Review) -> str:
    """评审结果 → 一段纯文本（给 agent 读，不是给前端渲染）。"""
    lines: list[str] = []
    if review.headline:
        lines.append(f"一句话结论：{review.headline}")
    for lane in review.lanes:
        score = "" if lane.score is None else f"｜得分 {lane.score:.2f}"
        line = (lane.one_line or "").strip()
        lines.append(f"- {lane.lane}{score}" + (f"｜{line}" if line else ""))
    for cluster in review.clusters:
        lanes_in = "、".join(getattr(cluster, "lanes", []) or [])
        if lanes_in:
            lines.append(f"立场相同：{lanes_in}")
    if review.unverified:
        lines.append("本轮评审提到但没核到的引用：" + "；".join(review.unverified))
    return "\n".join(lines)


@router.get("/sessions/{session_id}/synthesis", response=Synthesis)
async def get_session_synthesis(request: Any, session_id: str, turn: int | None = None) -> Synthesis:
    """回放已落库的综合结论；``turn`` 不传时取最近一次。"""
    session = await get_session_record(session_id=session_id, user_id=_user_id(request))
    if session is None:
        raise HttpError(404, "会话不存在")

    record = await latest_synthesis(session, turn)
    if record is None:
        raise HttpError(404, "该轮尚无综合结论")
    return _to_synthesis(record)
