"""Tests for TaskRecoveryService covering recovery, status, and scheduling."""
from __future__ import annotations

from datetime import timedelta
from unittest.mock import MagicMock, patch

import pytest
from django.utils import timezone

from apps.automation.models import CourtSMS, CourtSMSStatus, ScraperTask, ScraperTaskStatus, ScraperTaskType
from apps.automation.services.sms.task_recovery_service import TaskRecoveryService, periodic_recovery_task


@pytest.fixture
def svc():
    return TaskRecoveryService()


# ── init ──


class TestInit:
    def test_default_values(self, svc):
        assert svc.stuck_timeout_minutes == 30
        assert svc.max_retry_count == 3
        assert svc.recovery_max_age_hours == 24


# ── get_recovery_status ──


class TestGetRecoveryStatus:
    @pytest.mark.django_db
    def test_returns_dict_with_expected_keys(self, svc):
        result = svc.get_recovery_status()
        assert "status_counts" in result
        assert "recovery_needed" in result
        assert "stuck_tasks" in result
        assert "max_age_hours" in result
        assert "stuck_timeout_minutes" in result
        assert result["max_age_hours"] == 24
        assert result["stuck_timeout_minutes"] == 30


# ── _get_tasks_to_recover ──


class TestGetTasksToRecover:
    @pytest.mark.django_db
    def test_returns_empty_when_no_tasks(self, svc):
        result = svc._get_tasks_to_recover()
        assert result == []

    @pytest.mark.django_db
    def test_returns_incomplete_tasks(self, svc):
        sms = CourtSMS.objects.create(
            content="test",
            status=CourtSMSStatus.PENDING,
            received_at=timezone.now(),
        )
        result = svc._get_tasks_to_recover()
        assert any(t.id == sms.id for t in result)

    @pytest.mark.django_db
    def test_ignores_old_tasks(self, svc):
        sms = CourtSMS.objects.create(
            content="old",
            status=CourtSMSStatus.PENDING,
            received_at=timezone.now() - timedelta(hours=25),
        )
        # Manually update created_at since auto_now_add prevents setting via create()
        CourtSMS.objects.filter(id=sms.id).update(created_at=timezone.now() - timedelta(hours=25))
        result = svc._get_tasks_to_recover()
        assert len(result) == 0

    @pytest.mark.django_db
    def test_ignores_completed_tasks(self, svc):
        CourtSMS.objects.create(
            content="done",
            status=CourtSMSStatus.COMPLETED,
            received_at=timezone.now(),
        )
        result = svc._get_tasks_to_recover()
        assert len(result) == 0


# ── _get_stuck_tasks ──


class TestGetStuckTasks:
    @pytest.mark.django_db
    def test_returns_empty_when_no_stuck(self, svc):
        result = svc._get_stuck_tasks()
        assert result == []

    @pytest.mark.django_db
    def test_returns_stuck_tasks(self, svc):
        sms = CourtSMS.objects.create(
            content="stuck",
            status=CourtSMSStatus.MATCHING,
            received_at=timezone.now(),
        )
        # Manually update updated_at since auto_now prevents setting via create()
        CourtSMS.objects.filter(id=sms.id).update(updated_at=timezone.now() - timedelta(minutes=60))
        result = svc._get_stuck_tasks()
        assert any(t.id == sms.id for t in result)

    @pytest.mark.django_db
    def test_ignores_recently_updated(self, svc):
        CourtSMS.objects.create(
            content="recent",
            status=CourtSMSStatus.MATCHING,
            received_at=timezone.now(),
            updated_at=timezone.now(),  # Just updated, not stuck
        )
        result = svc._get_stuck_tasks()
        assert len(result) == 0


# ── _reset_stuck_task ──


class TestResetStuckTask:
    @pytest.mark.django_db
    def test_resets_status_to_pending(self, svc):
        sms = CourtSMS.objects.create(
            content="stuck",
            status=CourtSMSStatus.MATCHING,
            received_at=timezone.now(),
        )
        result = svc._reset_stuck_task(sms)
        assert result is True
        sms.refresh_from_db()
        assert sms.status == CourtSMSStatus.PENDING
        assert "系统恢复" in sms.error_message


# ── _recover_task ──


