"""Tests for core tasking query services: TaskQueryService, ScheduleQueryService, task_queue_query."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from apps.core.tasking import task_queue_query
from apps.core.tasking.query import ScheduleQueryService, TaskQueryService

# ── TaskQueryService ──


class TestTaskQueryService:
    @pytest.fixture
    def svc(self):
        return TaskQueryService()

    @pytest.mark.django_db
    def test_get_task_status_not_found(self, svc):
        result = svc.get_task_status("nonexistent-task-id")
        assert result["status"] == "not_found"
        assert result["task_id"] == "nonexistent-task-id"
        assert result["result"] is None

    @pytest.mark.django_db
    def test_get_failed_task_info_not_found(self, svc):
        result = svc.get_failed_task_info("nonexistent-task-id")
        assert result is None

    @pytest.mark.django_db
    def test_get_task_by_id_not_found(self, svc):
        result = svc.get_task_by_id("nonexistent-task-id")
        assert result is None

    @pytest.mark.django_db
    def test_cancel_task_not_found(self, svc):
        result = svc.cancel_task("nonexistent-task-id")
        assert result["exists"] is False
        assert result["queue_deleted"] == 0


# ── ScheduleQueryService ──


class TestScheduleQueryService:
    @pytest.fixture
    def svc(self):
        return ScheduleQueryService()

    @pytest.mark.django_db
    def test_schedule_exists_false(self, svc):
        assert svc.schedule_exists("nonexistent_schedule") is False

    @pytest.mark.django_db
    def test_get_schedule_by_name_not_found(self, svc):
        result = svc.get_schedule_by_name("nonexistent_schedule")
        assert result is None

    @pytest.mark.django_db
    def test_delete_schedules_empty(self, svc):
        count = svc.delete_schedules(name="nonexistent_schedule")
        assert count == 0

    @pytest.mark.django_db
    def test_delete_schedules_by_func(self, svc):
        count = svc.delete_schedules(func="nonexistent.func.path")
        assert count == 0


# ── task_queue_query.cluster_status（设置页·系统状态）──


class TestClusterStatus:
    @pytest.mark.django_db
    def test_non_redis_broker_clusters_none(self):
        """非 redis broker：clusters=None（无法探测）且不算错误。"""
        with patch("apps.core.tasking.redis_queue.is_redis_broker", return_value=False):
            data = task_queue_query.cluster_status()
        assert data["clusters"] is None
        assert data["broker_error"] is None
        assert data["queue_depth"] == 0

    @pytest.mark.django_db
    def test_redis_probe_error_degrades(self):
        """redis 连不上：clusters=None + broker_error 带异常摘要，不抛 500。"""
        with (
            patch("apps.core.tasking.redis_queue.is_redis_broker", return_value=True),
            patch(
                "apps.core.tasking.redis_queue._get_redis_connection",
                side_effect=ConnectionError("redis down"),
            ),
        ):
            data = task_queue_query.cluster_status()
        assert data["clusters"] is None
        assert "redis down" in (data["broker_error"] or "")

    @pytest.mark.django_db
    def test_heartbeat_keys_dedup_by_cluster_name(self):
        """心跳键按集群名去重：同名集群多进程只算 1 个，跨名即多集群。"""
        conn = MagicMock()
        conn.scan_iter.return_value = [
            b"django_q:default-abc12345:cluster:123",
            b"django_q:default-abc12345:cluster:456",
            b"django_q:zombie-deadbeef:cluster:789",
        ]
        with (
            patch("apps.core.tasking.redis_queue.is_redis_broker", return_value=True),
            patch("apps.core.tasking.redis_queue._get_redis_connection", return_value=conn),
        ):
            data = task_queue_query.cluster_status()
        assert data["clusters"] == 2

    @pytest.mark.django_db
    def test_today_counts_and_last_run_times(self):
        """今日成败计数与最近一次成功/失败时间来自 Task 表。"""
        from django.utils import timezone
        from django_q.models import Task

        now = timezone.now()
        Task.objects.create(id="ok-1", func="math.floor", started=now, stopped=now, success=True)
        Task.objects.create(id="bad-1", func="math.floor", started=now, stopped=now, success=False)

        with patch("apps.core.tasking.redis_queue.is_redis_broker", return_value=False):
            data = task_queue_query.cluster_status()

        assert data["succeeded_today"] == 1
        assert data["failed_today"] == 1
        assert data["last_success_at"] is not None
        assert data["last_failed_at"] is not None


# ── task_queue_query module-level functions ──


class TestTaskQueueQuery:
    @pytest.mark.django_db
    def test_list_queued_returns_queryset(self):
        result = task_queue_query.list_queued()
        assert result is not None

    @pytest.mark.django_db
    def test_list_queued_with_limit(self):
        result = task_queue_query.list_queued(limit=10)
        assert result is not None

    @pytest.mark.django_db
    def test_list_completed_returns_queryset(self):
        result = task_queue_query.list_completed()
        assert result is not None

    @pytest.mark.django_db
    def test_list_failed_returns_queryset(self):
        result = task_queue_query.list_failed()
        assert result is not None

    @pytest.mark.django_db
    def test_list_scheduled_returns_queryset(self):
        result = task_queue_query.list_scheduled()
        assert result is not None

    @pytest.mark.django_db
    def test_get_last_run_time_none(self):
        result = task_queue_query.get_last_run_time("nonexistent_schedule")
        assert result is None

    @pytest.mark.django_db
    def test_delete_task_zero(self):
        result = task_queue_query.delete_task("nonexistent-task-id")
        assert result == 0

    @pytest.mark.django_db
    def test_delete_schedule_zero(self):
        result = task_queue_query.delete_schedule(999999)
        assert result == 0

    @pytest.mark.django_db
    def test_get_task_or_none_not_found(self):
        result = task_queue_query.get_task_or_none("nonexistent-task-id")
        assert result is None

    @pytest.mark.django_db
    def test_resubmit_task_not_found(self):
        result = task_queue_query.resubmit_task("nonexistent-task-id")
        assert result is None

    def test_schedule_type_labels(self):
        assert isinstance(task_queue_query.SCHEDULE_TYPE_LABELS, dict)
        assert len(task_queue_query.SCHEDULE_TYPE_LABELS) > 0
