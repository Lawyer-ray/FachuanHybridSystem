"""Additional coverage tests for scraping_tasks."""

from __future__ import annotations

import asyncio
from concurrent.futures import Future
from threading import Thread
from unittest.mock import MagicMock, patch

import pytest

from apps.automation.models import ScraperTaskStatus

try:
    from plugins.court_automation import filing
except ImportError:
    pytest.skip("court_automation plugin not installed", allow_module_level=True)


from apps.automation.tasks.scraping_tasks import (
    _run_coroutine_sync,
    execute_preservation_quote_task,
    execute_scraper_task,
    process_pending_tasks,
    reset_running_tasks,
)


class TestRunCoroutineSyncEdge:
    def test_run_with_nested_exception(self):
        async def coro():
            raise TypeError("nested")
        with pytest.raises(TypeError, match="nested"):
            _run_coroutine_sync(coro())


class TestExecuteScraperTaskExtra:
    def test_execute_with_kwargs_logs(self):
        with patch("apps.automation.models.ScraperTask") as MockModel:
            MockModel.objects.get.side_effect = MockModel.DoesNotExist()
            # Should not raise even with extra kwargs
            execute_scraper_task(999, extra="param")

    def test_execute_task_exception_no_retry(self):
        with patch("apps.automation.models.ScraperTask") as MockModel:
            with patch("apps.automation.tasks.scraping_tasks._get_scraper_map") as mock_map:
                task = MagicMock()
                task.should_execute_now.return_value = True
                task.task_type = "document"
                task.get_task_type_display.return_value = "doc"
                task.priority = 1
                task.can_retry.return_value = False
                MockModel.objects.get.return_value = task

                mock_cls = MagicMock()
                mock_cls.return_value.execute.side_effect = RuntimeError("fail")
                mock_map.return_value = {"document": mock_cls}

                execute_scraper_task(1)
                # retry_count should NOT be incremented since can_retry is False
                task.save.assert_called_once()
                # 重试耗尽必须落终态，否则任务停在 running 等 qcluster 重启兜底
                assert task.status == ScraperTaskStatus.FAILED
                assert task.error_message

    def test_execute_task_exception_retry_schedules(self):
        with patch("apps.automation.models.ScraperTask") as MockModel:
            with patch("apps.automation.tasks.scraping_tasks._get_scraper_map") as mock_map:
                with patch("apps.core.tasking.ScheduleQueryService") as MockSched:
                    task = MagicMock()
                    task.should_execute_now.return_value = True
                    task.task_type = "document"
                    task.get_task_type_display.return_value = "doc"
                    task.priority = 1
                    task.can_retry.return_value = True
                    task.retry_count = 1
                    task.max_retries = 3
                    MockModel.objects.get.return_value = task

                    # retry_count 已改为数据库原子自增 + refresh_from_db 回填内存，
                    # 用 db_state 模拟数据库侧状态
                    db_state = {"retry_count": 1}

                    def fake_refresh(fields=None, **kwargs):
                        if fields and "retry_count" in fields:
                            task.retry_count = db_state["retry_count"]

                    def fake_update(**kwargs):
                        db_state["retry_count"] += 1
                        return 1

                    task.refresh_from_db.side_effect = fake_refresh
                    MockModel.objects.filter.return_value.update.side_effect = fake_update

                    mock_cls = MagicMock()
                    mock_cls.return_value.execute.side_effect = RuntimeError("fail")
                    mock_map.return_value = {"document": mock_cls}

                    execute_scraper_task(1)
                    assert task.retry_count == 2
                    MockSched.return_value.create_once_schedule.assert_called_once()


class TestProcessPendingTasksExtra:
    @patch("apps.core.tasking.submit_task")
    @patch("apps.automation.models.ScraperTask")
    @patch("apps.automation.models.ScraperTaskStatus")
    def test_process_submit_exception(self, MockStatus, MockModel, mock_submit):
        task = MagicMock()
        task.id = 1
        task.should_execute_now.return_value = True
        qs = MagicMock()
        qs.count.return_value = 1
        qs.__iter__ = MagicMock(return_value=iter([task]))
        MockModel.objects.filter.return_value.order_by.return_value = qs
        mock_submit.side_effect = RuntimeError("queue error")
        result = process_pending_tasks()
        assert result == 0

    @patch("apps.core.tasking.submit_task")
    @patch("apps.automation.models.ScraperTask")
    @patch("apps.automation.models.ScraperTaskStatus")
    def test_process_not_due_skipped(self, MockStatus, MockModel, mock_submit):
        task = MagicMock()
        task.id = 2
        task.should_execute_now.return_value = False
        qs = MagicMock()
        qs.count.return_value = 1
        qs.__iter__ = MagicMock(return_value=iter([task]))
        MockModel.objects.filter.return_value.order_by.return_value = qs
        result = process_pending_tasks()
        assert result == 0


class TestExecutePreservationQuoteTask:
    def test_quote_not_exists(self):
        with patch("apps.automation.models.PreservationQuote") as MockQuote:
            MockQuote.objects.filter.return_value.exists.return_value = False
            result = execute_preservation_quote_task(quote_id=999)
            assert result["status"] == "skipped"

    def test_token_error(self):
        from plugins.court_automation.preservation_quote.exceptions import TokenError

        with patch("apps.automation.models.PreservationQuote") as MockQuote:
            MockQuote.objects.filter.return_value.exists.return_value = True
            with patch("apps.automation.tasks.scraping_tasks._run_coroutine_sync") as mock_run:
                mock_run.side_effect = TokenError("token expired")
                with patch("apps.automation.models.QuoteStatus") as MockStatus:
                    MockStatus.FAILED = "failed"
                    quote = MagicMock()
                    MockQuote.objects.get.return_value = quote
                    result = execute_preservation_quote_task(quote_id=1)
                    assert result["status"] == "failed"
                    assert result["error"] == "token_error"

    def test_general_exception(self):
        with patch("apps.automation.models.PreservationQuote") as MockQuote:
            MockQuote.objects.filter.return_value.exists.return_value = True
            with patch("apps.automation.tasks.scraping_tasks._run_coroutine_sync") as mock_run:
                mock_run.side_effect = RuntimeError("network error")
                with patch("apps.automation.models.QuoteStatus") as MockStatus:
                    MockStatus.FAILED = "failed"
                    quote = MagicMock()
                    MockQuote.objects.get.return_value = quote
                    # 失败落库后不再向上 raise：避免 django-q2 按 max_attempts
                    # 自动重跑导致保险询价外呼被重复提交
                    result = execute_preservation_quote_task(quote_id=1)
                    assert result["status"] == "failed"
                    assert result["error"] == "execution_error"
                    quote.save.assert_called_once()

    def test_does_not_exist_exception(self):
        from django.core.exceptions import ObjectDoesNotExist

        with patch("apps.automation.models.PreservationQuote") as MockQuote:
            MockQuote.objects.filter.return_value.exists.return_value = True
            with patch("apps.automation.tasks.scraping_tasks._run_coroutine_sync") as mock_run:
                mock_run.side_effect = ObjectDoesNotExist("matching query does not exist")
                result = execute_preservation_quote_task(quote_id=1)
                assert result["status"] == "skipped"
