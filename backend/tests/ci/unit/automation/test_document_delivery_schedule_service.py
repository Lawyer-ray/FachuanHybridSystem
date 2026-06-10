"""Tests for DocumentDeliveryScheduleService covering CRUD, scheduling, and execution."""
from __future__ import annotations

from datetime import timedelta
from unittest.mock import MagicMock, patch

import pytest
from django.utils import timezone

from apps.automation.services.document_delivery.document_delivery_schedule_service import DocumentDeliveryScheduleService
from apps.automation.services.document_delivery.data_classes import DocumentQueryResult
from apps.core.exceptions import NotFoundError, ValidationException


@pytest.fixture
def svc():
    return DocumentDeliveryScheduleService(document_delivery_service=MagicMock())


# ── _validate_schedule_config ──


class TestValidateScheduleConfig:
    def test_valid_config(self, svc):
        svc._validate_schedule_config(1, 24, 24)  # should not raise

    def test_zero_runs_per_day(self, svc):
        with pytest.raises(ValidationException, match="每天运行次数必须大于0"):
            svc._validate_schedule_config(0, 24, 24)

    def test_invalid_hour_interval_zero(self, svc):
        with pytest.raises(ValidationException, match="运行间隔必须在1-24小时之间"):
            svc._validate_schedule_config(1, 0, 24)

    def test_invalid_hour_interval_too_high(self, svc):
        with pytest.raises(ValidationException, match="运行间隔必须在1-24小时之间"):
            svc._validate_schedule_config(1, 25, 24)

    def test_zero_cutoff_hours(self, svc):
        with pytest.raises(ValidationException, match="截止时间必须大于0小时"):
            svc._validate_schedule_config(1, 24, 0)

    def test_frequency_too_high(self, svc):
        with pytest.raises(ValidationException, match="运行频率配置不合理"):
            svc._validate_schedule_config(4, 8, 24)  # 4 * 8 = 32 > 24


# ── _calculate_next_run_time ──


class TestCalculateNextRunTime:
    def test_daily_once(self, svc):
        before = timezone.now()
        result = svc._calculate_next_run_time(1, 24)
        after = timezone.now()
        assert before + timedelta(hours=23) <= result <= after + timedelta(hours=25)

    def test_multiple_per_day(self, svc):
        before = timezone.now()
        result = svc._calculate_next_run_time(3, 8)
        after = timezone.now()
        assert before + timedelta(hours=7) <= result <= after + timedelta(hours=9)


# ── get_schedule ──


class TestGetSchedule:
    @pytest.mark.django_db
    def test_get_schedule_not_found(self, svc):
        with pytest.raises(NotFoundError, match="不存在"):
            svc.get_schedule(999999)


# ── delete_schedule ──


class TestDeleteSchedule:
    @pytest.mark.django_db
    def test_delete_schedule_not_found(self, svc):
        with pytest.raises(NotFoundError, match="不存在"):
            svc.delete_schedule(999999)


# ── list_schedules ──


class TestListSchedules:
    @pytest.mark.django_db
    def test_list_empty(self, svc):
        result = svc.list_schedules()
        assert isinstance(result, list)

    @pytest.mark.django_db
    def test_list_with_filters(self, svc):
        result = svc.list_schedules(credential_id=1, is_active=True)
        assert isinstance(result, list)


# ── get_due_schedules ──


class TestGetDueSchedules:
    @pytest.mark.django_db
    def test_get_due_schedules_empty(self, svc):
        result = svc.get_due_schedules()
        assert isinstance(result, list)


# ── execute_scheduled_task ──


class TestExecuteScheduledTask:
    @pytest.mark.django_db
    def test_execute_not_found(self, svc):
        with pytest.raises(NotFoundError, match="不存在"):
            svc.execute_scheduled_task(999999)


# ── _get_execution_lock_key / _acquire_execution_lock / _release_execution_lock ──


class TestExecutionLock:
    def test_lock_key_format(self, svc):
        key = svc._get_execution_lock_key(42)
        assert "42" in key
        assert "lock" in key

    @pytest.mark.django_db
    def test_acquire_and_release_lock(self, svc):
        with patch("django.core.cache.cache") as mock_cache:
            mock_cache.add.return_value = True
            assert svc._acquire_execution_lock(1) is True
            mock_cache.add.assert_called_once()

            svc._release_execution_lock(1)
            mock_cache.delete.assert_called_once()

    @pytest.mark.django_db
    def test_acquire_lock_already_held(self, svc):
        with patch("django.core.cache.cache") as mock_cache:
            mock_cache.add.return_value = False
            assert svc._acquire_execution_lock(1) is False


# ── remove_django_q_schedule / setup_django_q_schedule ──


class TestDjangoQSchedule:
    def test_remove_django_q_schedule(self, svc):
        with patch(
            "apps.core.tasking.ScheduleQueryService"
        ) as MockSvc:
            mock_instance = MagicMock()
            mock_instance.delete_schedules.return_value = 2
            MockSvc.return_value = mock_instance
            count = svc.remove_django_q_schedule("test_schedule")
            assert count == 2

    def test_setup_django_q_schedule(self, svc):
        with patch(
            "apps.core.tasking.ScheduleQueryService"
        ) as MockSvc:
            mock_instance = MagicMock()
            mock_instance.delete_schedules.return_value = 0
            mock_instance.create_interval_schedule.return_value = "task-123"
            MockSvc.return_value = mock_instance
            result = svc.setup_django_q_schedule(interval_minutes=5, schedule_name="test")
            assert result == "task-123"
