"""ScrapingTasks 测试。"""

from __future__ import annotations

from unittest.mock import MagicMock, patch


class TestModuleContract:
    """私有桥收敛后的模块契约。

    _run_coroutine_sync / _allow_async_unsafe 已收敛到
    apps.core.infrastructure.sync_async_bridge / async_context，
    模块内不应再残留私有版本（行为测试见 tests/ci/unit/core/ 对应文件）。
    """

    def test_private_bridge_symbols_removed(self) -> None:
        from apps.automation.tasks import scraping_tasks as module

        assert not hasattr(module, "_run_coroutine_sync")
        assert not hasattr(module, "_allow_async_unsafe")
        assert hasattr(module, "run_coro_sync")
        assert hasattr(module, "allow_async_unsafe")


class TestExecuteScraperTask:
    """execute_scraper_task 测试。"""

    @patch("apps.automation.models.ScraperTask")
    def test_execute_task_not_found(self, MockModel: MagicMock) -> None:
        from apps.automation.tasks.scraping_tasks import execute_scraper_task

        MockModel.objects.get.side_effect = MockModel.DoesNotExist()
        execute_scraper_task(999)
        # 任务不存在时早退，不做任何后续更新
        MockModel.objects.get.assert_called_once_with(id=999)
        MockModel.objects.filter.assert_not_called()

    @patch("apps.automation.tasks.scraping_tasks._get_scraper_map")
    @patch("apps.automation.models.ScraperTask")
    def test_execute_task_not_due(self, MockModel: MagicMock, mock_map: MagicMock) -> None:
        from apps.automation.tasks.scraping_tasks import execute_scraper_task

        task = MagicMock()
        task.should_execute_now.return_value = False
        MockModel.objects.get.return_value = task
        execute_scraper_task(1)
        # 未到执行时间直接跳过，不获取 scraper map
        mock_map.assert_not_called()

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
        # 成功路径：实例化对应 scraper 并执行
        mock_scraper_class.assert_called_once_with(task)
        mock_scraper_instance.execute.assert_called_once()

    @patch("apps.core.tasking.ScheduleQueryService")
    @patch("apps.automation.tasks.scraping_tasks._get_scraper_map")
    @patch("apps.automation.models.ScraperTask")
    def test_execute_task_with_retry(self, MockModel: MagicMock, mock_map: MagicMock, MockSched: MagicMock) -> None:
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

        # retry_count 已改为数据库原子自增 + refresh_from_db 回填内存，
        # 用 db_state 模拟数据库侧状态
        db_state = {"retry_count": 0}

        def fake_refresh(fields=None, **kwargs):
            if fields and "retry_count" in fields:
                task.retry_count = db_state["retry_count"]

        def fake_update(**kwargs):
            db_state["retry_count"] += 1
            return 1

        task.refresh_from_db.side_effect = fake_refresh
        MockModel.objects.filter.return_value.update.side_effect = fake_update

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
