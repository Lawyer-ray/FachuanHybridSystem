"""补充覆盖测试: core/tasking/query.py (41 missing)

覆盖: get_task_status 各分支, get_failed_task_info, cancel_task,
create_once_schedule, create_interval_schedule, create_monthly_schedule,
delete_schedules 带 func 参数等。
"""

from __future__ import annotations

from datetime import datetime
from unittest.mock import MagicMock, patch

import pytest

from apps.core.tasking.query import ScheduleQueryService, TaskQueryService

# ── TaskQueryService ──────────────────────────────────────────────


class TestTaskQueryServiceGetStatusBranches:
    """get_task_status 的 success / running / pending / not_found 分支。"""

    @pytest.fixture
    def svc(self) -> TaskQueryService:
        return TaskQueryService()

    @pytest.mark.django_db
    def test_task_found_success(self, svc: TaskQueryService) -> None:
        from django_q.models import Task

        task = Task.objects.create(
            id="task-ok-1",
            name="test.task",
            func="test.task",
            success=True,
            started=datetime(2025, 1, 1, 12, 0, 0),
            stopped=datetime(2025, 1, 1, 12, 0, 5),
        )
        result = svc.get_task_status("task-ok-1")
        assert result["status"] == "success"
        assert result["result"] == task.result
        assert result["started_at"] is not None
        assert result["finished_at"] is not None

    @pytest.mark.django_db
    def test_task_found_failure(self, svc: TaskQueryService) -> None:
        from django_q.models import Task

        Task.objects.create(
            id="task-fail-1",
            name="test.task",
            func="test.task",
            success=False,
            started=datetime(2025, 1, 1, 12, 0, 0),
            stopped=datetime(2025, 1, 1, 12, 0, 5),
        )
        result = svc.get_task_status("task-fail-1")
        assert result["status"] == "failure"

    @pytest.mark.django_db
    def test_task_running(self, svc: TaskQueryService) -> None:
        from django_q.models import Task

        Task.objects.create(
            id="task-run-1",
            name="test.task",
            func="test.task",
            success=False,
            started=datetime(2025, 1, 1, 12, 0, 0),
            stopped=datetime(2025, 1, 1, 12, 0, 1),  # DB has NOT NULL on stopped
        )
        # Simulate "running" by patching the queryset — test the logic path
        with patch.object(Task.objects, "filter") as mock_filter:
            mock_task = MagicMock()
            mock_task.success = False
            mock_task.started = datetime(2025, 1, 1, 12, 0, 0)
            mock_task.stopped = None  # Simulate running: started but not stopped
            mock_task.result = None
            mock_filter.return_value.first.return_value = mock_task
            result = svc.get_task_status("task-run-1")
            assert result["status"] == "running"

    @pytest.mark.django_db
    def test_task_pending_in_queue(self, svc: TaskQueryService) -> None:
        from django_q.models import OrmQ

        OrmQ.objects.create(key="pending-task-1", payload="{}")
        result = svc.get_task_status("pending-task-1")
        assert result["status"] == "pending"
        assert result["result"] is None
        assert result["started_at"] is None

    @pytest.mark.django_db
    def test_task_not_found(self, svc: TaskQueryService) -> None:
        result = svc.get_task_status("nonexistent-xyz")
        assert result["status"] == "not_found"


class TestTaskQueryServiceGetFailedTaskInfo:
    @pytest.fixture
    def svc(self) -> TaskQueryService:
        return TaskQueryService()

    @pytest.mark.django_db
    def test_returns_none_when_task_not_found(self, svc: TaskQueryService) -> None:
        assert svc.get_failed_task_info("no-such-task") is None

    @pytest.mark.django_db
    def test_returns_none_when_task_succeeded(self, svc: TaskQueryService) -> None:
        from django_q.models import Task

        Task.objects.create(
            id="task-success",
            name="t",
            func="f",
            success=True,
            started=datetime(2025, 1, 1),
            stopped=datetime(2025, 1, 1, 0, 1),
        )
        assert svc.get_failed_task_info("task-success") is None

    @pytest.mark.django_db
    def test_returns_none_when_stopped_is_none(self, svc: TaskQueryService) -> None:
        from django_q.models import Task

        # DB has NOT NULL on stopped, so we simulate via mock
        with patch.object(Task.objects, "filter") as mock_filter:
            mock_task = MagicMock()
            mock_task.success = False
            mock_task.stopped = None
            mock_filter.return_value.only.return_value.first.return_value = mock_task
            result = svc.get_failed_task_info("task-running")
            assert result is None

    @pytest.mark.django_db
    def test_returns_info_for_failed_task(self, svc: TaskQueryService) -> None:
        from django_q.models import Task

        stopped = datetime(2025, 6, 1, 10, 0, 0)
        Task.objects.create(
            id="task-failed",
            name="t",
            func="f",
            success=False,
            started=datetime(2025, 6, 1, 10, 0, 0),
            stopped=stopped,
            result="Traceback...",
        )
        info = svc.get_failed_task_info("task-failed")
        assert info is not None
        assert info["task_id"] == "task-failed"
        assert info["success"] is False
        assert info["result"] == "Traceback..."


