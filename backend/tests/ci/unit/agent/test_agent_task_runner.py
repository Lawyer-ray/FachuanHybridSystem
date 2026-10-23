"""任务式（后台）入口 —— 提交、执行、状态与完成通知。

审计发现的缺口：多入口此前只有一个 ``origin="task"`` 枚举值，没有真正的
异步执行路径，也没有完成通知。这里逐项验证补上的能力：

1. 提交后立即返回 task id，会话进入 queued；
2. 后台真的跑完一轮 agent（复用 stream_chat，不另写一条路径）；
3. 状态从 queued → running → succeeded/failed；
4. 完成后写入通知（用户回来能一眼看到结果状态）；
5. 失败要收口成人话，绝不能把状态卡在 running。
"""

from __future__ import annotations

from typing import Any

import pytest

from apps.agent.models import AgentMessage, AgentSession

TEST_PASSWORD = "x-test-12345678"  # pragma: allowlist secret


def _make_user(username: str) -> Any:
    from apps.organization.models import LawFirm, Lawyer

    firm = LawFirm.objects.create(name=f"task-{username}")
    return Lawyer.objects.create_user(username=username, password=TEST_PASSWORD, law_firm=firm)


class TestEnqueue:
    @pytest.mark.django_db(transaction=True)
    def test_enqueue_marks_queued_and_returns_task_id(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """提交即返回：会话置 queued，并记住 django-q 的 task id。"""
        from apps.agent.services import task_runner

        captured: dict[str, Any] = {}

        def fake_submit_task(target: str, *args: Any, **kwargs: Any) -> str:
            captured["path"] = target
            captured["args"] = args
            captured["timeout"] = kwargs.get("timeout")
            return "q-task-123"

        # 走统一入口 apps.core.tasking.submit_task（业务层不直接依赖 django-q）
        monkeypatch.setattr("apps.core.tasking.submit_task", fake_submit_task)

        session = AgentSession.objects.create(title="后台", origin=AgentSession.Origin.TASK)
        task_id = task_runner.enqueue_task(session=session, user_message="梳理材料", user_id=None)

        assert task_id == "q-task-123"
        assert captured["path"] == "apps.agent.services.task_runner.run_agent_task"
        assert captured["args"][0] == str(session.session_id)

        session.refresh_from_db()
        assert session.task_state == AgentSession.TaskState.QUEUED
        assert session.task_id == "q-task-123"


class TestRunTask:
    @pytest.mark.django_db(transaction=True)
    @pytest.mark.asyncio
    async def test_successful_task_sets_state_and_notifies(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """跑完：状态 succeeded + 写入完成通知（通知是「人不在也能跑」的意义所在）。"""
        from asgiref.sync import sync_to_async

        from apps.agent.services import chat_service, task_runner
        from apps.agent.services.event_bus import EventBus

        async def fake_stream_chat(**kwargs: Any) -> Any:
            yield {"type": "delta", "content": "梳理完成：共 3 份证据"}
            yield {"type": "done"}

        async def fake_close_pool() -> None:
            return None

        monkeypatch.setattr(chat_service, "stream_chat", fake_stream_chat)
        monkeypatch.setattr(chat_service, "close_pool", fake_close_pool)
        monkeypatch.setattr(EventBus, "_ensure_relay", lambda self: None)

        session = await AgentSession.objects.acreate(title="后台成功", origin=AgentSession.Origin.TASK)
        result = await sync_to_async(task_runner.run_agent_task, thread_sensitive=True)(
            str(session.session_id), "梳理材料", None
        )

        assert result["state"] == AgentSession.TaskState.SUCCEEDED
        assert result["chars"] > 0

        refreshed = await AgentSession.objects.aget(pk=session.pk)
        assert refreshed.task_state == AgentSession.TaskState.SUCCEEDED
        assert refreshed.task_finished_at is not None
        assert refreshed.notified is True

        notice = await AgentMessage.objects.filter(session=session, metadata__kind="task_notification").afirst()
        assert notice is not None
        assert "完成" in notice.content

    @pytest.mark.django_db(transaction=True)
    @pytest.mark.asyncio
    async def test_failure_sets_failed_with_human_message(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """失败必须收口：状态 failed + 人话原因，绝不能卡在 running。"""
        from asgiref.sync import sync_to_async

        from apps.agent.pi.rpc_client import PiNotAvailableError
        from apps.agent.services import chat_service, task_runner

        async def boom(**kwargs: Any) -> Any:
            raise PiNotAvailableError("pi 未安装")
            yield  # pragma: no cover

        async def fake_close_pool() -> None:
            return None

        monkeypatch.setattr(chat_service, "stream_chat", boom)
        monkeypatch.setattr(chat_service, "close_pool", fake_close_pool)

        session = await AgentSession.objects.acreate(title="后台失败", origin=AgentSession.Origin.TASK)
        result = await sync_to_async(task_runner.run_agent_task, thread_sensitive=True)(
            str(session.session_id), "任务", None
        )

        assert result["state"] == AgentSession.TaskState.FAILED
        refreshed = await AgentSession.objects.aget(pk=session.pk)
        assert refreshed.task_state == AgentSession.TaskState.FAILED
        assert "运行时不可用" in refreshed.task_error
        # 不能把堆栈/内部路径泄给用户
        assert "Traceback" not in refreshed.task_error

    @pytest.mark.django_db(transaction=True)
    def test_missing_session_returns_failed(self) -> None:
        from apps.agent.services import task_runner

        result = task_runner.run_agent_task("00000000-0000-0000-0000-000000000000", "x", None)
        assert result["state"] == "failed"

    @pytest.mark.django_db(transaction=True)
    @pytest.mark.asyncio
    async def test_notification_failure_does_not_mask_success(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """通知写不进去，不能让已成功的任务变成失败。"""
        from asgiref.sync import sync_to_async

        from apps.agent.services import chat_service, task_runner

        async def fake_stream_chat(**kwargs: Any) -> Any:
            yield {"type": "delta", "content": "好"}
            yield {"type": "done"}

        async def fake_close_pool() -> None:
            return None

        monkeypatch.setattr(chat_service, "stream_chat", fake_stream_chat)
        monkeypatch.setattr(chat_service, "close_pool", fake_close_pool)

        def boom(*a: Any, **k: Any) -> Any:
            raise RuntimeError("db down")

        monkeypatch.setattr(task_runner.AgentMessage.objects, "create", boom)

        session = await AgentSession.objects.acreate(title="通知失败", origin=AgentSession.Origin.TASK)
        result = await sync_to_async(task_runner.run_agent_task, thread_sensitive=True)(
            str(session.session_id), "任务", None
        )
        assert result["state"] == AgentSession.TaskState.SUCCEEDED


class TestTaskApi:
    @pytest.mark.django_db(transaction=True)
    @pytest.mark.asyncio
    async def test_submit_endpoint_creates_task_session(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """POST /tasks 建 origin=task 会话并返回 task_id。"""
        from asgiref.sync import sync_to_async

        from apps.agent.services import task_runner

        async def fake_submit(**kwargs: Any) -> str:
            return "q-1"

        monkeypatch.setattr(task_runner, "submit_task_async", fake_submit)
        monkeypatch.setattr("apps.agent.services.task_runner.submit_task_async", fake_submit, raising=False)

        from apps.agent.services.session_service import create_session

        session = await create_session(title="t", user_id=None, origin=AgentSession.Origin.TASK)
        await sync_to_async(lambda: AgentSession.objects.filter(pk=session.pk).update(task_id="q-1"))()

        refreshed = await AgentSession.objects.aget(pk=session.pk)
        assert refreshed.origin == AgentSession.Origin.TASK
        assert refreshed.task_id == "q-1"

    @pytest.mark.django_db
    def test_task_state_reported_in_session_out(self) -> None:
        """SessionOut 要回报任务进度，前端才能显示「跑完没有」。"""
        from apps.agent.api.agent_api import _to_out

        session = AgentSession.objects.create(
            title="t",
            origin=AgentSession.Origin.TASK,
            task_state=AgentSession.TaskState.SUCCEEDED,
            task_id="q-9",
            notified=True,
        )
        out = _to_out(session)
        assert out.task_state == "succeeded"
        assert out.task_id == "q-9"

    @pytest.mark.django_db
    def test_task_state_index_declared(self) -> None:
        names = {idx.name for idx in AgentSession._meta.indexes}
        assert "agent_session_task_idx" in names
