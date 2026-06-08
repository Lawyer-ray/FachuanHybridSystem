"""Tests for scraping_tasks.py and related task functions."""

import asyncio
from unittest.mock import MagicMock, patch

import pytest


# ============================================================
# reset_running_tasks
# ============================================================

class TestResetRunningTasks:
    def test_returns_zero_when_no_running(self):
        with patch("apps.automation.models.ScraperTask") as MockTask:
            with patch("apps.automation.models.ScraperTaskStatus") as MockStatus:
                from apps.automation.tasks.scraping_tasks import reset_running_tasks
                MockTask.objects.filter.return_value.count.return_value = 0
                result = reset_running_tasks()
                assert result == 0

    def test_resets_running_tasks(self):
        with patch("apps.automation.models.ScraperTask") as MockTask:
            with patch("apps.automation.models.ScraperTaskStatus") as MockStatus:
                from apps.automation.tasks.scraping_tasks import reset_running_tasks
                MockTask.objects.filter.return_value.count.return_value = 3
                MockTask.objects.filter.return_value.update.return_value = 3
                result = reset_running_tasks()
                assert result == 3


# ============================================================
# startup_check
# ============================================================

class TestStartupCheck:
    def test_returns_counts(self):
        from apps.automation.tasks.scraping_tasks import startup_check
        with patch("apps.automation.tasks.scraping_tasks.reset_running_tasks", return_value=2):
            with patch("apps.automation.tasks.scraping_tasks.process_pending_tasks", return_value=5):
                result = startup_check()
                assert result == {"reset_count": 2, "pending_count": 5}


# ============================================================
# _run_coroutine_sync
# ============================================================

class TestRunCoroutineSync:
    def test_run_simple_coroutine(self):
        from apps.automation.tasks.scraping_tasks import _run_coroutine_sync

        async def coro():
            return 42

        result = _run_coroutine_sync(coro())
        assert result == 42

    def test_run_coroutine_with_exception(self):
        from apps.automation.tasks.scraping_tasks import _run_coroutine_sync

        async def coro():
            raise ValueError("test error")

        with pytest.raises(ValueError, match="test error"):
            _run_coroutine_sync(coro())
