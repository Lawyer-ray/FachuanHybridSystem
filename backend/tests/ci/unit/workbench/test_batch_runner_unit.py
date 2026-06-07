"""batch_runner.py 单元测试。"""

from __future__ import annotations

from unittest.mock import MagicMock, patch
from uuid import uuid4

import pytest

_MODULE = "apps.workbench.tasks.batch_runner"


class TestRunBatchAnalysis:

    def test_run_batch_analysis_no_loop(self):
        """当没有运行中的事件循环时，直接调用 asyncio.run。"""
        from apps.workbench.tasks.batch_runner import run_batch_analysis
        job_id = str(uuid4())
        with patch(f"{_MODULE}.asyncio") as mock_asyncio:
            mock_asyncio.get_running_loop.side_effect = RuntimeError("no loop")
            mock_asyncio.run = MagicMock()
            run_batch_analysis(job_id)
            mock_asyncio.run.assert_called_once()

    def test_run_batch_analysis_with_loop(self):
        """当有运行中的事件循环时，使用线程池执行。"""
        from apps.workbench.tasks.batch_runner import run_batch_analysis
        job_id = str(uuid4())
        with patch(f"{_MODULE}.asyncio") as mock_asyncio:
            mock_asyncio.get_running_loop.return_value = MagicMock()
            with patch(f"{_MODULE}.concurrent.futures.ThreadPoolExecutor") as MockPool:
                mock_pool = MagicMock()
                mock_future = MagicMock()
                mock_future.result.return_value = None
                mock_pool.submit.return_value = mock_future
                MockPool.return_value.__enter__ = MagicMock(return_value=mock_pool)
                MockPool.return_value.__exit__ = MagicMock(return_value=False)
                run_batch_analysis(job_id)


class TestRunBatchRetry:

    def test_run_batch_retry_no_loop(self):
        from apps.workbench.tasks.batch_runner import run_batch_retry
        job_id = str(uuid4())
        item_ids = [str(uuid4())]
        with patch(f"{_MODULE}.asyncio") as mock_asyncio:
            mock_asyncio.get_running_loop.side_effect = RuntimeError("no loop")
            mock_asyncio.run = MagicMock()
            run_batch_retry(job_id, item_ids)
            mock_asyncio.run.assert_called_once()


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
        from apps.workbench.tasks.batch_runner import _sync_llm_chat
        from apps.core.llm.exceptions import LLMTimeoutError
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