class TestRecoverTask:
    @pytest.mark.django_db
    @patch("apps.automation.services.sms.task_recovery_service.submit_task")
    def test_recover_pending_task(self, mock_submit, svc):
        sms = CourtSMS.objects.create(
            content="pending",
            status=CourtSMSStatus.PENDING,
            received_at=timezone.now(),
        )
        result = svc._recover_task(sms)
        assert result is True
        mock_submit.assert_called_once()

    @pytest.mark.django_db
    @patch("apps.automation.services.sms.task_recovery_service.submit_task")
    def test_recover_download_failed_with_retries(self, mock_submit, svc):
        sms = CourtSMS.objects.create(
            content="failed",
            status=CourtSMSStatus.DOWNLOAD_FAILED,
            received_at=timezone.now(),
            retry_count=1,
        )
        result = svc._recover_task(sms)
        assert result is True

    @pytest.mark.django_db
    def test_recover_download_failed_no_retries_left(self, svc):
        sms = CourtSMS.objects.create(
            content="failed",
            status=CourtSMSStatus.DOWNLOAD_FAILED,
            received_at=timezone.now(),
            retry_count=3,
        )
        result = svc._recover_task(sms)
        assert result is False
        sms.refresh_from_db()
        assert sms.status == CourtSMSStatus.FAILED

    @pytest.mark.django_db
    @patch("apps.automation.services.sms.task_recovery_service.submit_task")
    def test_recover_matching_task(self, mock_submit, svc):
        sms = CourtSMS.objects.create(
            content="matching",
            status=CourtSMSStatus.MATCHING,
            received_at=timezone.now(),
            retry_count=0,
        )
        result = svc._recover_task(sms)
        assert result is True

    @pytest.mark.django_db
    def test_recover_matching_max_retries_reached(self, svc):
        sms = CourtSMS.objects.create(
            content="matching",
            status=CourtSMSStatus.MATCHING,
            received_at=timezone.now(),
            retry_count=3,
        )
        result = svc._recover_task(sms)
        assert result is False
        sms.refresh_from_db()
        assert sms.status == CourtSMSStatus.PENDING_MANUAL

    @pytest.mark.django_db
    @patch("apps.automation.services.sms.task_recovery_service.submit_task")
    def test_recover_downloading_with_success_scraper_task(self, mock_submit, svc):
        task = ScraperTask.objects.create(
            task_type=ScraperTaskType.COURT_DOCUMENT,
            status=ScraperTaskStatus.SUCCESS,
            url="https://example.com",
        )
        sms = CourtSMS.objects.create(
            content="downloading",
            status=CourtSMSStatus.DOWNLOADING,
            received_at=timezone.now(),
            scraper_task=task,
        )
        result = svc._recover_task(sms)
        assert result is True
        sms.refresh_from_db()
        assert sms.status == CourtSMSStatus.MATCHING

    @pytest.mark.django_db
    @patch("apps.automation.services.sms.task_recovery_service.submit_task")
    def test_recover_downloading_with_failed_scraper_task(self, mock_submit, svc):
        task = ScraperTask.objects.create(
            task_type=ScraperTaskType.COURT_DOCUMENT,
            status=ScraperTaskStatus.FAILED,
            url="https://example.com",
        )
        sms = CourtSMS.objects.create(
            content="downloading",
            status=CourtSMSStatus.DOWNLOADING,
            received_at=timezone.now(),
            retry_count=0,
            scraper_task=task,
        )
        result = svc._recover_task(sms)
        assert result is True
        sms.refresh_from_db()
        assert sms.status == CourtSMSStatus.DOWNLOAD_FAILED

    @pytest.mark.django_db
    def test_recover_downloading_no_scraper_task(self, svc):
        sms = CourtSMS.objects.create(
            content="downloading",
            status=CourtSMSStatus.DOWNLOADING,
            received_at=timezone.now(),
        )
        with patch("apps.automation.services.sms.task_recovery_service.submit_task"):
            result = svc._recover_task(sms)
        assert result is True
        sms.refresh_from_db()
        assert sms.status == CourtSMSStatus.PARSING

    @pytest.mark.django_db
    @patch("apps.automation.services.sms.task_recovery_service.submit_task")
    def test_recover_renaming_task(self, mock_submit, svc):
        sms = CourtSMS.objects.create(
            content="renaming",
            status=CourtSMSStatus.RENAMING,
            received_at=timezone.now(),
        )
        result = svc._recover_task(sms)
        assert result is True


# ── recover_all_tasks ──


class TestRecoverAllTasks:
    @pytest.mark.django_db
    def test_dry_run(self, svc):
        CourtSMS.objects.create(
            content="test",
            status=CourtSMSStatus.PENDING,
            received_at=timezone.now(),
        )
        result = svc.recover_all_tasks(dry_run=True)
        assert "recovered_count" in result
        assert "tasks" in result

    @pytest.mark.django_db
    def test_empty_recovery(self, svc):
        result = svc.recover_all_tasks()
        assert result["recovered_count"] == 0
        assert result["reset_count"] == 0


# ── schedule_periodic_recovery ──


class TestSchedulePeriodicRecovery:
    def test_schedule_periodic_recovery(self, svc):
        with patch(
            "apps.automation.services.sms.task_recovery_service.ScheduleQueryService"
        ) as MockSvc:
            mock_instance = MagicMock()
            MockSvc.return_value = mock_instance
            svc.schedule_periodic_recovery(interval_minutes=30)
            mock_instance.delete_schedules.assert_called_once()
            mock_instance.create_interval_schedule.assert_called_once()


# ── periodic_recovery_task ──


class TestPeriodicRecoveryTask:
    @pytest.mark.django_db
    def test_entry_function(self):
        result = periodic_recovery_task()
        assert isinstance(result, dict)
        assert "recovered_count" in result
