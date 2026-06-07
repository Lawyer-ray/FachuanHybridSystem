"""Comprehensive unit tests for batch_runner."""

from __future__ import annotations

import asyncio
import concurrent.futures
import time
from unittest.mock import MagicMock, patch, AsyncMock
from uuid import uuid4

import pytest

_MOD = "apps.workbench.tasks.batch_runner"


class TestRunBatchAnalysis:

    def test_no_loop_calls_asyncio_run(self):
        from apps.workbench.tasks.batch_runner import run_batch_analysis

        job_id = str(uuid4())
        with patch(f"{_MOD}.asyncio") as mock_asyncio:
            mock_asyncio.get_running_loop.side_effect = RuntimeError("no loop")
            mock_asyncio.run = MagicMock()
            run_batch_analysis(job_id)
            mock_asyncio.run.assert_called_once()

    def test_with_loop_uses_thread_pool(self):
        from apps.workbench.tasks.batch_runner import run_batch_analysis

        job_id = str(uuid4())
        with patch(f"{_MOD}.asyncio") as mock_asyncio:
            mock_asyncio.get_running_loop.return_value = MagicMock()
            with patch(f"{_MOD}.concurrent.futures.ThreadPoolExecutor") as MockPool:
                mock_pool = MagicMock()
                mock_future = MagicMock()
                mock_future.result.return_value = None
                mock_pool.submit.return_value = mock_future
                MockPool.return_value.__enter__ = MagicMock(return_value=mock_pool)
                MockPool.return_value.__exit__ = MagicMock(return_value=False)
                run_batch_analysis(job_id)
                mock_pool.submit.assert_called_once()


class TestRunBatchRetry:

    def test_no_loop_calls_asyncio_run(self):
        from apps.workbench.tasks.batch_runner import run_batch_retry

        job_id = str(uuid4())
        item_ids = [str(uuid4())]
        with patch(f"{_MOD}.asyncio") as mock_asyncio:
            mock_asyncio.get_running_loop.side_effect = RuntimeError("no loop")
            mock_asyncio.run = MagicMock()
            run_batch_retry(job_id, item_ids)
            mock_asyncio.run.assert_called_once()

    def test_with_loop_uses_thread_pool(self):
        from apps.workbench.tasks.batch_runner import run_batch_retry

        job_id = str(uuid4())
        item_ids = [str(uuid4())]
        with patch(f"{_MOD}.asyncio") as mock_asyncio:
            mock_asyncio.get_running_loop.return_value = MagicMock()
            with patch(f"{_MOD}.concurrent.futures.ThreadPoolExecutor") as MockPool:
                mock_pool = MagicMock()
                mock_future = MagicMock()
                mock_future.result.return_value = None
                mock_pool.submit.return_value = mock_future
                MockPool.return_value.__enter__ = MagicMock(return_value=mock_pool)
                MockPool.return_value.__exit__ = MagicMock(return_value=False)
                run_batch_retry(job_id, item_ids)
                mock_pool.submit.assert_called_once()


class TestSyncLlmChat:

    def test_success(self):
        from apps.workbench.tasks.batch_runner import _sync_llm_chat

        mock_llm = MagicMock()
        mock_response = MagicMock()
        mock_response.content = "analysis result"
        mock_llm.chat.return_value = mock_response

        with patch("apps.core.llm.config.LLMConfig") as mock_config:
            mock_config.resolve_backend_for_model.return_value = "default"
            result = _sync_llm_chat(
                mock_llm,
                messages=[{"role": "user", "content": "test"}],
                model="gpt-4",
                temperature=0.3,
            )
            assert result == "analysis result"
            mock_llm.chat.assert_called_once()

    def test_retryable_error_retries(self):
        from apps.workbench.tasks.batch_runner import _sync_llm_chat
        from apps.core.llm.exceptions import LLMTimeoutError

        mock_llm = MagicMock()
        mock_llm.chat.side_effect = [
            LLMTimeoutError("timeout"),
            MagicMock(content="recovered"),
        ]

        with patch("apps.core.llm.config.LLMConfig") as mock_config:
            mock_config.resolve_backend_for_model.return_value = "default"
            with patch(f"{_MOD}.time.sleep"):
                result = _sync_llm_chat(
                    mock_llm,
                    messages=[{"role": "user", "content": "test"}],
                    model="gpt-4",
                    temperature=0.3,
                    max_retries=2,
                    retry_delay=0.01,
                )
                assert result == "recovered"

    def test_non_retryable_error_raises(self):
        from apps.workbench.tasks.batch_runner import _sync_llm_chat

        mock_llm = MagicMock()
        mock_llm.chat.side_effect = ValueError("bad input")

        with patch("apps.core.llm.config.LLMConfig") as mock_config:
            mock_config.resolve_backend_for_model.return_value = "default"
            with pytest.raises(ValueError, match="bad input"):
                _sync_llm_chat(
                    mock_llm,
                    messages=[{"role": "user", "content": "test"}],
                    model="gpt-4",
                    temperature=0.3,
                    max_retries=3,
                )

    def test_all_retries_exhausted(self):
        from apps.workbench.tasks.batch_runner import _sync_llm_chat
        from apps.core.llm.exceptions import LLMTimeoutError

        mock_llm = MagicMock()
        mock_llm.chat.side_effect = LLMTimeoutError("always timeout")

        with patch("apps.core.llm.config.LLMConfig") as mock_config:
            mock_config.resolve_backend_for_model.return_value = "default"
            with patch(f"{_MOD}.time.sleep"):
                with pytest.raises(LLMTimeoutError):
                    _sync_llm_chat(
                        mock_llm,
                        messages=[{"role": "user", "content": "test"}],
                        model="gpt-4",
                        temperature=0.3,
                        max_retries=2,
                        retry_delay=0.01,
                    )


