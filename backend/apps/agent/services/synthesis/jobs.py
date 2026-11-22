"""综合结论的后台任务：提交（幂等）、查询、取消、worker 执行。

## 选型：复用 django-q（``apps.core.tasking``）

- 项目已有常驻 qcluster（生产由 launchd 托管，见 ``deploy/``），``services/task_runner``
  的后台 agent 任务也跑在它上面——同一套运维与日志；
- 进程内 ``asyncio.create_task`` 撑不住多 worker 与重启：任务跟着某个 gunicorn worker
  走，重启即丢，取消请求也可能落到另一个 worker 上。

## 状态机与兜底

``queued → running → succeeded / failed / cancelled``（见 ``AgentSynthesisJob.Status``）。

- **幂等**：同一会话同一轮同时只能有一个进行中的任务（数据库部分唯一约束）。重复提交
  返回已在跑的那一个，参数以先提交的为准；
- **认领**：worker 用 ``queued → running`` 的条件更新认领任务，认领失败就什么也不做。
  django-q 在 worker 被杀后会重投同一条消息，这一步保证不会重复花钱；
- **心跳**：运行中每 :data:`HEARTBEAT_SECONDS` 秒刷新 ``updated_at``，同时读取
  ``cancel_requested``。心跳超过 :data:`RUNNING_STALE_SECONDS` 没更新 = 进程已不在，
  查询时按失败收口；排队超过 :data:`QUEUED_STALE_SECONDS` 没人领 = 队列服务没在跑；
- **取消**：排队中直接出队并置 ``cancelled``；运行中只置 ``cancel_requested``，由跑着
  它的 worker 在下一次心跳时取消流水线（跨 worker 生效）；
- **超时**：流水线最长 :data:`JOB_TIMEOUT_SECONDS`，超时由本层截停并记失败；队列侧的
  硬超时 :data:`QUEUE_TASK_TIMEOUT_SECONDS` 略长，只在本层失灵时兜底。

关页面**不取消**任务：结果照样落库，回来能看到；重复点击已由幂等挡住。
"""

from __future__ import annotations

import asyncio
import contextlib
import logging
import uuid
from datetime import timedelta
from typing import Any

from asgiref.sync import sync_to_async
from django.db import IntegrityError, transaction
from django.utils import timezone

from ...models import AgentSession
from ...models.synthesis import AgentSynthesis, AgentSynthesisJob
from .control_flow import MUST_PROPAGATE
from .pipeline import NoUsableCandidatesError, SynthesisRequest, run_synthesis_pipeline

logger = logging.getLogger(__name__)

Status = AgentSynthesisJob.Status

#: worker 入口（django-q 按 dotted path 调用）。
WORKER_TARGET = "apps.agent.services.synthesis.jobs.run_synthesis_job"

#: 心跳 / 读取取消标志的间隔（秒）。也是"点了取消到真正停下"的最长等待。
HEARTBEAT_SECONDS = 3.0

#: 运行中超过这么久没心跳 = 进程已不在（重启 / 被杀）。
RUNNING_STALE_SECONDS = 120

#: 排队超过这么久没被领走 = 队列服务没在跑（或积压严重）。
QUEUED_STALE_SECONDS = 600

#: 流水线最长运行时间（秒）：评审 + 两次综合 + 威科核验的宽松上限。
JOB_TIMEOUT_SECONDS = 1050

#: 交给 django-q 的硬超时：比 :data:`JOB_TIMEOUT_SECONDS` 略长，只兜底。
#: 必须小于 ``Q_CLUSTER["retry"]``（默认 1200），否则 django-q 会在任务还在跑时重投一次。
QUEUE_TASK_TIMEOUT_SECONDS = 1080

_STALE_RUNNING_ERROR = "后台任务已中断（服务重启或进程退出），请重新生成"
_STALE_QUEUED_ERROR = "后台任务长时间未被处理（任务队列服务可能未启动），请稍后重试或联系管理员"
_ENQUEUE_ERROR = "后台任务队列不可用，请稍后重试或联系管理员"
_TIMEOUT_ERROR = "综合结论超时未完成，已停止；可减少参与栏或关闭「先评审」后重试"
_GENERIC_ERROR = "综合结论生成失败，请稍后重试"


