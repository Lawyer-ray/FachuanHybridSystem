"""综合结论后台任务：幂等提交 / 取消 / worker 认领与心跳 / 超时 / 过期收口。

评审 🔴5 的回归：旧实现在一次同步请求里串起评审 + agent 综合 + 威科核验，必然先被
前端或反代超时掐断，后端照样跑完；律师再点一次就重复花钱，且 run_id 固定为
``会话:synthesis:轮次``，并发点击互相覆盖。

流水线本身打桩（``jobs.run_synthesis_pipeline``）；队列投递打桩（``jobs._enqueue``）；
不联网、不起 agent。worker 在测试线程里同步跑（``run_synthesis_job`` 内部 ``asyncio.run``），
它经 ``sync_to_async`` 在另一条连接上读写库，所以用事务模式（数据要提交可见）。
"""

from __future__ import annotations

import asyncio
from datetime import timedelta
from types import SimpleNamespace
from typing import Any

import pytest
from asgiref.sync import async_to_sync, sync_to_async
from django.db import IntegrityError, transaction
from django.utils import timezone
from ninja.errors import HttpError

from apps.agent.api import synthesis_api
from apps.agent.api.synthesis_api import SynthesisIn
from apps.agent.models import AgentMessage, AgentSession, AgentSynthesis
from apps.agent.models.synthesis import AgentSynthesisJob
from apps.agent.services.synthesis import jobs
from apps.organization.models import LawFirm, Lawyer

Status = AgentSynthesisJob.Status
_LANES = ["pi", "dsh"]


def _request(user: Any) -> SimpleNamespace:
    return SimpleNamespace(auth=user)


def _make_user(username: str) -> Any:
    firm = LawFirm.objects.create(name=f"综合任务测试所-{username}")
    return Lawyer.objects.create_user(
        username=username,
        password="x-test-12345678",  # pragma: allowlist secret（测试固定口令，非真实凭证）
        law_firm=firm,
    )


def _make_session(user: Any, *, empty: bool = False) -> AgentSession:
    session = AgentSession.objects.create(user=user, title="两栏综合")
    AgentMessage.objects.create(session=session, role=AgentMessage.Role.USER, content="请审查合同第 3 条")
    for lane in _LANES:
        AgentMessage.objects.create(
            session=session,
            role=AgentMessage.Role.ASSISTANT,
            agent_kind=lane,
            content="" if empty else f"【脱敏样例】{lane}：违约金建议改为日万分之五。",
            metadata={"model": "m1"},
        )
    return session


@pytest.fixture
def enqueued(monkeypatch: pytest.MonkeyPatch) -> list[str]:
    """队列投递打桩：记录投递的 job_id，不真的进 django-q。"""
    calls: list[str] = []

    def fake_enqueue(job: AgentSynthesisJob) -> str:
        calls.append(job.job_id)
        return f"q-{len(calls)}"

    monkeypatch.setattr(jobs, "_enqueue", fake_enqueue)
    return calls


@pytest.fixture
def fast_supervisor(monkeypatch: pytest.MonkeyPatch) -> None:
    """心跳调快 + 进程池释放打桩（worker 收尾会关 pi 进程池）。"""
    from apps.agent.services.chat import pool

    async def no_close() -> None:
        return None

    monkeypatch.setattr(jobs, "HEARTBEAT_SECONDS", 0.05)
    monkeypatch.setattr(pool, "close_pool", no_close)


def _submit(user: Any, session: AgentSession, **overrides: Any) -> Any:
    payload = SynthesisIn(turn=1, agents=list(_LANES), **overrides)
    return async_to_sync(synthesis_api.synthesize_session)(_request(user), str(session.session_id), payload)


# ── 提交：幂等与约束 ─────────────────────────────────────────────────────


