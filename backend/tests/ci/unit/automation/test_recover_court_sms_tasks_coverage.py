"""Tests for recover_court_sms_tasks management command uncovered branches."""

from __future__ import annotations

from datetime import timedelta
from typing import Any
from unittest.mock import MagicMock, patch, PropertyMock

import pytest
from django.utils import timezone


class TestRecoverSingleSms:
    """Cover _recover_single_sms branches."""

    def _cmd(self):
        from apps.automation.management.commands.recover_court_sms_tasks import Command
        return Command()

    def _mock_sms(self, status, retry_count=0):
        sms = MagicMock()
        sms.status = status
        sms.retry_count = retry_count
        sms.scraper_task = None
        sms.save = MagicMock()
        return sms

    def test_pending_submits_async(self):
        cmd = self._cmd()
        submit_fn = MagicMock()
        sms = self._mock_sms("pending")
        with patch("apps.automation.models.CourtSMSStatus") as mock_status:
            mock_status.PENDING = "pending"
            result = cmd._recover_single_sms(sms, submit_fn)
        assert result is True
        submit_fn.assert_called_once()

    def test_download_failed_retry_ok(self):
        cmd = self._cmd()
        submit_fn = MagicMock()
        sms = self._mock_sms("download_failed", retry_count=1)
        with patch("apps.automation.models.CourtSMSStatus") as mock_status:
            mock_status.DOWNLOAD_FAILED = "download_failed"
            result = cmd._recover_single_sms(sms, submit_fn)
        assert result is True
        submit_fn.assert_called_once()

    def test_download_failed_retry_exhausted(self):
        cmd = self._cmd()
        submit_fn = MagicMock()
        sms = self._mock_sms("download_failed", retry_count=3)
        with patch("apps.automation.models.CourtSMSStatus") as mock_status:
            mock_status.DOWNLOAD_FAILED = "download_failed"
            mock_status.FAILED = "failed"
            result = cmd._recover_single_sms(sms, submit_fn)
        assert result is False
        assert sms.status == "failed"
        sms.save.assert_called_once()

    def test_matching_submits_async(self):
        cmd = self._cmd()
        submit_fn = MagicMock()
        sms = self._mock_sms("matching")
        with patch("apps.automation.models.CourtSMSStatus") as mock_status:
            mock_status.MATCHING = "matching"
            result = cmd._recover_single_sms(sms, submit_fn)
        assert result is True
        submit_fn.assert_called_once()

    def test_renaming_submits_async(self):
        cmd = self._cmd()
        submit_fn = MagicMock()
        sms = self._mock_sms("renaming")
        with patch("apps.automation.models.CourtSMSStatus") as mock_status:
            mock_status.RENAMING = "renaming"
            result = cmd._recover_single_sms(sms, submit_fn)
        assert result is True

    def test_notifying_submits_async(self):
        cmd = self._cmd()
        submit_fn = MagicMock()
        sms = self._mock_sms("notifying")
        with patch("apps.automation.models.CourtSMSStatus") as mock_status:
            mock_status.NOTIFYING = "notifying"
            result = cmd._recover_single_sms(sms, submit_fn)
        assert result is True

    def test_downloading_delegates(self):
        cmd = self._cmd()
        submit_fn = MagicMock()
        sms = self._mock_sms("downloading")
        with patch("apps.automation.models.CourtSMSStatus") as mock_status:
            mock_status.DOWNLOADING = "downloading"
            with patch.object(cmd, "_recover_single_downloading", return_value=True) as mock_rd:
                result = cmd._recover_single_sms(sms, submit_fn)
        assert result is True
        mock_rd.assert_called_once_with(sms, submit_fn)

    def test_other_status_submits_async(self):
        cmd = self._cmd()
        submit_fn = MagicMock()
        sms = self._mock_sms("parsing")
        with patch("apps.automation.models.CourtSMSStatus") as mock_status:
            mock_status.PENDING = "pending"
            mock_status.DOWNLOAD_FAILED = "download_failed"
            mock_status.MATCHING = "matching"
            mock_status.RENAMING = "renaming"
            mock_status.NOTIFYING = "notifying"
            mock_status.DOWNLOADING = "downloading"
            result = cmd._recover_single_sms(sms, submit_fn)
        assert result is True
        submit_fn.assert_called_once()


