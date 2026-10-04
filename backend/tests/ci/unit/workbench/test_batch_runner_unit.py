"""batch_runner.py 单元测试。"""

from __future__ import annotations

from unittest.mock import MagicMock, patch
from uuid import uuid4

import pytest

_MODULE = "apps.workbench.tasks.batch_runner"


class TestRunBatchAnalysis:
    def test_run_batch_analysis_delegates_to_bridge(self):
        """入口统一委托 run_coro_sync（loop 判定/超时语义在桥内）。"""
        from apps.workbench.tasks.batch_runner import run_batch_analysis

        def _swallow(coro, **kwargs):
            coro.close()
            return None

        job_id = str(uuid4())
        with patch(f"{_MODULE}.run_coro_sync", side_effect=_swallow) as mock_bridge:
            run_batch_analysis(job_id)
            mock_bridge.assert_called_once()

    def test_run_batch_analysis_bridge_thread_path(self):
        """桥的线程路径（有运行中循环）经 ThreadPoolExecutor 执行——端到端冒烟。"""
        from apps.workbench.tasks.batch_runner import run_batch_analysis

        job_id = str(uuid4())
        with (
            patch(f"{_MODULE}._run_batch_async") as mock_async,
            patch("apps.core.infrastructure.sync_async_bridge._has_running_loop", return_value=True),
            patch("apps.core.infrastructure.sync_async_bridge.ThreadPoolExecutor") as MockPool,
        ):
            mock_async.return_value = MagicMock()
            pool = MockPool.return_value
            mock_future = MagicMock()
            mock_future.result.return_value = None
            pool.submit.return_value = mock_future
            run_batch_analysis(job_id)
            pool.submit.assert_called_once()
            mock_future.result.assert_called_once()
            pool.shutdown.assert_called_once_with(wait=False, cancel_futures=True)


class TestRunBatchRetry:
    def test_run_batch_retry_delegates_to_bridge(self):
        from apps.workbench.tasks.batch_runner import run_batch_retry

        def _swallow(coro, **kwargs):
            coro.close()
            return None

        job_id = str(uuid4())
        item_ids = [str(uuid4())]
        with patch(f"{_MODULE}.run_coro_sync", side_effect=_swallow) as mock_bridge:
            run_batch_retry(job_id, item_ids)
            mock_bridge.assert_called_once()


class TestSyncLlmChat:
    @patch("apps.core.llm.config.LLMConfig.resolve_backend_for_model", return_value="ollama")
    def test_returns_content_on_success(self, _mock_backend):
        from apps.workbench.tasks.batch_runner import _sync_llm_chat

        llm = MagicMock()
        response = MagicMock()
        response.content = "分析结果"
        llm.chat.return_value = response
        result = _sync_llm_chat(
            llm,
            messages=[{"role": "user", "content": "test"}],
            model="model",
            temperature=0.3,
            max_retries=1,
        )
        assert result == "分析结果"

    @patch("apps.core.llm.config.LLMConfig.resolve_backend_for_model", return_value="ollama")
    def test_retries_on_timeout(self, _mock_backend):
        from apps.core.llm.exceptions import LLMTimeoutError
        from apps.workbench.tasks.batch_runner import _sync_llm_chat

        llm = MagicMock()
        response = MagicMock()
        response.content = "ok"
        llm.chat.side_effect = [
            LLMTimeoutError(message="timeout", timeout_seconds=60),
            response,
        ]
        with patch("apps.workbench.tasks.batch_runner.time.sleep"):
            result = _sync_llm_chat(
                llm,
                messages=[{"role": "user", "content": "test"}],
                model="model",
                temperature=0.3,
                max_retries=2,
                retry_delay=0.01,
            )
        assert result == "ok"
