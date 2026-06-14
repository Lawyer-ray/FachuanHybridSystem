"""Tests for automation.management.commands.execute_document_delivery_schedules.

Covers: _execute_single_schedule, _print_summary, _get_specific_schedule,
_show_schedule_info, _get_credential_info, _show_execution_result.
"""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest

from apps.automation.management.commands.execute_document_delivery_schedules import Command


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_command() -> Command:
    cmd = Command()
    cmd.stdout = MagicMock()
    cmd.style = MagicMock()
    cmd.style.SUCCESS = MagicMock(side_effect=lambda x: x)
    cmd.style.WARNING = MagicMock(side_effect=lambda x: x)
    cmd.style.ERROR = MagicMock(side_effect=lambda x: x)
    return cmd


def _make_schedule(
    *,
    schedule_id: int = 1,
    credential_id: int = 10,
    is_active: bool = True,
    next_run_at=None,
    runs_per_day: int = 4,
    hour_interval: int = 6,
    cutoff_hours: int = 24,
    last_run_at=None,
):
    sched = MagicMock()
    sched.id = schedule_id
    sched.credential_id = credential_id
    sched.is_active = is_active
    sched.next_run_at = next_run_at
    sched.runs_per_day = runs_per_day
    sched.hour_interval = hour_interval
    sched.cutoff_hours = cutoff_hours
    sched.last_run_at = last_run_at
    return sched


# ---------------------------------------------------------------------------
# _execute_single_schedule
# ---------------------------------------------------------------------------


class TestExecuteSingleSchedule:
    def test_success_returns_processed_count(self):
        cmd = _make_command()
        schedule = _make_schedule()
        schedule_service = MagicMock()
        schedule_service.execute_scheduled_task.return_value = SimpleNamespace(
            processed_count=5, failed_count=0
        )
        p, f = cmd._execute_single_schedule(schedule, schedule_service, verbose=False)
        assert p == 5
        assert f == 0

    def test_success_verbose_writes_stdout(self):
        cmd = _make_command()
        schedule = _make_schedule()
        schedule_service = MagicMock()
        result = SimpleNamespace(
            processed_count=3,
            failed_count=1,
            total_found=4,
            skipped_count=0,
            case_log_ids=[1, 2],
            errors=["err1"],
        )
        schedule_service.execute_scheduled_task.return_value = result
        p, f = cmd._execute_single_schedule(schedule, schedule_service, verbose=True)
        assert p == 3
        assert f == 1
        assert cmd.stdout.write.called

    def test_exception_returns_0_1(self):
        cmd = _make_command()
        schedule = _make_schedule()
        schedule_service = MagicMock()
        schedule_service.execute_scheduled_task.side_effect = RuntimeError("boom")
        p, f = cmd._execute_single_schedule(schedule, schedule_service, verbose=False)
        assert p == 0
        assert f == 1

    def test_exception_verbose_writes_error(self):
        cmd = _make_command()
        schedule = _make_schedule()
        schedule_service = MagicMock()
        schedule_service.execute_scheduled_task.side_effect = RuntimeError("boom")
        cmd._execute_single_schedule(schedule, schedule_service, verbose=True)
        # stdout.write should have been called with the error message
        assert cmd.stdout.write.call_count >= 1


# ---------------------------------------------------------------------------
# _print_summary
# ---------------------------------------------------------------------------


class TestPrintSummary:
    def test_verbose_prints_summary(self):
        cmd = _make_command()
        cmd._print_summary(verbose=True, total_processed=10, total_failed=2)
        assert cmd.stdout.write.call_count >= 2  # separator + summary

    def test_non_verbose_with_activity_logs(self):
        cmd = _make_command()
        cmd._print_summary(verbose=False, total_processed=5, total_failed=0)
        # No stdout write expected when not verbose and there's activity
        # (logger.info is called instead)

    def test_non_verbose_no_activity(self):
        cmd = _make_command()
        cmd._print_summary(verbose=False, total_processed=0, total_failed=0)
        # Nothing happens


# ---------------------------------------------------------------------------
# _get_specific_schedule
# ---------------------------------------------------------------------------