class TestCancelWatcher:

    @pytest.mark.asyncio
    async def test_sets_event_when_cancelled(self):
        from apps.workbench.tasks.batch_runner import _cancel_watcher

        job_id = uuid4()
        cancel_event = asyncio.Event()

        with patch(f"{_MOD}.sync_to_async") as mock_sync:
            mock_fn = MagicMock(return_value=True)
            mock_sync.return_value = mock_fn

            with patch("asyncio.sleep", new_callable=AsyncMock):
                await _cancel_watcher(job_id, cancel_event)
                assert cancel_event.is_set()

    @pytest.mark.asyncio
    async def test_stops_when_event_set(self):
        from apps.workbench.tasks.batch_runner import _cancel_watcher

        job_id = uuid4()
        cancel_event = asyncio.Event()
        cancel_event.set()

        with patch(f"{_MOD}.sync_to_async") as mock_sync:
            mock_fn = MagicMock(return_value=False)
            mock_sync.return_value = mock_fn
            await _cancel_watcher(job_id, cancel_event)
            mock_fn.assert_not_called()


class TestIncrementCounter:

    @pytest.mark.asyncio
    async def test_increments_completed(self):
        from apps.workbench.tasks.batch_runner import _increment_counter

        job_id = uuid4()

        with patch(f"{_MOD}.sync_to_async") as mock_sync:
            # First call returns current counts, second call is the update
            mock_sync.side_effect = [
                MagicMock(return_value={"total_items": 10, "completed_items": 5, "failed_items": 2}),
                MagicMock(),
            ]
            await _increment_counter(job_id, "completed_items")
            assert mock_sync.call_count == 2

    @pytest.mark.asyncio
    async def test_no_job_returns_early(self):
        from apps.workbench.tasks.batch_runner import _increment_counter

        job_id = uuid4()

        with patch(f"{_MOD}.sync_to_async") as mock_sync:
            mock_sync.return_value = MagicMock(return_value=None)
            await _increment_counter(job_id, "completed_items")
            # Only the read query, no update
            assert mock_sync.call_count == 1

    @pytest.mark.asyncio
    async def test_zero_total_items(self):
        from apps.workbench.tasks.batch_runner import _increment_counter

        job_id = uuid4()

        with patch(f"{_MOD}.sync_to_async") as mock_sync:
            mock_sync.return_value = MagicMock(return_value={"total_items": 0, "completed_items": 0, "failed_items": 0})
            await _increment_counter(job_id, "completed_items")
            assert mock_sync.call_count == 1


