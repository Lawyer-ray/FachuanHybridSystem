"""Tests for finance/tasks.py - sync_lpr_rates and setup_lpr_sync_schedule."""

from datetime import datetime
from unittest.mock import MagicMock, patch

import pytest


class TestSyncLprRates:
    """Test sync_lpr_rates task."""

    def test_calls_sync_latest(self):
        """sync_lpr_rates calls LPRSyncService.sync_latest()."""
        from apps.finance.tasks import sync_lpr_rates

        with patch("apps.finance.services.lpr.LPRSyncService") as MockService:
            mock_instance = MockService.return_value
            mock_instance.sync_latest.return_value = {"created": 1, "updated": 0, "skipped": 0, "total": 1}

            result = sync_lpr_rates()

            MockService.assert_called_once()
            mock_instance.sync_latest.assert_called_once()
            assert result == {"created": 1, "updated": 0, "skipped": 0, "total": 1}

    def test_raises_on_sync_failure(self):
        """sync_lpr_rates raises when LPRSyncService raises."""
        from apps.finance.tasks import sync_lpr_rates

        with patch("apps.finance.services.lpr.LPRSyncService") as MockService:
            mock_instance = MockService.return_value
            mock_instance.sync_latest.side_effect = RuntimeError("Network error")

            with pytest.raises(RuntimeError, match="Network error"):
                sync_lpr_rates()


class TestSetupLprSyncSchedule:
    """Test setup_lpr_sync_schedule task."""

    def test_creates_schedule_when_not_exists(self):
        """Creates schedule when it doesn't exist."""
        from apps.finance.tasks import setup_lpr_sync_schedule

        with patch("apps.core.tasking.ScheduleQueryService") as MockService:
            mock_svc = MockService.return_value
            mock_svc.schedule_exists.return_value = False

            setup_lpr_sync_schedule()

            mock_svc.schedule_exists.assert_called_once_with("lpr_monthly_sync")
            mock_svc.create_monthly_schedule.assert_called_once()

    def test_skips_when_schedule_exists(self):
        """Skips creation when schedule already exists."""
        from apps.finance.tasks import setup_lpr_sync_schedule

        with patch("apps.core.tasking.ScheduleQueryService") as MockService:
            mock_svc = MockService.return_value
            mock_svc.schedule_exists.return_value = True

            setup_lpr_sync_schedule()

            mock_svc.schedule_exists.assert_called_once_with("lpr_monthly_sync")
            mock_svc.create_monthly_schedule.assert_not_called()
