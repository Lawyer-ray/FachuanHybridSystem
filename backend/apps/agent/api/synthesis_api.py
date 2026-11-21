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

from typing import Any

from ninja import Router, Schema
from ninja.errors import HttpError
from pydantic import Field

from apps.core.security.auth import JWTOrSessionAuth

from ..models import AgentSynthesis
from ..services.adjudication.contracts import DroppedCandidate, Synthesis, SynthesisCitation
from ..services.chat.aggregate import MAX_CANDIDATES, synthesize
from ..services.session_service import get_session as get_session_record
from ..services.synthesis.store import latest_synthesis, load_turn_candidates, resolve_model, save_synthesis
from ._helpers import _user_id

router = Router(tags=["Agent 综合结论"], auth=JWTOrSessionAuth())


class SynthesisIn(Schema):
    """触发一次综合结论所需的上下文。"""

    #: 会话内第几轮（从 1 起，按 user 消息顺序计数）。
    turn: int = Field(ge=1)
    #: 参与综合的栏（``agent_kind``）；正文从 AgentMessage 里按栏回读。
    agents: list[str] = Field(min_length=1, max_length=MAX_CANDIDATES)
    #: 执行合成的模型；空串 = 服务端取本轮某栏实际用过的模型（见 ``resolve_model``）。
    model: str = Field(default="", max_length=200)


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
    """对指定轮次跑一次综合结论（独立请求，不进 SSE）。"""
    user_id = _user_id(request)
    session = await get_session_record(session_id=session_id, user_id=user_id)
    if session is None:
        raise HttpError(404, "会话不存在")

    lanes = _normalize_lanes(payload.agents)
    try:
        task, candidates = await load_turn_candidates(session, payload.turn, lanes)
    except LookupError as exc:
        raise HttpError(404, "该轮次不存在") from exc
    # 只接 ValueError：``resolve_model`` 的唯一失败原因是"没有可用模型"，它必须
    # 变成 422（可操作："去请求里指定 model"），而不是 500。宽 except 基类
    # 在这里会把"我们写错了"也折成 422，让人查错方向。
    try:
        model = await resolve_model(session, payload.turn, payload.model)
    except ValueError as exc:
        raise HttpError(422, "未配置综合模型") from exc

    synthesis = await synthesize(task, candidates, model=model)
    # ``session_id`` / ``turn`` 由 API 补齐（``synthesize`` 与轮次无关，见其 docstring）。
    synthesis = synthesis.model_copy(update={"session_id": str(session.session_id), "turn": payload.turn})
    await save_synthesis(session=session, user_id=user_id, synthesis=synthesis)
    return synthesis


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