class TestTaskQueryServiceCancelTask:
    @pytest.fixture
    def svc(self) -> TaskQueryService:
        return TaskQueryService()

    @pytest.mark.django_db
    def test_cancel_running_task(self, svc: TaskQueryService) -> None:
        from django_q.models import Task

        Task.objects.create(
            id="running-task",
            name="t",
            func="f",
            success=False,
            started=datetime(2025, 1, 1),
            stopped=datetime(2025, 1, 1, 0, 0, 1),
        )
        # Simulate running: started but not stopped
        with patch.object(Task.objects, "filter") as mock_filter:
            mock_task = MagicMock()
            mock_task.started = datetime(2025, 1, 1)
            mock_task.stopped = None
            mock_filter.return_value.first.return_value = mock_task
            mock_filter.return_value.delete.return_value = (0, {})
            result = svc.cancel_task("running-task")
            assert result["exists"] is True
            assert result["running"] is True
            assert result["finished"] is False

    @pytest.mark.django_db
    def test_cancel_finished_task(self, svc: TaskQueryService) -> None:
        from django_q.models import Task

        Task.objects.create(
            id="done-task",
            name="t",
            func="f",
            success=True,
            started=datetime(2025, 1, 1),
            stopped=datetime(2025, 1, 1, 0, 1),
        )
        result = svc.cancel_task("done-task")
        assert result["finished"] is True
        assert result["running"] is False

    @pytest.mark.django_db
    def test_cancel_removes_from_queue(self, svc: TaskQueryService) -> None:
        from django_q.models import OrmQ

        OrmQ.objects.create(key="queued-task", payload="{}")
        result = svc.cancel_task("queued-task")
        assert result["queue_deleted"] == 1

    @pytest.mark.django_db
    def test_cancel_nonexistent(self, svc: TaskQueryService) -> None:
        result = svc.cancel_task("no-such")
        assert result["exists"] is False
        assert result["queue_deleted"] == 0


# ── ScheduleQueryService ──────────────────────────────────────────


class TestScheduleQueryServiceExtended:
    @pytest.fixture
    def svc(self) -> ScheduleQueryService:
        return ScheduleQueryService()

    @pytest.mark.django_db
    def test_delete_schedules_by_name_and_func(self, svc: ScheduleQueryService) -> None:
        from django_q.models import Schedule

        Schedule.objects.create(
            name="my_sched",
            func="my.func",
            schedule_type=Schedule.ONCE,
        )
        count = svc.delete_schedules(name="my_sched", func="my.func")
        assert count == 1
        assert not Schedule.objects.filter(name="my_sched").exists()

    @pytest.mark.django_db
    def test_create_once_schedule(self, svc: ScheduleQueryService) -> None:
        from django_q.models import Schedule

        sched = svc.create_once_schedule(
            func="my.func",
            args="arg1",
            name="once-test",
            next_run=datetime(2025, 12, 31, 23, 59),
        )
        assert sched.name == "once-test"
        assert sched.func == "my.func"
        assert sched.schedule_type == Schedule.ONCE

    @pytest.mark.django_db
    def test_create_monthly_schedule(self, svc: ScheduleQueryService) -> None:
        from django_q.models import Schedule

        sched = svc.create_monthly_schedule(
            func="monthly.func",
            name="monthly-test",
            next_run=datetime(2025, 6, 1),
            repeats=3,
        )
        assert sched.name == "monthly-test"
        assert sched.func == "monthly.func"
        assert sched.schedule_type == Schedule.MONTHLY
        assert sched.repeats == 3

    @pytest.mark.django_db
    def test_create_interval_schedule(self, svc: ScheduleQueryService) -> None:
        from django_q.models import Schedule

        result = svc.create_interval_schedule(
            func="interval.func",
            name="int-test",
            minutes=10,
            args="a",
            repeats=5,
        )
        assert isinstance(result, str)
        assert Schedule.objects.filter(name="int-test").exists()

    @pytest.mark.django_db
    def test_create_interval_schedule_without_args_passes_none(self, svc: ScheduleQueryService) -> None:
        """无参任务不得落库任何位置的参数。

        回归：旧实现把空的 ``args`` 字符串作为第二位位置参数传给
        ``django_q.tasks.schedule(func, *args, **kwargs)``，落库成
        ``Schedule.args="''"``；触发时调度器 ``ast.literal_eval`` 得到 ``("")``，
        零参任务就报 ``takes 0 positional arguments but 1 was given``。
        """
        import ast

        from django_q.models import Schedule

        svc.create_interval_schedule(
            func="apps.agent.services.memory_tasks.dispatch_behavior_derivation",
            name="int-noargs-test",
            minutes=60,
        )
        sched = Schedule.objects.get(name="int-noargs-test")
        # 空字符串 / None 之外的值都会在触发时变成多余的位置参数
        assert not sched.args
        # 与调度器同口径复算，确认展开后是空参数表
        assert (not sched.args) or ast.literal_eval(sched.args) == ()

    @pytest.mark.django_db
    def test_create_interval_schedule_args_roundtrip(self, svc: ScheduleQueryService) -> None:
        """带参任务落库的 args 字符串能被调度器原样还原。"""
        import ast

        from django_q.models import Schedule

        svc.create_interval_schedule(
            func="interval.func",
            name="int-args-test",
            minutes=10,
            args="a",
        )
        sched = Schedule.objects.get(name="int-args-test")
        # 落库必须是源码字面量："a" 会被 literal_eval 解析成 ast.Name 而报错
        assert sched.args == "'a'", f"落库 args 必须是源码字面量，实际={sched.args!r}"
        args = ast.literal_eval(sched.args)
        if type(args) is not tuple:  # 与 django_q.scheduler 同一归一化规则
            args = (args,)
        assert args == ("a",)
