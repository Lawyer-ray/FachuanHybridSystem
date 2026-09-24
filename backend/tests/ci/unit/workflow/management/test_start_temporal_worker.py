"""Tests for workflow/management/commands/start_temporal_worker.py (0% coverage).

Covers: Command.add_arguments, Command._temporal_sandbox_logging, Command.handle.
"""

from __future__ import annotations

import logging
import sys
from io import StringIO
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest


class TestStartTemporalWorkerAddArguments:
    def test_default_arguments(self):
        from apps.workflow.management.commands.start_temporal_worker import Command

        cmd = Command()
        parser = MagicMock()
        cmd.add_arguments(parser)
        assert parser.add_argument.call_count == 3

    def test_argument_defaults(self):
        from apps.workflow.management.commands.start_temporal_worker import Command

        cmd = Command()
        parser = MagicMock()
        cmd.add_arguments(parser)

        calls = {call.args[0]: call.kwargs for call in parser.add_argument.call_args_list}
        assert "--temporal-address" in calls
        assert "--task-queue" in calls
        assert "--max-activities" in calls
        assert calls["--temporal-address"]["default"] == "localhost:7233"
        assert calls["--task-queue"]["default"] == "fachuan-workflow"
        assert calls["--max-activities"]["default"] == 5


class TestStartTemporalWorkerSandboxLogging:
    def test_no_module_loaded_does_not_raise(self):
        from apps.workflow.management.commands.start_temporal_worker import Command

        cmd = Command()
        # 模块未加载时不应抛异常
        with patch.dict(sys.modules, {"apps.core.infrastructure.logging": None}):
            with cmd._temporal_sandbox_logging():
                pass

    def test_does_not_mutate_filter_class(self):
        """关键回归测试：绝不能改动 RequestContextFilter 类本身。

        历史 bug：worker 命令用 `cls.filter = lambda ...` 做进程级 monkeypatch，
        污染同进程内其它测试对该 filter 的断言（见 core 的
        TestRequestContextFilter）。
        """
        from apps.core.infrastructure.logging import RequestContextFilter
        from apps.workflow.management.commands.start_temporal_worker import Command

        original = RequestContextFilter.filter
        cmd = Command()
        with cmd._temporal_sandbox_logging():
            pass
        assert RequestContextFilter.filter is original

    def test_removes_and_restores_filters_on_root_logger(self):
        """运行期间从 root logger 摘除 RequestContextFilter 实例，退出后恢复。"""
        from apps.core.infrastructure.logging import RequestContextFilter
        from apps.workflow.management.commands.start_temporal_worker import Command

        root = logging.getLogger()
        marker = RequestContextFilter()
        root.addFilter(marker)
        saved = list(root.filters)
        cmd = Command()
        try:
            with cmd._temporal_sandbox_logging():
                assert marker not in root.filters
            assert root.filters == saved
            assert marker in root.filters
        finally:
            root.removeFilter(marker)

    def test_get_request_context_filter_types_returns_type(self):
        from apps.core.infrastructure.logging import RequestContextFilter
        from apps.workflow.management.commands.start_temporal_worker import Command

        types = Command._get_request_context_filter_types()
        assert RequestContextFilter in types

    def test_get_request_context_filter_types_empty_when_missing(self):
        from apps.workflow.management.commands.start_temporal_worker import Command

        with patch.dict(sys.modules, {"apps.core.infrastructure.logging": None}):
            assert Command._get_request_context_filter_types() == ()


class TestStartTemporalWorkerHandle:
    def test_handle_calls_asyncio_run(self):
        from apps.workflow.management.commands.start_temporal_worker import Command

        cmd = Command()
        cmd.stdout = StringIO()
        cmd.style = MagicMock()
        cmd.style.SUCCESS = lambda x: f"SUCCESS: {x}"

        with patch("asyncio.run") as mock_run:
            cmd.handle(
                temporal_address="localhost:7233",
                task_queue="fachuan-workflow",
                max_activities=5,
            )
            mock_run.assert_called_once()
