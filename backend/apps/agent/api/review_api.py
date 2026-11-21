"""Agent 多答评审 API —— 按需触发 rubric 判定，并支持刷新后回放。

端点前缀：``/api/v1/agent``（评审子域）。

## 为什么是独立请求，不塞进 SSE

一轮对话的收尾是按栏 ``done`` 判定的；评审要等所有栏的正文都落库之后才能
开始，而且本身可能跑几十秒（N 栏 × M 条 judge 调用）。塞进 SSE 会让"晚到的
评审"错过 turn 的收尾帧，前端只能等一个可能永远不来的事件。独立请求的
语义更干净：律师点"评审"，拿到一份完整结果；失败就是失败，不拖累对话。

## 落库与回放

每次 POST 落一行 ``AgentReview``（逐条 verdict / 立场成团存 JSON）。GET 取该轮最新的
一条——刷新页面/第二天再看都能拿回同一份结果，不需要重跑 judge。
本批只有影子模式：结果只展示，**不触发任何自动动作**。

## judge 模型：前端不许猜

``POST`` 的 ``judge_models`` 可省略，服务端按契约 §C2 四条解析（见
``services/review/judge_models.py``）。前端要提前知道能选什么，问
``GET /agent/review/options``——那里的清单来自平台真实模型表。
"""

from __future__ import annotations

from typing import Any, Literal, cast

from asgiref.sync import sync_to_async
from django.utils import timezone
from ninja import Router, Schema
from ninja.errors import HttpError
from pydantic import Field

from apps.core.security.auth import JWTOrSessionAuth

from ..models import AgentReview, AgentReviewAdoption
from ..services.adjudication.contracts import CriteriaVerdict, EquivalenceCluster, LaneReview, Review
from ..services.chat_service import MAX_ANSWERS
from ..services.review.adoption import find_owned_review, load_adoption, record_adoption
from ..services.review.judge_models import configured_judge_models, resolve_judge_models
from ..services.review.jury import run_jury
from ..services.review.rubric import DEFAULT_RUBRIC_ID, UnknownRubricError, available_rubric_ids, load_rubric
from ..services.review.store import latest_review, load_turn_answers, load_turn_models, save_review
from ..services.session_service import get_session as get_session_record
from ._helpers import _user_id
from .session_api import _available_models

router = Router(tags=["Agent 评审"], auth=JWTOrSessionAuth())


class ReviewIn(Schema):
    """触发一轮评审所需的上下文。"""

    #: 会话内第几轮（从 1 起，按 user 消息顺序计数）。
    turn: int = Field(ge=1)
    #: 参与本轮的栏（``agent_kind``）；答案从 AgentMessage 里按栏回读。
    #: 上限与多答运行时一致（``MAX_ANSWERS = 4``），避免一次评审把 judge 预算放大。
    agents: list[str] = Field(min_length=1, max_length=MAX_ANSWERS)
    #: 默认走内置合同问答 rubric（库里还没有 rubric 表单，见 ``rubric.DEFAULT_RUBRIC_ID``）。
    rubric_id: str = DEFAULT_RUBRIC_ID
    #: **可省略**：空列表 = 服务端解析（§C2 第 2/3 条），不是"用不到模型"。
    #: 之前是 ``min_length=1``，逼得前端必须猜一个模型名——猜错时评审全线
    #: ``judge_error``，而律师只看到"三栏全没评上"。
    judge_models: list[str] = Field(default_factory=list)


class ReviewOptions(Schema):
    """触发评审前前端要问的可选项（契约 §C1）。"""

    rubric_ids: list[str]
    #: 平台真实模型清单；**空列表** = 平台没有可用模型 → 前端置灰按钮并显示原因。
    judge_models: list[str]
    max_lanes: int


def _normalize_lanes(agents: list[str]) -> list[str]:
    """去重并保持请求顺序；空串栏直接丢弃（不存在的 lane 判不出任何东西）。"""
    lanes = [lane.strip() for lane in dict.fromkeys(agents) if lane.strip()]
    if not lanes:
        raise HttpError(422, "agents 不能为空")
    return lanes


def _to_contract_cluster(item: dict[str, Any]) -> EquivalenceCluster:
    """JSON 列 → 冻结 dataclass（``member_ids`` 列里是 list，契约要 tuple）。"""
    return EquivalenceCluster(
        member_ids=tuple(item.get("member_ids") or ()),
        representative_id=str(item.get("representative_id") or ""),
        tie=bool(item.get("tie")),
    )


def _to_review(record: AgentReview) -> Review:
    """把落库快照还原成契约对象（``latest_review`` 已 ``select_related`` 会话）。"""
    return Review(
        review_id=record.review_id,
        session_id=str(record.session.session_id),
        turn=record.turn,
        rubric_id=record.rubric_id,
        stage=cast(Literal["shadow"], record.stage),
        lanes=[LaneReview.model_validate(item) for item in record.lanes],
        verdicts=[CriteriaVerdict.model_validate(item) for item in record.verdicts],
        headline=record.headline,
        unverified=list(record.unverified),
        tokens=dict(record.tokens),
        clusters=[_to_contract_cluster(item) for item in record.clusters],
        clusters_error=record.clusters_error,
    )