class TestGetSpecificSchedule:
    def test_not_found_raises(self):
        cmd = _make_command()
        with patch("apps.automation.models.DocumentDeliverySchedule") as MockModel, \
             patch("apps.core.exceptions.NotFoundError", RuntimeError):
            DoesNotExist = type("DoesNotExist", (Exception,), {})
            MockModel.DoesNotExist = DoesNotExist
            MockModel.objects.get.side_effect = DoesNotExist()
            with pytest.raises(RuntimeError):
                cmd._get_specific_schedule(999, force=False)

    def test_inactive_without_force_returns_empty(self):
        cmd = _make_command()
        schedule = _make_schedule(is_active=False)
        with patch("apps.automation.models.DocumentDeliverySchedule") as MockModel:
            MockModel.objects.get.return_value = schedule
            result = cmd._get_specific_schedule(1, force=False)
            assert result == []

    def test_inactive_with_force_returns_schedule(self):
        cmd = _make_command()
        schedule = _make_schedule(is_active=False)
        with patch("apps.automation.models.DocumentDeliverySchedule") as MockModel:
            MockModel.objects.get.return_value = schedule
            result = cmd._get_specific_schedule(1, force=True)
            assert len(result) == 1

    def test_not_due_without_force_returns_empty(self):
        from django.utils import timezone
        from datetime import timedelta

        cmd = _make_command()
        schedule = _make_schedule(is_active=True, next_run_at=timezone.now() + timedelta(hours=1))
        with patch("apps.automation.models.DocumentDeliverySchedule") as MockModel:
            MockModel.objects.get.return_value = schedule
            result = cmd._get_specific_schedule(1, force=False)
            assert result == []

    def test_due_returns_schedule(self):
        from django.utils import timezone
        from datetime import timedelta

        cmd = _make_command()
        schedule = _make_schedule(is_active=True, next_run_at=timezone.now() - timedelta(hours=1))
        with patch("apps.automation.models.DocumentDeliverySchedule") as MockModel:
            MockModel.objects.get.return_value = schedule
            result = cmd._get_specific_schedule(1, force=False)
            assert len(result) == 1


# ---------------------------------------------------------------------------
# _show_schedule_info
# ---------------------------------------------------------------------------


class TestShowScheduleInfo:
    def test_writes_schedule_count(self):
        cmd = _make_command()
        schedules = [_make_schedule(schedule_id=i) for i in range(3)]
        with patch.object(cmd, "_get_credential_info", return_value="凭证1"):
            cmd._show_schedule_info(schedules)
        assert cmd.stdout.write.call_count >= 3

    def test_with_last_run_at(self):
        from django.utils import timezone

        cmd = _make_command()
        schedule = _make_schedule(last_run_at=timezone.now())
        with patch.object(cmd, "_get_credential_info", return_value="凭证1"):
            cmd._show_schedule_info([schedule])
        assert cmd.stdout.write.call_count >= 2


# ---------------------------------------------------------------------------
# _get_credential_info
# ---------------------------------------------------------------------------


class TestGetCredentialInfo:
    def test_success(self):
        cmd = _make_command()
        with patch("apps.core.interfaces.ServiceLocator") as MockLocator:
            svc = MagicMock()
            svc.get_credential.return_value = SimpleNamespace(username="admin")
            MockLocator.get_organization_service.return_value = svc
            result = cmd._get_credential_info(1)
            assert "admin" in result

    def test_fallback_on_error(self):
        cmd = _make_command()
        with patch("apps.core.interfaces.ServiceLocator") as MockLocator:
            MockLocator.get_organization_service.side_effect = RuntimeError("fail")
            result = cmd._get_credential_info(42)
            assert "42" in result


# ---------------------------------------------------------------------------
# _show_execution_result
# ---------------------------------------------------------------------------


class TestShowExecutionResult:
    def test_shows_counts(self):
        cmd = _make_command()
        result = SimpleNamespace(
            total_found=10,
            processed_count=8,
            skipped_count=1,
            failed_count=1,
            case_log_ids=[1, 2, 3],
            errors=["e1", "e2", "e3", "e4"],
        )
        cmd._show_execution_result(_make_schedule(), result)
        assert cmd.stdout.write.call_count >= 3  # main + case logs + errors

    def test_no_errors_no_case_logs(self):
        cmd = _make_command()
        result = SimpleNamespace(
            total_found=0,
            processed_count=0,
            skipped_count=0,
            failed_count=0,
            case_log_ids=None,
            errors=[],
        )
        cmd._show_execution_result(_make_schedule(), result)
        assert cmd.stdout.write.call_count == 1  # just the main line
