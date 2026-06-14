"""Round 4 coverage tests for automation.services.scraper.core.monitor_service.

Targets remaining uncovered branches:
- MonitorService.check_stuck_tasks: service locator path (no objects attr)
- MonitorService.check_high_failure_rate: service locator path (no _meta)
- MonitorService.send_alert: info level, error level
- MonitorServiceAdapter: all internal methods delegation
- MonitorService.get_task_statistics: service without objects (get_tasks_since path)
"""
from __future__ import annotations

from unittest.mock import MagicMock, patch, call

import pytest


# ---------------------------------------------------------------------------
# MonitorService.check_stuck_tasks — service locator path
# ---------------------------------------------------------------------------


class TestCheckStuckTasksServiceLocator:
    def test_no_objects_attr_uses_get_stuck_tasks(self):
        from apps.automation.services.scraper.core.monitor_service import MonitorService

        task_svc = MagicMock(spec=[])  # no 'objects' attr
        stuck_result = MagicMock()
        stuck_result.exists.return_value = True
        stuck_result.count.return_value = 2
        stuck_result.__iter__ = MagicMock(return_value=iter([MagicMock(), MagicMock()]))
        task_svc.get_stuck_tasks = MagicMock(return_value=stuck_result)

        svc = MonitorService(task_service=task_svc)
        result = svc.check_stuck_tasks(timeout_minutes=30)
        assert len(result) == 2
        task_svc.get_stuck_tasks.assert_called_once()


# ---------------------------------------------------------------------------
# MonitorService.check_high_failure_rate — service path (no _meta)
# ---------------------------------------------------------------------------


class TestCheckHighFailureRateServicePath:
    def test_no_meta_uses_get_task_type_choices(self):
        from apps.automation.services.scraper.core.monitor_service import MonitorService

        task_svc = MagicMock(spec=["get_task_type_choices", "get_tasks_by_type_and_status"])
        task_svc.get_task_type_choices.return_value = [("type_a", "Type A")]

        # Return an object with count() and filter() to match the service path
        qs = MagicMock()
        qs.count.return_value = 10  # total
        failed_qs = MagicMock()
        failed_qs.count.return_value = 10  # all failed
        qs.filter.return_value = failed_qs
        task_svc.get_tasks_by_type_and_status.return_value = qs

        svc = MonitorService(task_service=task_svc)
        result = svc.check_high_failure_rate(threshold=0.5, min_tasks=5)
        assert "type_a" in result

    def test_service_returns_fewer_than_min_tasks(self):
        from apps.automation.services.scraper.core.monitor_service import MonitorService

        task_svc = MagicMock(spec=["get_task_type_choices", "get_tasks_by_type_and_status"])
        task_svc.get_task_type_choices.return_value = [("type_a", "Type A")]
        # Return object with count() that returns small number
        qs = MagicMock()
        qs.count.return_value = 2  # below min_tasks=5
        task_svc.get_tasks_by_type_and_status.return_value = qs

        svc = MonitorService(task_service=task_svc)
        result = svc.check_high_failure_rate(threshold=0.5, min_tasks=5)
        assert result == {}

    def test_service_returns_empty(self):
        from apps.automation.services.scraper.core.monitor_service import MonitorService

        task_svc = MagicMock(spec=["get_task_type_choices", "get_tasks_by_type_and_status"])
        task_svc.get_task_type_choices.return_value = [("type_a", "Type A")]
        # Return object with count() that returns 0
        qs = MagicMock()
        qs.count.return_value = 0
        task_svc.get_tasks_by_type_and_status.return_value = qs

        svc = MonitorService(task_service=task_svc)
        result = svc.check_high_failure_rate(threshold=0.5, min_tasks=5)
        assert result == {}


# ---------------------------------------------------------------------------
# MonitorService.send_alert
# ---------------------------------------------------------------------------


class TestSendAlert:
    def test_warning_level(self):
        from apps.automation.services.scraper.core.monitor_service import MonitorService

        alert_svc = MagicMock()
        svc = MonitorService(alert_service=alert_svc)
        svc.send_alert("title", "message", level="warning")
        alert_svc.log.assert_called_once()

    def test_error_level(self):
        from apps.automation.services.scraper.core.monitor_service import MonitorService

        alert_svc = MagicMock()
        svc = MonitorService(alert_service=alert_svc)
        svc.send_alert("title", "message", level="error")
        alert_svc.log.assert_called_once()

    def test_default_level_is_warning(self):
        from apps.automation.services.scraper.core.monitor_service import MonitorService

        alert_svc = MagicMock()
        svc = MonitorService(alert_service=alert_svc)
        svc.send_alert("title", "message")
        alert_svc.log.assert_called_once()


# ---------------------------------------------------------------------------
# MonitorService.get_task_statistics — service without objects
# ---------------------------------------------------------------------------


class TestGetTaskStatisticsServicePath:
    def test_no_objects_uses_get_tasks_since(self):
        from apps.automation.services.scraper.core.monitor_service import MonitorService

        task_svc = MagicMock(spec=["get_tasks_since"])
        qs = MagicMock()
        qs.count.return_value = 5
        qs.filter.return_value.count.return_value = 1
        qs.values.return_value.values_list.return_value = []
        task_svc.get_tasks_since.return_value = qs

        svc = MonitorService(task_service=task_svc)
        stats = svc.get_task_statistics(hours=12)
        assert "total" in stats
        task_svc.get_tasks_since.assert_called_once()


# ---------------------------------------------------------------------------
# MonitorServiceAdapter — additional internal method tests
# ---------------------------------------------------------------------------


class TestMonitorServiceAdapterInternal:
    def test_send_alert_internal_with_default_level(self):
        from apps.automation.services.scraper.core.monitor_service import (
            MonitorService,
            MonitorServiceAdapter,
        )

        inner = MagicMock(spec=MonitorService)
        adapter = MonitorServiceAdapter(service=inner)
        adapter.send_alert_internal("t", "m")
        inner.send_alert.assert_called_with("t", "m", "warning")

    def test_get_task_statistics_internal_default(self):
        from apps.automation.services.scraper.core.monitor_service import (
            MonitorService,
            MonitorServiceAdapter,
        )

        inner = MagicMock(spec=MonitorService)
        inner.get_task_statistics.return_value = {"total": 0}
        adapter = MonitorServiceAdapter(service=inner)
        result = adapter.get_task_statistics_internal()
        inner.get_task_statistics.assert_called_with(24)

    def test_check_stuck_tasks_internal_default(self):
        from apps.automation.services.scraper.core.monitor_service import (
            MonitorService,
            MonitorServiceAdapter,
        )

        inner = MagicMock(spec=MonitorService)
        inner.check_stuck_tasks.return_value = []
        adapter = MonitorServiceAdapter(service=inner)
        result = adapter.check_stuck_tasks_internal()
        inner.check_stuck_tasks.assert_called_with(30)

    def test_check_high_failure_rate_internal_default(self):
        from apps.automation.services.scraper.core.monitor_service import (
            MonitorService,
            MonitorServiceAdapter,
        )

        inner = MagicMock(spec=MonitorService)
        inner.check_high_failure_rate.return_value = {}
        adapter = MonitorServiceAdapter(service=inner)
        result = adapter.check_high_failure_rate_internal()
        inner.check_high_failure_rate.assert_called_with(0.5, 10)
