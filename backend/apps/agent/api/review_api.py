"""Agent 多答评审 API —— 按需触发 rubric 判定，并支持刷新后回放。

端点前缀：``/api/v1/agent``（评审子域）。

## 为什么是独立请求，不塞进 SSE

一轮对话的收尾是按栏 ``done`` 判定的；评审要等所有栏的正文都落库之后才能
开始，而且本身可能跑几十秒（N 栏 × M 条 judge 调用）。塞进 SSE 会让"晚到的
评审"错过 turn 的收尾帧，前端只能等一个可能永远不来的事件。独立请求的
语义更干净：律师点"评审"，拿到一份完整结果；失败就是失败，不拖累对话。

## 落库与回放

每次 POST 落一行 ``AgentReview``（逐条 verdict 存 JSON）。GET 取该轮最新的
一条——刷新页面/第二天再看都能拿回同一份结果，不需要重跑 judge。
本批只有影子模式：结果只展示，**不触发任何自动动作**。
"""

from __future__ import annotations

from typing import Any, Literal, cast

from ninja import Router, Schema
from ninja.errors import HttpError
from pydantic import Field

from apps.core.security.auth import JWTOrSessionAuth

from ..models import AgentReview
from ..services.adjudication.contracts import CriteriaVerdict, LaneReview, Review
from ..services.review.jury import run_jury
from ..services.review.rubric import UnknownRubricError, load_rubric
from ..services.review.store import latest_review, load_turn_answers, save_review
from ..services.session_service import get_session as get_session_record
from ._helpers import _user_id

router = Router(tags=["Agent 评审"], auth=JWTOrSessionAuth())


class ReviewIn(Schema):
    """触发一轮评审所需的上下文。"""

    #: 会话内第几轮（从 1 起，按 user 消息顺序计数）。
    turn: int = Field(ge=1)
    #: 参与本轮的栏（``agent_kind``）；答案从 AgentMessage 里按栏回读。
    #: 上限与多答运行时一致（``MAX_ANSWERS = 4``），避免一次评审把 judge 预算放大。
    agents: list[str] = Field(min_length=1, max_length=4)
    rubric_id: str
    judge_models: list[str] = Field(min_length=1)


def _normalize_lanes(agents: list[str]) -> list[str]:
    """去重并保持请求顺序；空串栏直接丢弃（不存在的 lane 判不出任何东西）。"""
    lanes = [lane.strip() for lane in dict.fromkeys(agents) if lane.strip()]
    if not lanes:
        raise HttpError(422, "agents 不能为空")
    return lanes


def _to_review(record: AgentReview) -> Review:
    """把落库快照还原成契约对象（``latest_review`` 已 ``select_related`` 会话）。"""
    return Review(
        review_id=record.review_id,
        session_id=str(record.session.session_id),
        turn=record.turn,
        stage=cast(Literal["shadow"], record.stage),
        lanes=[LaneReview.model_validate(item) for item in record.lanes],
        verdicts=[CriteriaVerdict.model_validate(item) for item in record.verdicts],
        headline=record.headline,
        unverified=list(record.unverified),
        tokens=dict(record.tokens),
    )


@router.post("/sessions/{session_id}/review", response=Review)
async def review_session(request: Any, session_id: str, payload: ReviewIn) -> Review:
    """对指定轮次跑一次 rubric 评审（独立请求，不进 SSE）。"""
    session = await get_session_record(session_id=session_id, user_id=_user_id(request))
    if session is None:
        raise HttpError(404, "会话不存在")

    try:
        rubric = load_rubric(payload.rubric_id)
    except UnknownRubricError as exc:
        raise HttpError(404, f"评分标准不存在: {payload.rubric_id}") from exc

    lanes = _normalize_lanes(payload.agents)
    try:
        task, answers = await load_turn_answers(session, payload.turn, lanes)
    except LookupError as exc:
        raise HttpError(404, "该轮次不存在") from exc
    review = await run_jury(
        session_id=str(session.session_id),
        turn=payload.turn,
        task=task,
        answers=answers,
        rubric=rubric,
        judge_models=list(payload.judge_models),
    )
    await save_review(
        session=session,
        user_id=_user_id(request),
        rubric_id=payload.rubric_id,
        judge_models=list(payload.judge_models),
        review=review,
    )
    return review


@router.get("/sessions/{session_id}/review", response=Review)
async def get_session_review(request: Any, session_id: str, turn: int | None = None) -> Review:
    """回放已落库的评审结果；``turn`` 不传时取最近一次。"""
    session = await get_session_record(session_id=session_id, user_id=_user_id(request))
    if session is None:
        raise HttpError(404, "会话不存在")

    record = await latest_review(session, turn)
    if record is None:
        raise HttpError(404, "该轮尚无评审结果")
    return _to_review(record)
