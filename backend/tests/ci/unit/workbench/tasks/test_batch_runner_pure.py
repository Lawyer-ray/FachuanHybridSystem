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
    def test_run_batch_analysis_delegates_to_bridge(self):
        """入口应统一委托 run_coro_sync，并携带 7200s 超时。"""

        def _swallow(coro, **kwargs):  # 关闭未消费协程，避免 never-awaited 告警
            coro.close()
            return None

        with (
            patch("apps.workbench.tasks.batch_runner.run_coro_sync", side_effect=_swallow) as mock_bridge,
            patch("apps.workbench.tasks.batch_runner._run_batch_async") as mock_async,
        ):
            mock_async.return_value = None
            run_batch_analysis("00000000-0000-0000-0000-000000000001")
            mock_bridge.assert_called_once()
            assert mock_bridge.call_args.kwargs["timeout"] == 7200


class TestRunBatchRetry:
    def test_run_batch_retry_delegates_to_bridge(self):
        """重试入口应统一委托 run_coro_sync，并携带 3600s 超时。"""

        def _swallow(coro, **kwargs):
            coro.close()
            return None

        with (
            patch("apps.workbench.tasks.batch_runner.run_coro_sync", side_effect=_swallow) as mock_bridge,
            patch("apps.workbench.tasks.batch_runner._run_batch_retry_async") as mock_async,
        ):
            mock_async.return_value = None
            run_batch_retry("00000000-0000-0000-0000-000000000001", ["00000000-0000-0000-0000-000000000002"])
            mock_bridge.assert_called_once()
            assert mock_bridge.call_args.kwargs["timeout"] == 3600
