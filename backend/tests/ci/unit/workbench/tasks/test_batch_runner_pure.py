"""Tests for workbench.tasks.batch_runner - pure logic functions."""

from __future__ import annotations

import asyncio
from typing import Any
from unittest.mock import MagicMock, patch

import pytest

from apps.workbench.tasks.batch_runner import _sync_llm_chat, run_batch_analysis, run_batch_retry


class TestSyncLlmChat:
    def test_success(self):
        with patch("apps.core.llm.config.LLMConfig") as MockConfig:
            MockConfig.resolve_backend_for_model.return_value = "default"
            llm = MagicMock()
            response = MagicMock()
            response.content = "analysis result"
            llm.chat.return_value = response
            result = _sync_llm_chat(llm, [{"role": "user", "content": "test"}], "model", 0.3)
            assert result == "analysis result"

    @patch("apps.workbench.tasks.batch_runner.time.sleep")
    def test_retry_on_timeout(self, mock_sleep):
        from apps.core.llm.config import LLMConfig
        from apps.core.llm.exceptions import LLMTimeoutError

        with patch.object(LLMConfig, "resolve_backend_for_model", return_value="default"):
            llm = MagicMock()
            response = MagicMock()
            response.content = "success after retry"
            llm.chat.side_effect = [LLMTimeoutError("timeout"), response]
            result = _sync_llm_chat(
                llm, [{"role": "user", "content": "test"}], "model", 0.3, max_retries=2, retry_delay=0.01
            )
            assert result == "success after retry"

    @patch("apps.workbench.tasks.batch_runner.time.sleep")
    def test_retry_exhausted(self, mock_sleep):
        from apps.core.llm.config import LLMConfig
        from apps.core.llm.exceptions import LLMTimeoutError

        with patch.object(LLMConfig, "resolve_backend_for_model", return_value="default"):
            llm = MagicMock()
            llm.chat.side_effect = LLMTimeoutError("timeout")
            with pytest.raises(LLMTimeoutError):
                _sync_llm_chat(
                    llm, [{"role": "user", "content": "test"}], "model", 0.3, max_retries=2, retry_delay=0.01
                )


class TestRunBatchAnalysis:
    def test_run_batch_analysis_no_loop(self):
        with patch("apps.workbench.tasks.batch_runner._run_batch_async"):
            with patch("apps.workbench.tasks.batch_runner.asyncio") as mock_asyncio:
                mock_asyncio.get_running_loop.side_effect = RuntimeError("no loop")
                mock_asyncio.run = MagicMock()
                run_batch_analysis("00000000-0000-0000-0000-000000000001")
                mock_asyncio.run.assert_called_once()


class TestRunBatchRetry:
    def test_run_batch_retry_no_loop(self):
        with patch("apps.workbench.tasks.batch_runner._run_batch_retry_async"):
            with patch("apps.workbench.tasks.batch_runner.asyncio") as mock_asyncio:
                mock_asyncio.get_running_loop.side_effect = RuntimeError("no loop")
                mock_asyncio.run = MagicMock()
                run_batch_retry("00000000-0000-0000-0000-000000000001", ["00000000-0000-0000-0000-000000000002"])
                mock_asyncio.run.assert_called_once()