# ── 查询与收口 ────────────────────────────────────────────────────────────


def _expire_stale(session: AgentSession, turn: int | None = None) -> None:
    """把心跳停掉的进行中任务收口为失败（查询与提交前调用）。"""
    now = timezone.now()
    jobs = AgentSynthesisJob.objects.filter(session=session)
    if turn is not None:
        jobs = jobs.filter(turn=turn)
    jobs.filter(status=Status.RUNNING, updated_at__lt=now - timedelta(seconds=RUNNING_STALE_SECONDS)).update(
        status=Status.FAILED, stage="", error=_STALE_RUNNING_ERROR, finished_at=now, updated_at=now
    )
    jobs.filter(status=Status.QUEUED, updated_at__lt=now - timedelta(seconds=QUEUED_STALE_SECONDS)).update(
        status=Status.FAILED, stage="", error=_STALE_QUEUED_ERROR, finished_at=now, updated_at=now
    )


def _active_job(session: AgentSession, turn: int) -> AgentSynthesisJob | None:
    return (
        AgentSynthesisJob.objects.filter(session=session, turn=turn, status__in=AgentSynthesisJob.ACTIVE_STATUSES)
        .order_by("-created_at", "-id")
        .first()
    )


def _with_relations(job_id: str) -> AgentSynthesisJob:
    return AgentSynthesisJob.objects.select_related("session", "synthesis", "synthesis__session").get(job_id=job_id)


def _get_job_sync(session: AgentSession, job_id: str) -> AgentSynthesisJob | None:
    _expire_stale(session)
    if not AgentSynthesisJob.objects.filter(session=session, job_id=job_id).exists():
        return None
    return _with_relations(job_id)


def _latest_job_sync(session: AgentSession, turn: int) -> AgentSynthesisJob | None:
    _expire_stale(session, turn)
    job = AgentSynthesisJob.objects.filter(session=session, turn=turn).order_by("-created_at", "-id").first()
    return _with_relations(job.job_id) if job is not None else None


async def get_job(session: AgentSession, job_id: str) -> AgentSynthesisJob | None:
    """取该会话下的某个任务（不属于该会话 = ``None``）。"""
    return await sync_to_async(_get_job_sync, thread_sensitive=True)(session, job_id)


async def latest_job(session: AgentSession, turn: int) -> AgentSynthesisJob | None:
    """取该会话某一轮最近一次任务（刷新页面后接着显示进度用）。"""
    return await sync_to_async(_latest_job_sync, thread_sensitive=True)(session, turn)


# ── 提交 ──────────────────────────────────────────────────────────────────


def _enqueue(job: AgentSynthesisJob) -> str:
    """投递到后台队列，返回队列任务 id（测试替换这一层）。"""
    from apps.core.tasking import submit_task

    return str(
        submit_task(
            WORKER_TARGET,
            job.job_id,
            task_name=f"agent-synthesis:{job.job_id}",
            timeout=QUEUE_TASK_TIMEOUT_SECONDS,
        )
    )


def _submit_sync(
    session: AgentSession, user_id: int | None, request: SynthesisRequest
) -> tuple[AgentSynthesisJob, bool]:
    _expire_stale(session, request.turn)
    existing = _active_job(session, request.turn)
    if existing is not None:
        return _with_relations(existing.job_id), False

    try:
        with transaction.atomic():
            job = AgentSynthesisJob.objects.create(
                job_id=uuid.uuid4().hex,
                session=session,
                user_id=user_id,
                turn=request.turn,
                status=Status.QUEUED,
                params=request.to_params(),
            )
    except IntegrityError:
        # 并发的另一次点击抢先建了进行中的任务（部分唯一约束）：返回它。
        existing = _active_job(session, request.turn)
        if existing is None:
            raise
        return _with_relations(existing.job_id), False

    try:
        task_id = _enqueue(job)
    except MUST_PROPAGATE:
        raise
    except BaseException:
        logger.warning("综合结论任务入队失败 job=%s", job.job_id, exc_info=True)
        now = timezone.now()
        AgentSynthesisJob.objects.filter(pk=job.pk, status=Status.QUEUED).update(
            status=Status.FAILED, error=_ENQUEUE_ERROR, finished_at=now, updated_at=now
        )
    else:
        AgentSynthesisJob.objects.filter(pk=job.pk).update(task_id=task_id)
    return _with_relations(job.job_id), True