class TestRecoverSingleDownloading:
    """Cover _recover_single_downloading branches."""

    def _cmd(self):
        from apps.automation.management.commands.recover_court_sms_tasks import Command
        return Command()

    def test_no_scraper_task(self):
        cmd = self._cmd()
        submit_fn = MagicMock()
        sms = MagicMock()
        sms.scraper_task = None
        sms.save = MagicMock()
        with patch("apps.automation.models.CourtSMSStatus") as mock_status:
            mock_status.PARSING = "parsing"
            result = cmd._recover_single_downloading(sms, submit_fn)
        assert result is True
        assert sms.status == "parsing"
        submit_fn.assert_called_once()

    def test_scraper_success(self):
        cmd = self._cmd()
        submit_fn = MagicMock()
        sms = MagicMock()
        sms.scraper_task = MagicMock()
        sms.scraper_task.status = "success"
        sms.save = MagicMock()
        with patch("apps.automation.models.CourtSMSStatus") as mock_status, \
             patch("apps.automation.models.ScraperTaskStatus") as scraper_status:
            mock_status.MATCHING = "matching"
            scraper_status.SUCCESS = "success"
            result = cmd._recover_single_downloading(sms, submit_fn)
        assert result is True
        assert sms.status == "matching"
        submit_fn.assert_called_once()

    def test_scraper_failed_with_retry(self):
        cmd = self._cmd()
        submit_fn = MagicMock()
        sms = MagicMock()
        sms.scraper_task = MagicMock()
        sms.scraper_task.status = "failed"
        sms.retry_count = 1
        sms.save = MagicMock()
        with patch("apps.automation.models.CourtSMSStatus") as mock_status, \
             patch("apps.automation.models.ScraperTaskStatus") as scraper_status:
            mock_status.DOWNLOAD_FAILED = "download_failed"
            scraper_status.FAILED = "failed"
            result = cmd._recover_single_downloading(sms, submit_fn)
        assert result is True
        assert sms.status == "download_failed"
        submit_fn.assert_called_once()

    def test_scraper_failed_no_retry(self):
        cmd = self._cmd()
        submit_fn = MagicMock()
        sms = MagicMock()
        sms.scraper_task = MagicMock()
        sms.scraper_task.status = "failed"
        sms.retry_count = 3
        sms.save = MagicMock()
        with patch("apps.automation.models.CourtSMSStatus") as mock_status, \
             patch("apps.automation.models.ScraperTaskStatus") as scraper_status:
            mock_status.DOWNLOAD_FAILED = "download_failed"
            scraper_status.FAILED = "failed"
            result = cmd._recover_single_downloading(sms, submit_fn)
        assert result is True
        submit_fn.assert_not_called()

    def test_scraper_still_running(self):
        cmd = self._cmd()
        submit_fn = MagicMock()
        sms = MagicMock()
        sms.scraper_task = MagicMock()
        sms.scraper_task.status = "running"
        with patch("apps.automation.models.ScraperTaskStatus") as scraper_status:
            scraper_status.SUCCESS = "success"
            scraper_status.FAILED = "failed"
            result = cmd._recover_single_downloading(sms, submit_fn)
        assert result is False
        submit_fn.assert_not_called()


class TestResetStuckTasks:
    """Cover _reset_stuck_tasks."""

    def _cmd(self):
        from apps.automation.management.commands.recover_court_sms_tasks import Command
        return Command()

    def test_resets_stuck_tasks(self):
        cmd = self._cmd()
        sms = MagicMock()
        sms.id = 42
        sms.status = "parsing"
        sms.save = MagicMock()

        with patch("apps.automation.models.CourtSMS") as mock_model, \
             patch("apps.automation.models.CourtSMSStatus") as mock_status, \
             patch("django.utils.timezone.now", return_value=timezone.now()):
            mock_status.PARSING = "parsing"
            mock_status.DOWNLOADING = "downloading"
            mock_status.MATCHING = "matching"
            mock_status.RENAMING = "renaming"
            mock_status.NOTIFYING = "notifying"
            mock_status.PENDING = "pending"

            mock_model.objects.filter.return_value = [sms]
            result = cmd._reset_stuck_tasks(timezone.now() - timedelta(hours=24))
        assert result == 1

    def test_handles_save_exception(self):
        cmd = self._cmd()
        sms = MagicMock()
        sms.id = 42
        sms.status = "parsing"
        sms.save = MagicMock(side_effect=Exception("db error"))

        with patch("apps.automation.models.CourtSMS") as mock_model, \
             patch("apps.automation.models.CourtSMSStatus") as mock_status:
            mock_status.PARSING = "parsing"
            mock_status.DOWNLOADING = "downloading"
            mock_status.MATCHING = "matching"
            mock_status.RENAMING = "renaming"
            mock_status.NOTIFYING = "notifying"
            mock_status.PENDING = "pending"

            mock_model.objects.filter.return_value = [sms]
            result = cmd._reset_stuck_tasks(timezone.now() - timedelta(hours=24), verbose=False)
        assert result == 0


