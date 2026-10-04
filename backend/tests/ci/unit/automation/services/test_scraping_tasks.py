"""Tests for scraping_tasks.py and related task functions."""

from unittest.mock import patch

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
# 私有桥 _run_coroutine_sync 已收敛到
# apps.core.infrastructure.sync_async_bridge.run_coro_sync，
# 行为测试见 tests/ci/unit/core/test_sync_async_bridge.py
# ============================================================