async def submit_job(
    *, session: AgentSession, user_id: int | None, request: SynthesisRequest
) -> tuple[AgentSynthesisJob, bool]:
    """提交一次综合；同轮已有进行中的任务时返回它。

    Returns:
        ``(任务, 是否新建)``。
    """
    return await sync_to_async(_submit_sync, thread_sensitive=True)(session, user_id, request)


# ── 取消 ──────────────────────────────────────────────────────────────────


def _cancel_sync(session: AgentSession, job_id: str) -> AgentSynthesisJob | None:
    job = _get_job_sync(session, job_id)
    if job is None:
        return None
    now = timezone.now()
    if job.status == Status.QUEUED:
        # 先改状态再出队：worker 的认领是 ``queued → running`` 的条件更新，状态一改它就领不走。
        cancelled = AgentSynthesisJob.objects.filter(pk=job.pk, status=Status.QUEUED).update(
            status=Status.CANCELLED, cancel_requested=True, stage="", finished_at=now, updated_at=now
        )
        if cancelled and job.task_id:
            from apps.core.tasking.submission import TaskSubmissionService

            try:
                TaskSubmissionService().cancel(job.task_id)
            except MUST_PROPAGATE:
                raise
            except BaseException:
                # 出队失败无碍：状态已是 cancelled，worker 领到也只会跳过。
                logger.warning("综合结论任务出队失败（状态已置取消）job=%s", job.job_id, exc_info=True)
        if not cancelled:
            # 恰好被 worker 领走：按运行中处理。
            AgentSynthesisJob.objects.filter(pk=job.pk, status=Status.RUNNING).update(cancel_requested=True)
    elif job.status == Status.RUNNING:
        AgentSynthesisJob.objects.filter(pk=job.pk, status=Status.RUNNING).update(cancel_requested=True)
    return _with_relations(job.job_id)


async def request_cancel(session: AgentSession, job_id: str) -> AgentSynthesisJob | None:
    """请求取消（已结束的任务原样返回）；任务不属于该会话时返回 ``None``。"""
    return await sync_to_async(_cancel_sync, thread_sensitive=True)(session, job_id)


# ── worker ────────────────────────────────────────────────────────────────


def run_synthesis_job(job_id: str) -> dict[str, Any]:
    """django-q worker 入口（同步）：认领任务并跑完流水线。

    认领失败（已被取消 / 已有人在跑 / 已结束）直接返回，不做任何事——django-q 重投
    同一条消息时靠这一步避免重复花钱。本函数不向外抛业务异常：状态一律落在任务行上。
    """
    now = timezone.now()
    claimed = AgentSynthesisJob.objects.filter(job_id=job_id, status=Status.QUEUED).update(
        status=Status.RUNNING, started_at=now, updated_at=now
    )
    if not claimed:
        logger.info("综合结论任务未认领（已取消 / 已在跑 / 已结束）job=%s", job_id)
        return {"job_id": job_id, "skipped": True}
    try:
        status = asyncio.run(_supervise(job_id))
    except MUST_PROPAGATE:
        raise
    except BaseException:
        # 监督层自身出错（如心跳写库失败）：收口成失败，别让任务卡在 running 等心跳过期。
        logger.exception("综合结论任务监督异常 job=%s", job_id)
        _finish(AgentSynthesisJob.objects.get(job_id=job_id).pk, Status.FAILED, error=_GENERIC_ERROR)
        status = Status.FAILED
    return {"job_id": job_id, "status": status}


def _load_user(user_id: int | None) -> Any:
    """后台没有请求对象：按 user_id 重新加载发起人（核验与凭证解析按它判律所）。"""
    if user_id is None:
        return None
    from django.contrib.auth import get_user_model

    return get_user_model().objects.filter(pk=user_id).first()


def _heartbeat(pk: int, stage: str | None = None) -> bool:
    """刷新心跳（可选写阶段），返回是否已被请求取消。"""
    fields: dict[str, Any] = {"updated_at": timezone.now()}
    if stage is not None:
        fields["stage"] = stage
    AgentSynthesisJob.objects.filter(pk=pk, status=Status.RUNNING).update(**fields)
    return bool(AgentSynthesisJob.objects.filter(pk=pk, cancel_requested=True).exists())


