"""ScrapingTasks 测试。"""

from __future__ import annotations

import asyncio
from unittest.mock import MagicMock, patch

import pytest

from apps.automation.tasks.scraping_tasks import (
    _run_coroutine_sync,
    check_stuck_tasks,
    startup_check,
)


class TestRunCoroutineSync:
    """_run_coroutine_sync 测试。"""

    def test_run_without_existing_loop(self) -> None:
        async def coro() -> str:
            return "result"
        result = _run_coroutine_sync(coro())
        assert result == "result"

    def test_run_with_exception(self) -> None:
        async def coro() -> None:
            raise ValueError("test error")
        with pytest.raises(ValueError, match="test error"):
            _run_coroutine_sync(coro())


class TestCheckStuckTasks:
    """check_stuck_tasks 测试。"""

    @patch("apps.core.interfaces.ServiceLocator")
    def test_check_stuck_tasks_no_stuck(self, mock_sl: MagicMock) -> None:
        mock_monitor = MagicMock()
        mock_monitor.check_stuck_tasks.return_value = []
        mock_sl.get_monitor_service.return_value = mock_monitor
        check_stuck_tasks()
        mock_monitor.send_alert.assert_not_called()

    @patch("apps.core.interfaces.ServiceLocator")
    def test_check_stuck_tasks_with_stuck(self, mock_sl: MagicMock) -> None:
        mock_monitor = MagicMock()
        mock_monitor.check_stuck_tasks.return_value = [MagicMock(), MagicMock()]
        mock_sl.get_monitor_service.return_value = mock_monitor
        check_stuck_tasks()
        mock_monitor.send_alert.assert_called_once()


class TestStartupCheck:
    """startup_check 测试。"""

    @patch("apps.automation.tasks.scraping_tasks.process_pending_tasks", return_value=5)
    @patch("apps.automation.tasks.scraping_tasks.reset_running_tasks", return_value=2)
    def test_startup_check(self, mock_reset: MagicMock, mock_process: MagicMock) -> None:
        result = startup_check()
        assert result == {"reset_count": 2, "pending_count": 5}


class TestExecuteScraperTask:
    """execute_scraper_task 测试。"""

    @patch("apps.automation.models.ScraperTask")
    def test_execute_task_not_found(self, MockModel: MagicMock) -> None:
        from apps.automation.tasks.scraping_tasks import execute_scraper_task
        MockModel.objects.get.side_effect = MockModel.DoesNotExist()
        execute_scraper_task(999)

    @patch("apps.automation.tasks.scraping_tasks._get_scraper_map")
    @patch("apps.automation.models.ScraperTask")
    def test_execute_task_not_due(self, MockModel: MagicMock, mock_map: MagicMock) -> None:
        from apps.automation.tasks.scraping_tasks import execute_scraper_task
        task = MagicMock()
        task.should_execute_now.return_value = False
        MockModel.objects.get.return_value = task
        execute_scraper_task(1)

    @patch("apps.automation.tasks.scraping_tasks._get_scraper_map")
    @patch("apps.automation.models.ScraperTask")
    def test_execute_task_unsupported_type(self, MockModel: MagicMock, mock_map: MagicMock) -> None:
        from apps.automation.tasks.scraping_tasks import execute_scraper_task
        task = MagicMock()
        task.should_execute_now.return_value = True
        task.task_type = "unsupported"
        MockModel.objects.get.return_value = task
        mock_map.return_value = {}
        execute_scraper_task(1)
        assert task.status == "failed"

    @patch("apps.automation.tasks.scraping_tasks._get_scraper_map")
    @patch("apps.automation.models.ScraperTask")
    def test_execute_task_success(self, MockModel: MagicMock, mock_map: MagicMock) -> None:
        from apps.automation.tasks.scraping_tasks import execute_scraper_task
        task = MagicMock()
        task.should_execute_now.return_value = True
        task.task_type = "document"
        task.get_task_type_display.return_value = "文书下载"
        task.priority = 1
        MockModel.objects.get.return_value = task

        mock_scraper_class = MagicMock()
        mock_scraper_instance = MagicMock()
        mock_scraper_instance.execute.return_value = {"files": []}
        mock_scraper_class.return_value = mock_scraper_instance
        mock_map.return_value = {"document": mock_scraper_class}

        execute_scraper_task(1)

    @patch("apps.core.tasking.ScheduleQueryService")
    @patch("apps.automation.tasks.scraping_tasks._get_scraper_map")
    @patch("apps.automation.models.ScraperTask")
    def test_execute_task_with_retry(self, MockModel: MagicMock, mock_map: MagicMock,
                                      MockSched: MagicMock) -> None:
        from apps.automation.tasks.scraping_tasks import execute_scraper_task
        task = MagicMock()
        task.should_execute_now.return_value = True
        task.task_type = "document"
        task.get_task_type_display.return_value = "文书下载"
        task.priority = 1
        task.can_retry.return_value = True
        task.retry_count = 0
        task.max_retries = 3
        MockModel.objects.get.return_value = task

        mock_scraper_class = MagicMock()
        mock_scraper_class.return_value.execute.side_effect = RuntimeError("fail")
        mock_map.return_value = {"document": mock_scraper_class}

        execute_scraper_task(1)
        assert task.retry_count == 1


class TestProcessPendingTasks:
    """process_pending_tasks 测试。"""

    @patch("apps.core.tasking.submit_task")
    @patch("apps.automation.models.ScraperTask")
    @patch("apps.automation.models.ScraperTaskStatus")
    def test_process_no_pending(self, MockStatus: MagicMock, MockModel: MagicMock, mock_submit: MagicMock) -> None:
        from apps.automation.tasks.scraping_tasks import process_pending_tasks
        MockModel.objects.filter.return_value.order_by.return_value.count.return_value = 0
        result = process_pending_tasks()
        assert result == 0

    @patch("apps.core.tasking.submit_task")
    @patch("apps.automation.models.ScraperTask")
    @patch("apps.automation.models.ScraperTaskStatus")
    def test_process_with_pending(self, MockStatus: MagicMock, MockModel: MagicMock, mock_submit: MagicMock) -> None:
        from apps.automation.tasks.scraping_tasks import process_pending_tasks
        task = MagicMock()
        task.should_execute_now.return_value = True
        task.id = 1
        qs = MagicMock()
        qs.count.return_value = 1
        qs.__iter__ = MagicMock(return_value=iter([task]))
        MockModel.objects.filter.return_value.order_by.return_value = qs
        result = process_pending_tasks()
        assert result == 1


class TestResetRunningTasks:
    """reset_running_tasks 测试。"""

    @patch("apps.automation.models.ScraperTask")
    @patch("apps.automation.models.ScraperTaskStatus")
    def test_reset_no_running(self, MockStatus: MagicMock, MockModel: MagicMock) -> None:
        from apps.automation.tasks.scraping_tasks import reset_running_tasks
        MockModel.objects.filter.return_value.count.return_value = 0
        result = reset_running_tasks()
        assert result == 0

    @patch("apps.automation.models.ScraperTask")
    @patch("apps.automation.models.ScraperTaskStatus")
    def test_reset_with_running(self, MockStatus: MagicMock, MockModel: MagicMock) -> None:
        from apps.automation.tasks.scraping_tasks import reset_running_tasks
        qs = MagicMock()
        qs.count.return_value = 3
        MockModel.objects.filter.return_value = qs
        result = reset_running_tasks()
        assert result == 3