@router.get("/review/options", response=ReviewOptions)
async def review_options(request: Any) -> ReviewOptions:
    """列出可选的 rubric 与 judge 模型（前端构造 ``/review`` 请求前先问这里）。

    ``_available_models()`` 是**同步** ORM（查 LLMProvider），必须 ``sync_to_async``——
    在事件循环里直接调会抛 ``SynchronousOnlyOperation``，而它会被降级路径吞成
    "平台没有可用模型"，症状是按钮永远置灰而日志一片安静。
    """
    return ReviewOptions(
        rubric_ids=available_rubric_ids(),
        judge_models=await sync_to_async(_available_models, thread_sensitive=True)(),
        max_lanes=MAX_ANSWERS,
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
        # §C2 第 3 条要用本轮真正跑过的模型：不为了一次查询把解析拆成两段。
        turn_models = await load_turn_models(session, payload.turn, lanes)
    except LookupError as exc:
        raise HttpError(404, "该轮次不存在") from exc

    judge_models = resolve_judge_models(
        requested=payload.judge_models,
        configured=configured_judge_models(),
        turn_models=turn_models,
    )
    if not judge_models:
        # 不编默认模型名：平台上不存在的名字只会让 21 条判定全变 judge_error。
        raise HttpError(422, "未配置评审模型")

    review = await run_jury(
        session_id=str(session.session_id),
        turn=payload.turn,
        task=task,
        answers=answers,
        rubric=rubric,
        judge_models=judge_models,
        # rubric_id 进 Review 契约（落库另有 rubric_id 列）：离线校准按版本归因
        rubric_id=payload.rubric_id,
    )
    await save_review(
        session=session,
        user_id=_user_id(request),
        rubric_id=payload.rubric_id,
        # 落实际用过的清单（而不是请求里的空列表）：复盘时才看得出这次判官是谁。
        judge_models=judge_models,
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


class AdoptIn(Schema):
    """律师显式采纳的请求体。"""

    #: 采纳的栏（``agent_kind``）；``None`` = 不归属某一栏（合并/手改，原因写 ``note``）。
    lane: str | None = Field(default=None, max_length=64)
    merged: bool = False
    note: str = Field(default="", max_length=500)


class AdoptionOut(Schema):
    """一次采纳的线上形状（POST 返回、GET 回显同一形状）。"""

    review_id: str
    lane: str | None
    merged: bool
    note: str
    adopted_at: str


class AdoptionEnvelope(Schema):
    """GET 回显；``adoption=None`` = 这轮还没采纳（不是错误）。"""

    adoption: AdoptionOut | None


def _adoption_out(review: AgentReview, record: AgentReviewAdoption) -> AdoptionOut:
    """落库行 → 契约形状；``review_id`` 用已加载对象，避免同步回查。"""
    return AdoptionOut(
        review_id=review.review_id,
        lane=record.lane,
        merged=record.merged,
        note=record.note,
        # 统一按当前时区输出：POST 的返回值来自内存对象（UTC），GET 的回显来自
        # 数据库连接（本地时区），不归一化会让"同一次采纳"在刷新前后字符串不同。
        adopted_at=timezone.localtime(record.adopted_at).isoformat(),
    )


@router.post("/reviews/{review_id}/adopt", response=AdoptionOut)
async def adopt_review(request: Any, review_id: str, payload: AdoptIn) -> AdoptionOut:
    """律师显式采纳某栏/合并结果（幂等：同一 review 重复采纳覆盖同一行）。

    影子开关**不**拦这条路由：采纳是律师点的，不是系统自动做的；
    ``FACHUAN_REVIEW_SHADOW`` 只决定将来的自动路径能否启动
    （见 ``services/review/adoption.py`` 的模块说明）。
    """
    review = await find_owned_review(review_id=review_id, user_id=_user_id(request))
    if review is None:
        # 不存在与非本人同答 404：区分开等于给了一个"这个 review_id 存在"的探针。
        raise HttpError(404, "评审不存在")
    record = await record_adoption(
        review=review,
        user_id=_user_id(request),
        lane=payload.lane,
        merged=payload.merged,
        note=payload.note,
    )
    return _adoption_out(review, record)


@router.get("/reviews/{review_id}/adoption", response=AdoptionEnvelope)
async def get_review_adoption(request: Any, review_id: str) -> AdoptionEnvelope:
    """回显当前采纳结果（刷新可回放）；未采纳时 ``adoption`` 为 ``null``。"""
    review = await find_owned_review(review_id=review_id, user_id=_user_id(request))
    if review is None:
        raise HttpError(404, "评审不存在")
    record = await load_adoption(review)
    return AdoptionEnvelope(adoption=_adoption_out(review, record) if record is not None else None)
