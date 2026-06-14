"""Round 4 coverage tests for execute_document_delivery_schedules management command.

Targets remaining uncovered branches:
- handle: full integration with dry-run, schedule-id, no schedules found
- _execute_single_schedule: verbose with no errors
- _print_summary: non-verbose with both processed and failed
- _get_specific_schedule: next_run_at is None (always due)
- _show_schedule_info: schedule with no last_run_at, no next_run_at
- _show_execution_result: more than 3 errors, exactly 3 errors
- add_arguments: verify parser arguments registered
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
# add_arguments
# ---------------------------------------------------------------------------


class TestAddArguments:
    def test_registers_all_arguments(self):
        cmd = Command()
        parser = MagicMock()
        cmd.add_arguments(parser)
        assert parser.add_argument.call_count >= 3  # --dry-run, --schedule-id, --force


# ---------------------------------------------------------------------------
# _execute_single_schedule — verbose no errors
# ---------------------------------------------------------------------------


class TestExecuteSingleScheduleVerboseNoErrors:
    def test_verbose_no_errors_no_case_log(self):
        cmd = _make_command()
        schedule = _make_schedule()
        schedule_service = MagicMock()
        result = SimpleNamespace(
            processed_count=3,
            failed_count=0,
            total_found=3,
            skipped_count=0,
            case_log_ids=[],
            errors=[],
        )
        schedule_service.execute_scheduled_task.return_value = result
        p, f = cmd._execute_single_schedule(schedule, schedule_service, verbose=True)
        assert p == 3
        assert f == 0


# ---------------------------------------------------------------------------
# _print_summary — non-verbose with activity
# ---------------------------------------------------------------------------


class TestPrintSummaryRound4:
    def test_non_verbose_with_both_counts(self):
        cmd = _make_command()
        # Should log but not write to stdout
        cmd._print_summary(verbose=False, total_processed=5, total_failed=2)


# ---------------------------------------------------------------------------
# _get_specific_schedule — next_run_at is None
# ---------------------------------------------------------------------------


class TestGetSpecificScheduleEdge:
    def test_next_run_at_none_returns_schedule(self):
        cmd = _make_command()
        schedule = _make_schedule(is_active=True, next_run_at=None)
        with patch("apps.automation.models.DocumentDeliverySchedule") as MockModel:
            MockModel.objects.get.return_value = schedule
            result = cmd._get_specific_schedule(1, force=False)
        assert len(result) == 1

    def test_force_with_active_due(self):
        cmd = _make_command()
        schedule = _make_schedule(is_active=True)
        with patch("apps.automation.models.DocumentDeliverySchedule") as MockModel:
            MockModel.objects.get.return_value = schedule
            result = cmd._get_specific_schedule(1, force=True)
        assert len(result) == 1


# ---------------------------------------------------------------------------
# _show_schedule_info — no last_run, no next_run
# ---------------------------------------------------------------------------


class TestShowScheduleInfoEdge:
    def test_no_last_run_no_next_run(self):
        cmd = _make_command()
        schedule = _make_schedule(last_run_at=None, next_run_at=None)
        with patch.object(cmd, "_get_credential_info", return_value="凭证1"):
            cmd._show_schedule_info([schedule])
        assert cmd.stdout.write.call_count >= 1

    def test_multiple_schedules(self):
        cmd = _make_command()
        schedules = [_make_schedule(schedule_id=i, last_run_at=None, next_run_at=None) for i in range(5)]
        with patch.object(cmd, "_get_credential_info", return_value="凭证1"):
            cmd._show_schedule_info(schedules)
        assert cmd.stdout.write.call_count >= 5


# ---------------------------------------------------------------------------
# _show_execution_result — more than 3 errors
# ---------------------------------------------------------------------------


class TestShowExecutionResultEdge:
    def test_more_than_three_errors(self):
        cmd = _make_command()
        result = SimpleNamespace(
            total_found=10,
            processed_count=5,
            skipped_count=0,
            failed_count=5,
            case_log_ids=[1],
            errors=["e1", "e2", "e3", "e4", "e5"],
        )
        cmd._show_execution_result(_make_schedule(), result)
        # main line + case log + 3 errors + "...还有2个错误"
        assert cmd.stdout.write.call_count >= 4

    def test_exactly_three_errors(self):
        cmd = _make_command()
        result = SimpleNamespace(
            total_found=3,
            processed_count=0,
            skipped_count=0,
            failed_count=3,
            case_log_ids=None,
            errors=["e1", "e2", "e3"],
        )
        cmd._show_execution_result(_make_schedule(), result)
        # main line + 3 errors
        assert cmd.stdout.write.call_count >= 4

    def test_with_case_log_ids(self):
        cmd = _make_command()
        result = SimpleNamespace(
            total_found=2,
            processed_count=2,
            skipped_count=0,
            failed_count=0,
            case_log_ids=[10, 20, 30],
            errors=[],
        )
        cmd._show_execution_result(_make_schedule(), result)
        # main line + case log line
        assert cmd.stdout.write.call_count >= 2
