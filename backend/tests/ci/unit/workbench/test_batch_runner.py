"""Batch runner tests with mocked dependencies."""

from __future__ import annotations

import asyncio
from unittest.mock import MagicMock, patch

import pytest

from apps.workbench.tasks.batch_runner import (
    CHUNK_THRESHOLD,
    _cancel_watcher,
    _sync_llm_chat,
    run_batch_analysis,
    run_batch_retry,
)


class TestSyncLlmChat:
    @patch("apps.core.llm.config.LLMConfig.resolve_backend_for_model")
    def test_sync_llm_chat_success(self, mock_resolve_backend):
        mock_resolve_backend.return_value = "openai"
        mock_llm = MagicMock()
        mock_response = MagicMock()
        mock_response.content = "分析结果"
        mock_llm.chat.return_value = mock_response

        result = _sync_llm_chat(
            mock_llm,
            messages=[{"role": "user", "content": "分析"}],
            model="gpt-4",
            temperature=0.3,
        )
        assert result == "分析结果"

    @patch("apps.core.llm.config.LLMConfig.resolve_backend_for_model")
    def test_sync_llm_chat_retry_on_timeout(self, mock_resolve_backend):
        from apps.core.llm.exceptions import LLMTimeoutError

        mock_resolve_backend.return_value = "openai"
        mock_llm = MagicMock()
        mock_response = MagicMock()
        mock_response.content = "ok"
        mock_llm.chat.side_effect = [LLMTimeoutError("timeout"), mock_response]

        result = _sync_llm_chat(
            mock_llm,
            messages=[{"role": "user", "content": "test"}],
            model="gpt-4",
            temperature=0.3,
            max_retries=2,
            retry_delay=0.01,
        )
        assert result == "ok"

    @patch("apps.core.llm.config.LLMConfig.resolve_backend_for_model")
    def test_sync_llm_chat_max_retries_exceeded(self, mock_resolve_backend):
        from apps.core.llm.exceptions import LLMTimeoutError

        mock_resolve_backend.return_value = "openai"
        mock_llm = MagicMock()
        mock_llm.chat.side_effect = LLMTimeoutError("timeout")

        with pytest.raises(LLMTimeoutError):
            _sync_llm_chat(
                mock_llm,
                messages=[{"role": "user", "content": "test"}],
                model="gpt-4",
                temperature=0.3,
                max_retries=2,
                retry_delay=0.01,
            )


class TestConstants:
    def test_chunk_threshold(self):
        assert CHUNK_THRESHOLD > 0


class TestRunBatchAnalysis:
    @patch("apps.workbench.tasks.batch_runner.asyncio.run")
    def test_run_batch_analysis_no_loop(self, mock_run):
        mock_run.return_value = None
        with patch("apps.workbench.tasks.batch_runner.asyncio.get_running_loop", side_effect=RuntimeError):
            run_batch_analysis("00000000-0000-0000-0000-000000000001")
            mock_run.assert_called_once()


class TestRunBatchRetry:
    @patch("apps.workbench.tasks.batch_runner.asyncio.run")
    def test_run_batch_retry_no_loop(self, mock_run):
        mock_run.return_value = None
        with patch("apps.workbench.tasks.batch_runner.asyncio.get_running_loop", side_effect=RuntimeError):
            run_batch_retry("00000000-0000-0000-0000-000000000001", ["00000000-0000-0000-0000-000000000002"])
            mock_run.assert_called_once()