class TestRecoverIncompleteTasks:
    """Cover _recover_incomplete_tasks."""

    def _cmd(self):
        from apps.automation.management.commands.recover_court_sms_tasks import Command
        return Command()

    def test_recovers_tasks(self):
        cmd = self._cmd()
        sms = MagicMock()
        sms.id = 10

        with patch("apps.automation.models.CourtSMS") as mock_model, \
             patch("apps.automation.models.CourtSMSStatus") as mock_status, \
             patch("apps.core.tasking.submit_task") as mock_submit, \
             patch.object(cmd, "_recover_single_sms", return_value=True):
            mock_model.objects.filter.return_value.order_by.return_value = [sms]
            result = cmd._recover_incomplete_tasks(timezone.now() - timedelta(hours=24))
        assert result >= 0

    def test_handles_recover_exception(self):
        cmd = self._cmd()
        sms = MagicMock()
        sms.id = 10

        with patch("apps.automation.models.CourtSMS") as mock_model, \
             patch("apps.automation.models.CourtSMSStatus") as mock_status, \
             patch("apps.core.tasking.submit_task"), \
             patch.object(cmd, "_recover_single_sms", side_effect=Exception("boom")):
            mock_model.objects.filter.return_value.order_by.return_value = [sms]
            result = cmd._recover_incomplete_tasks(timezone.now() - timedelta(hours=24), verbose=False)
        assert result == 0


class TestShowCurrentStatus:
    """Cover _show_current_status."""

    def _cmd(self):
        from apps.automation.management.commands.recover_court_sms_tasks import Command
        return Command()

    def test_displays_status(self):
        cmd = self._cmd()
        cmd.stdout = MagicMock()
        mock_enum = [MagicMock(value="pending", label="待处理"), MagicMock(value="done", label="完成")]

        with patch("apps.automation.models.CourtSMS") as mock_model, \
             patch("apps.automation.models.CourtSMSStatus", mock_enum):
            mock_model.objects.filter.return_value.count.return_value = 5
            cmd._show_current_status(timezone.now() - timedelta(hours=24))
        assert cmd.stdout.write.called


class TestShowRecoveryPlan:
    """Cover _show_recovery_plan."""

    def _cmd(self):
        from apps.automation.management.commands.recover_court_sms_tasks import Command
        return Command()

    def test_shows_incomplete_tasks(self):
        cmd = self._cmd()
        cmd.stdout = MagicMock()
        sms = MagicMock()
        sms.id = 1
        sms.get_status_display.return_value = "待处理"
        sms.created_at = timezone.now()
        sms.content = "test content"

        with patch("apps.automation.models.CourtSMS") as mock_model, \
             patch("apps.automation.models.CourtSMSStatus") as mock_status:
            mock_status.PENDING = "pending"
            mock_status.PARSING = "parsing"
            mock_status.DOWNLOADING = "downloading"
            mock_status.DOWNLOAD_FAILED = "download_failed"
            mock_status.MATCHING = "matching"
            mock_status.RENAMING = "renaming"
            mock_status.NOTIFYING = "notifying"

            qs_mock = MagicMock()
            qs_mock.exists.return_value = True
            qs_mock.count.return_value = 1
            qs_mock.__getitem__ = MagicMock(return_value=[sms])
            mock_model.objects.filter.return_value.order_by.return_value = qs_mock
            cmd._show_recovery_plan(timezone.now() - timedelta(hours=24), reset_stuck=False)
        assert cmd.stdout.write.called
