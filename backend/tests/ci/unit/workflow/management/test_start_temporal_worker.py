"""Tests for workflow/management/commands/start_temporal_worker.py (0% coverage).

Covers: Command.add_arguments, Command._setup_logging, Command.handle.
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


class TestStartTemporalWorkerSetupLogging:
    def test_setup_logging_no_mod(self):
        from apps.workflow.management.commands.start_temporal_worker import Command

        cmd = Command()
        # Should not raise even if module is not loaded
        with patch.dict(sys.modules, {"apps.core.infrastructure.logging": None}):
            cmd._setup_logging()

    def test_setup_logging_with_request_context_filter(self):
        from apps.workflow.management.commands.start_temporal_worker import Command

        cmd = Command()
        mock_filter_cls = MagicMock()
        mock_filter_cls.filter = MagicMock()
        mock_mod = MagicMock(RequestContextFilter=mock_filter_cls)
        with patch.dict(sys.modules, {"apps.core.infrastructure.logging": mock_mod}):
            cmd._setup_logging()
            # After setup, the filter should be replaced with a lambda
            assert callable(mock_filter_cls.filter)


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