@pytest.mark.django_db(transaction=True)
def test_submit_returns_job_immediately_and_is_idempotent_per_turn(enqueued: list[str]) -> None:
    user = _make_user("synth_job_idem")
    session = _make_session(user)

    first = _submit(user, session)
    second = _submit(user, session, model="glm53")

    assert first.status == Status.QUEUED and first.created is True
    # 重复点击：拿到的是已在跑的那一个，不新建、不重复投递（不重复花钱）
    assert second.created is False
    assert second.job_id == first.job_id
    assert enqueued == [first.job_id]
    job = AgentSynthesisJob.objects.get(session=session)
    assert job.task_id == "q-1"
    # 参数以先提交的为准
    assert job.params["model"] == ""
    assert job.params["agents"] == _LANES


@pytest.mark.django_db(transaction=True)
def test_database_allows_only_one_active_job_per_turn(enqueued: list[str]) -> None:
    """并发的两次点击都越过了"先查后建"时，由部分唯一约束兜住。"""
    user = _make_user("synth_job_constraint")
    session = _make_session(user)
    first = _submit(user, session)

    with pytest.raises(IntegrityError), transaction.atomic():
        AgentSynthesisJob.objects.create(job_id="dup", session=session, turn=1, status=Status.RUNNING)

    # 结束后的轮次可以再提交一次（"重新生成"）
    AgentSynthesisJob.objects.filter(job_id=first.job_id).update(status=Status.SUCCEEDED)
    again = _submit(user, session)
    assert again.created is True and again.job_id != first.job_id


@pytest.mark.django_db(transaction=True)
def test_submit_rejects_turn_without_usable_candidates(enqueued: list[str]) -> None:
    user = _make_user("synth_job_empty")
    session = _make_session(user, empty=True)

    with pytest.raises(HttpError) as exc:
        _submit(user, session)

    assert exc.value.status_code == 422
    assert not AgentSynthesisJob.objects.filter(session=session).exists()
    assert enqueued == []


@pytest.mark.django_db(transaction=True)
def test_enqueue_failure_marks_job_failed(monkeypatch: pytest.MonkeyPatch) -> None:
    def broken_enqueue(_job: AgentSynthesisJob) -> str:
        raise ConnectionError("redis down")

    monkeypatch.setattr(jobs, "_enqueue", broken_enqueue)
    user = _make_user("synth_job_enqueue_fail")
    session = _make_session(user)

    out = _submit(user, session)

    assert out.status == Status.FAILED
    assert "队列" in out.error


@pytest.mark.django_db(transaction=True)
def test_job_of_another_session_is_404(enqueued: list[str]) -> None:
    owner = _make_user("synth_job_owner")
    intruder = _make_user("synth_job_intruder")
    session = _make_session(owner)
    other = _make_session(intruder)
    job = _submit(owner, session)

    with pytest.raises(HttpError) as exc:
        async_to_sync(synthesis_api.get_synthesis_job)(_request(intruder), str(other.session_id), job.job_id)
    assert exc.value.status_code == 404


# ── 取消 ─────────────────────────────────────────────────────────────────


