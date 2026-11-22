"""Agent 综合结论 API —— 提交后台任务、轮询进度、取消、回放结论。

端点前缀：``/api/v1/agent``（综合结论子域）。

## 为什么是后台任务，不是一个同步请求

一次综合 = (可选)评审（多 judge，约 5 万 token）+ agent 综合（最多 2 次）+ 威科核验，
常常跑几分钟。同步请求会先被前端或反代超时掐断，而后端照样跑完、照样落库，律师
再点一次就重复花钱。所以 ``POST .../synthesize`` 只做校验并提交任务，立即返回任务；
前端轮询 ``GET .../synthesis/jobs/{job_id}`` 到终态。流水线见
``services/synthesis/pipeline.py``，任务的幂等 / 心跳 / 取消见 ``services/synthesis/jobs.py``。

## 为什么不塞进 SSE

一轮对话的收尾按栏 ``done`` 判定；综合要等所有栏正文落库后才能开始。塞进 SSE 会让
"晚到的结论"错过 turn 的收尾帧。

## 错误口径

- 会话不存在 / 不归属当前用户 / session_id 不是 UUID：一律 404（不区分，避免
  变成"这个 id 存在"的探针）；任务不属于该会话同样 404；
- 该轮次不存在：404；
- 本轮所有候选都为空或失败：422（不提交任务，省一次无意义的钱）；
- 运行期失败（agent 报错、超时、核验之外的异常）不走 HTTP 错误码：任务记 ``failed``
  并带一句人话原因，由轮询拿到。
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from ninja import Router, Schema
from ninja.errors import HttpError
from pydantic import Field

from apps.core.security.auth import JWTOrSessionAuth

from ..models import AgentSynthesis
from ..models.synthesis import AgentSynthesisJob
from ..services.adjudication.contracts import DroppedCandidate, Synthesis, SynthesisCitation
from ..services.chat.aggregate import MAX_CANDIDATES
from ..services.session_service import get_session as get_session_record
from ..services.synthesis.agent_runner import DEFAULT_SYNTHESIS_KIND
from ..services.synthesis.jobs import get_job, latest_job, request_cancel, submit_job
from ..services.synthesis.pipeline import NoUsableCandidatesError, SynthesisRequest, load_usable_candidates
from ..services.synthesis.store import latest_synthesis
from ._helpers import _user_id

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
    #: 是否先跑一轮评审，把"哪栏更可靠"作为取舍依据喂给综合（默认跑，约 5 万 token）。
    review: bool = True
    #: 威科凭证 ID。**可以省略**：省略时服务端自动挑本所的威科凭证
    #: （见 ``legal_research.services.credential_resolver``）。
    credential_id: int | None = Field(default=None, ge=1)


class SynthesisJobOut(Schema):
    """一次综合任务的状态（轮询用）。"""

    job_id: str
    session_id: str
    turn: int
    #: ``queued`` / ``running`` / ``succeeded`` / ``failed`` / ``cancelled``。
    status: str
    #: 运行中的阶段：``review`` / ``synthesis`` / ``verify`` / ``saving``；其余时候为空。
    stage: str
    #: 失败原因（给人看的一句话）。
    error: str
    #: 已请求取消、等待 worker 停下。
    cancel_requested: bool
    #: 这次是否先跑了评审（成功后前端据此回读评审卡）。
    review: bool
    #: 本次提交是否新建了任务（``False`` = 同轮已有进行中的任务，返回的是它）。
    created: bool = False
    created_at: datetime
    updated_at: datetime
    #: 成功时的结论；其余状态为 ``None``。
    synthesis: Synthesis | None = None


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
    """把落库快照还原成契约对象（调用方已 ``select_related`` 会话）。"""
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


def _to_job_out(job: AgentSynthesisJob, *, created: bool = False) -> SynthesisJobOut:
    """任务行 → 响应（调用方已 ``select_related`` 会话与结论）。"""
    params = job.params or {}
    return SynthesisJobOut(
        job_id=job.job_id,
        session_id=str(job.session.session_id),
        turn=job.turn,
        status=job.status,
        stage=job.stage,
        error=job.error,
        cancel_requested=job.cancel_requested,
        review=bool(params.get("review", True)),
        created=created,
        created_at=job.created_at,
        updated_at=job.updated_at,
        synthesis=_to_synthesis(job.synthesis) if job.synthesis is not None else None,
    )


async def _owned_session(request: Any, session_id: str) -> Any:
    session = await get_session_record(session_id=session_id, user_id=_user_id(request))
    if session is None:
        raise HttpError(404, "会话不存在")
    return session


@router.post("/sessions/{session_id}/synthesize", response=SynthesisJobOut)
async def synthesize_session(request: Any, session_id: str, payload: SynthesisIn) -> SynthesisJobOut:
    """提交一次综合结论任务，立即返回任务状态（不等结果）。

    同一会话同一轮已有进行中的任务时，返回那一个（``created=False``，参数以先提交的
    为准），不重复花钱。
    """
    user_id = _user_id(request)
    session = await _owned_session(request, session_id)

    lanes = _normalize_lanes(payload.agents)
    # 先在请求里做便宜的校验（只读库），坏请求当场报错，不进队列。
    try:
        await load_usable_candidates(session, payload.turn, lanes)
    except LookupError as exc:
        raise HttpError(404, "该轮次不存在") from exc
    except NoUsableCandidatesError as exc:
        raise HttpError(422, str(exc)) from exc

    job, created = await submit_job(
        session=session,
        user_id=user_id,
        request=SynthesisRequest(
            turn=payload.turn,
            lanes=lanes,
            model=(payload.model or "").strip(),
            kind=payload.kind,
            review=payload.review,
            credential_id=payload.credential_id,
        ),
    )
    return _to_job_out(job, created=created)


@router.get("/sessions/{session_id}/synthesis/jobs", response=SynthesisJobOut)
async def get_latest_synthesis_job(request: Any, session_id: str, turn: int) -> SynthesisJobOut:
    """某一轮最近一次综合任务（刷新页面后接着显示进度）；该轮没提交过时 404。"""
    session = await _owned_session(request, session_id)
    job = await latest_job(session, turn)
    if job is None:
        raise HttpError(404, "该轮尚无综合任务")
    return _to_job_out(job)


@router.get("/sessions/{session_id}/synthesis/jobs/{job_id}", response=SynthesisJobOut)
async def get_synthesis_job(request: Any, session_id: str, job_id: str) -> SynthesisJobOut:
    """轮询某个综合任务。"""
    session = await _owned_session(request, session_id)
    job = await get_job(session, job_id)
    if job is None:
        raise HttpError(404, "综合任务不存在")
    return _to_job_out(job)


@router.post("/sessions/{session_id}/synthesis/jobs/{job_id}/cancel", response=SynthesisJobOut)
async def cancel_synthesis_job(request: Any, session_id: str, job_id: str) -> SynthesisJobOut:
    """取消综合任务：排队中立即取消；运行中置取消标志，数秒内停下（轮询可见）。

    已结束的任务原样返回（取消是幂等的）。
    """
    session = await _owned_session(request, session_id)
    job = await request_cancel(session, job_id)
    if job is None:
        raise HttpError(404, "综合任务不存在")
    return _to_job_out(job)


@router.get("/sessions/{session_id}/synthesis", response=Synthesis)
async def get_session_synthesis(request: Any, session_id: str, turn: int | None = None) -> Synthesis:
    """回放已落库的综合结论；``turn`` 不传时取最近一次。"""
    session = await _owned_session(request, session_id)
    record = await latest_synthesis(session, turn)
    if record is None:
        raise HttpError(404, "该轮尚无综合结论")
    return _to_synthesis(record)
