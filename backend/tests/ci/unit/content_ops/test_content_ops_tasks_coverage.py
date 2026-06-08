"""content_ops 模块 0% 覆盖率文件单元测试

覆盖文件:
- apps/content_ops/tasks.py
"""

from __future__ import annotations

import os
from unittest.mock import MagicMock, patch

import pytest


class TestExecuteContentOpsTask:
    """execute_content_ops_task 任务测试"""

    def test_execute_task_success(self):
        from apps.content_ops.tasks import execute_content_ops_task

        with patch("apps.content_ops.services.executor.ContentOpsExecutor") as MockExecutor:
            mock_instance = MagicMock()
            mock_instance.run.return_value = {"task_id": "t1", "status": "success"}
            MockExecutor.return_value = mock_instance

            result = execute_content_ops_task("t1")
            assert result["status"] == "success"
            mock_instance.run.assert_called_once_with(task_id="t1")

    def test_execute_task_failure(self):
        from apps.content_ops.tasks import execute_content_ops_task

        with patch("apps.content_ops.services.executor.ContentOpsExecutor") as MockExecutor:
            mock_instance = MagicMock()
            mock_instance.run.return_value = {"task_id": "t2", "status": "failed", "error": "timeout"}
            MockExecutor.return_value = mock_instance

            result = execute_content_ops_task("t2")
            assert result["status"] == "failed"

    def test_execute_task_sets_django_env(self):
        from apps.content_ops.tasks import execute_content_ops_task

        with patch("apps.content_ops.services.executor.ContentOpsExecutor") as MockExecutor:
            MockExecutor.return_value = MagicMock(run=MagicMock(return_value={"status": "ok"}))

            os.environ.pop("DJANGO_ALLOW_ASYNC_UNSAFE", None)
            execute_content_ops_task("t3")
            assert os.environ.get("DJANGO_ALLOW_ASYNC_UNSAFE") == "true"

    def test_execute_task_returns_dict(self):
        from apps.content_ops.tasks import execute_content_ops_task

        with patch("apps.content_ops.services.executor.ContentOpsExecutor") as MockExecutor:
            mock_instance = MagicMock()
            mock_instance.run.return_value = {"task_id": "t4", "status": "completed", "items": 5}
            MockExecutor.return_value = mock_instance

            result = execute_content_ops_task("t4")
            assert isinstance(result, dict)
            assert "task_id" in result