@pytest.mark.django_db(transaction=True)
def test_cancel_queued_job_dequeues_and_worker_skips_it(
    enqueued: list[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    from apps.core.tasking import submission

    dequeued: list[str] = []
    monkeypatch.setattr(submission.TaskSubmissionService, "cancel", lambda _self, task_id: dequeued.append(task_id))
    ran: list[str] = []

    async def must_not_run(**_kwargs: Any) -> Any:
        ran.append("pipeline")

    monkeypatch.setattr(jobs, "run_synthesis_pipeline", must_not_run)
    user = _make_user("synth_job_cancel_queued")
    session = _make_session(user)
    job = _submit(user, session)

    out = async_to_sync(synthesis_api.cancel_synthesis_job)(_request(user), str(session.session_id), job.job_id)

    assert out.status == Status.CANCELLED
    assert dequeued == ["q-1"]
    # 队列里的消息若已被 worker 拿到：认领（queued → running）失败，什么也不做
    assert jobs.run_synthesis_job(job.job_id) == {"job_id": job.job_id, "skipped": True}
    assert ran == []


@pytest.mark.django_db(transaction=True)
def test_cancel_running_job_only_sets_flag(enqueued: list[str]) -> None:
    user = _make_user("synth_job_cancel_running")
    session = _make_session(user)
    job = _submit(user, session)
    AgentSynthesisJob.objects.filter(job_id=job.job_id).update(status=Status.RUNNING, updated_at=timezone.now())

    out = async_to_sync(synthesis_api.cancel_synthesis_job)(_request(user), str(session.session_id), job.job_id)

    # 运行中的任务在别的进程里：这里只置标志，由它在下一次心跳时自行停下
    assert out.status == Status.RUNNING
    assert out.cancel_requested is True


# ── worker ───────────────────────────────────────────────────────────────


@pytest.mark.django_db(transaction=True)
def test_worker_runs_pipeline_and_records_result(
    enqueued: list[str], fast_supervisor: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    user = _make_user("synth_job_success")
    session = _make_session(user)
    job = _submit(user, session, kind="claude-agent", review=False)
    seen: dict[str, Any] = {}

    async def fake_pipeline(*, session: Any, user_id: Any, user: Any, request: Any, run_id: str, on_stage: Any) -> Any:
        seen.update(user_pk=user.pk, user_id=user_id, request=request, run_id=run_id)
        await on_stage("synthesis")
        return await sync_to_async(AgentSynthesis.objects.create)(
            session=session, user_id=user_id, synthesis_id="syn-ok", turn=1, model="m1", text="结论[来源：pi]"
        )

    monkeypatch.setattr(jobs, "run_synthesis_pipeline", fake_pipeline)

    assert jobs.run_synthesis_job(job.job_id) == {"job_id": job.job_id, "status": Status.SUCCEEDED}

    record = AgentSynthesisJob.objects.get(job_id=job.job_id)
    assert record.status == Status.SUCCEEDED and record.stage == ""
    assert record.synthesis is not None and record.synthesis.synthesis_id == "syn-ok"
    # 后台按 user_id 重新加载发起人（不依赖 HTTP 请求对象）
    assert seen["user_pk"] == user.pk == seen["user_id"]
    assert seen["request"].kind == "claude-agent" and seen["request"].review is False
    # run_id 按任务唯一，不再是固定的「会话:synthesis:轮次」
    assert seen["run_id"] == f"{session.session_id}:synthesis:1:{job.job_id}"

    # 轮询接口在成功后带上结论
    polled = async_to_sync(synthesis_api.get_synthesis_job)(_request(user), str(session.session_id), job.job_id)
    assert polled.status == Status.SUCCEEDED
    assert polled.synthesis is not None and polled.synthesis.text == "结论[来源：pi]"
    assert polled.review is False


@pytest.mark.django_db(transaction=True)
def test_worker_stops_pipeline_when_cancel_requested(
    enqueued: list[str], fast_supervisor: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    """运行中收到取消：worker 在下一次心跳读到标志，取消流水线（CancelledError 送进去）并记 cancelled。"""
    user = _make_user("synth_job_cancel_live")
    session = _make_session(user)
    job = _submit(user, session)
    observed: list[str] = []

    async def slow_pipeline(**_kwargs: Any) -> Any:
        # 模拟"另一个进程里律师点了取消"
        await sync_to_async(AgentSynthesisJob.objects.filter(job_id=job.job_id).update)(cancel_requested=True)
        try:
            await asyncio.sleep(30)
        except asyncio.CancelledError:
            observed.append("cancelled")
            raise

    monkeypatch.setattr(jobs, "run_synthesis_pipeline", slow_pipeline)

    assert jobs.run_synthesis_job(job.job_id)["status"] == Status.CANCELLED
    assert observed == ["cancelled"], "流水线必须真的收到取消，而不是被放着跑完"
    assert AgentSynthesisJob.objects.get(job_id=job.job_id).status == Status.CANCELLED


@pytest.mark.django_db(transaction=True)
def test_worker_times_out_and_records_failure(
    enqueued: list[str], fast_supervisor: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    user = _make_user("synth_job_timeout")
    session = _make_session(user)
    job = _submit(user, session)

    async def endless(**_kwargs: Any) -> Any:
        await asyncio.sleep(30)

    monkeypatch.setattr(jobs, "run_synthesis_pipeline", endless)
    monkeypatch.setattr(jobs, "JOB_TIMEOUT_SECONDS", 0.1)

    assert jobs.run_synthesis_job(job.job_id)["status"] == Status.FAILED
    record = AgentSynthesisJob.objects.get(job_id=job.job_id)
    assert record.status == Status.FAILED and "超时" in record.error


@pytest.mark.django_db(transaction=True)
def test_worker_records_readable_failure(
    enqueued: list[str], fast_supervisor: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    from apps.core.llm.exceptions import LLMError

    user = _make_user("synth_job_fail")
    session = _make_session(user)
    job = _submit(user, session)

    async def failing(**_kwargs: Any) -> Any:
        raise LLMError("综合结论未通过校验（no_anchor），请重试或换一个 agent")

    monkeypatch.setattr(jobs, "run_synthesis_pipeline", failing)

    assert jobs.run_synthesis_job(job.job_id)["status"] == Status.FAILED
    assert "no_anchor" in AgentSynthesisJob.objects.get(job_id=job.job_id).error


@pytest.mark.django_db(transaction=True)
def test_redelivered_message_does_not_run_twice(enqueued: list[str], monkeypatch: pytest.MonkeyPatch) -> None:
    """django-q 在 worker 被杀后会重投同一条消息：已在跑的任务不能再跑一遍（重复花钱）。"""
    ran: list[str] = []

    async def must_not_run(**_kwargs: Any) -> Any:
        ran.append("pipeline")

    monkeypatch.setattr(jobs, "run_synthesis_pipeline", must_not_run)
    user = _make_user("synth_job_redeliver")
    session = _make_session(user)
    job = _submit(user, session)
    AgentSynthesisJob.objects.filter(job_id=job.job_id).update(status=Status.RUNNING, updated_at=timezone.now())

    assert jobs.run_synthesis_job(job.job_id) == {"job_id": job.job_id, "skipped": True}
    assert ran == []


# ── 过期收口与刷新恢复 ───────────────────────────────────────────────────


@pytest.mark.django_db(transaction=True)
def test_stale_running_job_is_failed_and_turn_can_be_resubmitted(enqueued: list[str]) -> None:
    """进程重启 / 被杀后心跳停了：查询时按失败收口，且不再挡住重新提交。"""
    user = _make_user("synth_job_stale")
    session = _make_session(user)
    job = _submit(user, session)
    long_ago = timezone.now() - timedelta(seconds=jobs.RUNNING_STALE_SECONDS + 60)
    AgentSynthesisJob.objects.filter(job_id=job.job_id).update(status=Status.RUNNING, updated_at=long_ago)

    latest = async_to_sync(synthesis_api.get_latest_synthesis_job)(_request(user), str(session.session_id), 1)
    assert latest.job_id == job.job_id
    assert latest.status == Status.FAILED and "中断" in latest.error

    again = _submit(user, session)
    assert again.created is True and again.job_id != job.job_id


@pytest.mark.django_db(transaction=True)
def test_latest_job_404_when_turn_never_submitted(enqueued: list[str]) -> None:
    user = _make_user("synth_job_none")
    session = _make_session(user)

    with pytest.raises(HttpError) as exc:
        async_to_sync(synthesis_api.get_latest_synthesis_job)(_request(user), str(session.session_id), 1)
    assert exc.value.status_code == 404


def test_queue_timeout_stays_below_django_q_retry() -> None:
    """队列硬超时必须小于 ``Q_CLUSTER["retry"]``，否则任务还在跑时 django-q 会重投一次。"""
    from django.conf import settings

    retry = int((getattr(settings, "Q_CLUSTER", {}) or {}).get("retry") or 1200)
    assert jobs.JOB_TIMEOUT_SECONDS < jobs.QUEUE_TASK_TIMEOUT_SECONDS < retry