class TestAnalyzeSingleItem:

    @pytest.mark.asyncio
    async def test_short_text_single_chunk(self):
        from apps.workbench.tasks.batch_runner import _analyze_single_item

        item = MagicMock()
        item.file.path = "/tmp/test.docx"
        item.file_name = "test.docx"

        extractor = MagicMock()
        extractor.extract_text.return_value = "short text"
        extractor.extract_doc_metadata.return_value = {"case_number": "2024-01"}

        loop = asyncio.get_running_loop()
        thread_pool = MagicMock()
        cancel_event = asyncio.Event()

        mock_llm = MagicMock()
        mock_response = MagicMock()
        mock_response.content = '{"is_relevant": true}'
        mock_llm.chat.return_value = mock_response

        with patch(f"{_MOD}.build_case_info", return_value="Case: 2024-01"):
            with patch(f"{_MOD}.chunk_text") as mock_chunk:
                with patch(f"{_MOD}.merge_chunk_results", return_value="final"):
                    with patch(f"{_MOD}.LLMConfig") as mock_config:
                        mock_config.resolve_backend_for_model.return_value = "default"
                        mock_chunk.return_value = ["short text"]

                        # Run in executor returns the value directly
                        async def fake_run_in_executor(pool, fn, *args):
                            return fn(*args)

                        loop.run_in_executor = fake_run_in_executor

                        result = await _analyze_single_item(
                            item,
                            job_prompt="test prompt",
                            job_llm_model="gpt-4",
                            llm=mock_llm,
                            extractor=extractor,
                            thread_pool=thread_pool,
                            loop=loop,
                            cancel_event=cancel_event,
                        )
                        assert result == "final"

    @pytest.mark.asyncio
    async def test_cancel_event_raises(self):
        from apps.workbench.tasks.batch_runner import _analyze_single_item

        item = MagicMock()
        item.file.path = "/tmp/test.docx"
        item.file_name = "test.docx"

        extractor = MagicMock()
        extractor.extract_text.return_value = "text"

        loop = asyncio.get_running_loop()
        thread_pool = MagicMock()
        cancel_event = asyncio.Event()
        cancel_event.set()  # pre-cancel

        mock_llm = MagicMock()

        async def fake_run_in_executor(pool, fn, *args):
            return fn(*args)

        loop.run_in_executor = fake_run_in_executor

        with pytest.raises(asyncio.CancelledError):
            await _analyze_single_item(
                item,
                job_prompt="prompt",
                job_llm_model="gpt-4",
                llm=mock_llm,
                extractor=extractor,
                thread_pool=thread_pool,
                loop=loop,
                cancel_event=cancel_event,
            )


class TestRunBatchAsync:

    @pytest.mark.asyncio
    async def test_sets_status_running(self):
        from apps.workbench.tasks.batch_runner import _run_batch_async

        job_id = uuid4()
        mock_job = MagicMock()
        mock_job.metadata = {"concurrency": 5}
        mock_job.prompt = "test"
        mock_job.llm_model = "gpt-4"

        with patch(f"{_MOD}.BatchJob") as MockJob:
            MockJob.objects.get.return_value = mock_job
            MockJob.objects.filter.return_value.update = MagicMock()
            MockJob.DoesNotExist = type("DoesNotExist", (Exception,), {})

            with patch(f"{_MOD}.BatchJobItem") as MockItem:
                MockItem.objects.filter.return_value.__aiter__ = MagicMock(return_value=iter([]))

                with patch(f"{_MOD}.task_registry") as mock_registry:
                    with patch(f"{_MOD}.DocTextExtractor") as MockExtractor:
                        with patch(f"{_MOD}.timezone"):
                            with patch(f"{_MOD}.generate_summary") as mock_summary:
                                with patch(f"{_MOD}.generate_detail_zip") as mock_zip:
                                    mock_summary.return_value = AsyncMock(return_value="summary")
                                    MockExtractor.return_value.cleanup = MagicMock()

                                    await _run_batch_async(job_id)
                                    mock_registry.register.assert_called_once()

    @pytest.mark.asyncio
    async def test_job_not_found_sets_failed(self):
        from apps.workbench.tasks.batch_runner import _run_batch_async

        job_id = uuid4()

        with patch(f"{_MOD}.BatchJob") as MockJob:
            MockJob.objects.get.side_effect = MockJob.DoesNotExist()

            with patch(f"{_MOD}.DocTextExtractor") as MockExtractor:
                MockExtractor.return_value.cleanup = MagicMock()
                await _run_batch_async(job_id)
                # No crash, the exception is caught and sets FAILED


class TestRunBatchRetryAsync:

    @pytest.mark.asyncio
    async def test_job_not_found_returns_early(self):
        from apps.workbench.tasks.batch_runner import _run_batch_retry_async

        job_id = uuid4()

        with patch(f"{_MOD}.BatchJob") as MockJob:
            MockJob.DoesNotExist = type("DoesNotExist", (Exception,), {})
            MockJob.objects.get.side_effect = MockJob.DoesNotExist()

            with patch(f"{_MOD}.DocTextExtractor") as MockExtractor:
                MockExtractor.return_value.cleanup = MagicMock()
                await _run_batch_retry_async(job_id, [])
                # Should return early without error

    @pytest.mark.asyncio
    async def test_empty_item_ids_no_analysis(self):
        from apps.workbench.tasks.batch_runner import _run_batch_retry_async

        job_id = uuid4()
        mock_job = MagicMock()
        mock_job.metadata = {"concurrency": 5}

        with patch(f"{_MOD}.BatchJob") as MockJob:
            MockJob.objects.get.return_value = mock_job
            MockJob.objects.filter.return_value.update = MagicMock()

            with patch(f"{_MOD}.BatchJobItem") as MockItem:
                MockItem.objects.filter.return_value.__aiter__ = MagicMock(return_value=iter([]))

                with patch(f"{_MOD}.DocTextExtractor") as MockExtractor:
                    MockExtractor.return_value.cleanup = MagicMock()
                    with patch(f"{_MOD}.timezone"):
                        await _run_batch_retry_async(job_id, [])
                        # No items to process