def _finish(pk: int, status: str, *, error: str = "", synthesis: AgentSynthesis | None = None) -> None:
    now = timezone.now()
    AgentSynthesisJob.objects.filter(pk=pk, status=Status.RUNNING).update(
        status=status,
        stage="",
        error=error[:255],
        synthesis=synthesis,
        finished_at=now,
        updated_at=now,
    )


def _failure_message(exc: BaseException) -> str:
    """异常 → 给律师看的一句话（不泄露堆栈 / 内部路径）。"""
    from apps.core.llm.exceptions import LLMError

    if isinstance(exc, NoUsableCandidatesError):
        return str(exc)
    if isinstance(exc, LookupError):
        return "该轮次不存在"
    if isinstance(exc, LLMError):
        # agent_runner 的 LLMError 文案本身就是给人看的（"综合 agent 失败: …"）。
        return str(exc) or _GENERIC_ERROR
    return _GENERIC_ERROR


async def _supervise(job_id: str) -> str:
    """跑流水线并看着它：心跳、取消、超时都在这里；返回终态。"""
    from ..chat.pool import close_pool

    job = await AgentSynthesisJob.objects.select_related("session").aget(job_id=job_id)
    pk = job.pk
    session = job.session
    user = await sync_to_async(_load_user, thread_sensitive=True)(job.user_id)
    request = SynthesisRequest.from_params(job.turn, job.params or {})

    async def on_stage(stage: str) -> None:
        await sync_to_async(_heartbeat, thread_sensitive=True)(pk, stage)

    pipeline = asyncio.create_task(
        run_synthesis_pipeline(
            session=session,
            user_id=job.user_id,
            user=user,
            request=request,
            # 按任务唯一：并发的两次综合（不同轮）审批与日志互不覆盖。
            run_id=f"{session.session_id}:synthesis:{job.turn}:{job.job_id}",
            on_stage=on_stage,
        ),
        name=f"agent-synthesis:{job_id}",
    )
    loop = asyncio.get_running_loop()
    deadline = loop.time() + JOB_TIMEOUT_SECONDS
    stop_reason = ""
    try:
        while True:
            done, _pending = await asyncio.wait({pipeline}, timeout=HEARTBEAT_SECONDS)
            if done:
                break
            if await sync_to_async(_heartbeat, thread_sensitive=True)(pk):
                stop_reason = Status.CANCELLED
            elif loop.time() >= deadline:
                stop_reason = "timeout"
            if stop_reason:
                pipeline.cancel()
                break

        try:
            record = await pipeline
        except asyncio.CancelledError:
            if not stop_reason:
                raise  # 不是我们取消的（进程在退出）：原样上抛
            if stop_reason == Status.CANCELLED:
                logger.info("综合结论任务已取消 job=%s", job_id)
                await sync_to_async(_finish, thread_sensitive=True)(pk, Status.CANCELLED)
                return Status.CANCELLED
            logger.warning("综合结论任务超时 job=%s", job_id)
            await sync_to_async(_finish, thread_sensitive=True)(pk, Status.FAILED, error=_TIMEOUT_ERROR)
            return Status.FAILED
        except MUST_PROPAGATE:
            raise
        except BaseException as exc:
            logger.warning("综合结论任务失败 job=%s", job_id, exc_info=True)
            await sync_to_async(_finish, thread_sensitive=True)(pk, Status.FAILED, error=_failure_message(exc))
            return Status.FAILED

        await sync_to_async(_finish, thread_sensitive=True)(pk, Status.SUCCEEDED, synthesis=record)
        return Status.SUCCEEDED
    finally:
        if not pipeline.done():
            pipeline.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await pipeline
        # worker 进程长期存活：跑完释放 pi 进程池（同 services/task_runner）。
        with contextlib.suppress(OSError, RuntimeError):
            await close_pool()


__all__ = [
    "HEARTBEAT_SECONDS",
    "JOB_TIMEOUT_SECONDS",
    "QUEUED_STALE_SECONDS",
    "QUEUE_TASK_TIMEOUT_SECONDS",
    "RUNNING_STALE_SECONDS",
    "get_job",
    "latest_job",
    "request_cancel",
    "run_synthesis_job",
    "submit_job",
]
