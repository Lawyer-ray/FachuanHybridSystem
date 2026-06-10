"""Tests for core tasking query services: TaskQueryService, ScheduleQueryService, task_queue_query."""
from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from apps.core.tasking.query import ScheduleQueryService, TaskQueryService
from apps.core.tasking import task_queue_query


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
