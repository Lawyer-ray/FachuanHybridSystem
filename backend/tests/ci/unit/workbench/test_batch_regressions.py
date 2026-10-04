"""批量分析 create_job 事务 / batch_runner 幂等与线程池释放的回归测试。"""

from __future__ import annotations

import asyncio
import concurrent.futures
from contextlib import contextmanager
from typing import Any, ClassVar
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import UUID

import pytest
from django.core.files.storage import default_storage
from django.core.files.uploadedfile import SimpleUploadedFile

from apps.workbench.models import BatchJob, BatchJobItem, BatchJobStatus
from apps.workbench.services.batch_service import BatchAnalysisService
from apps.workbench.tasks.batch_runner import _run_batch_async

_MODULE = "apps.workbench.tasks.batch_runner"


@pytest.fixture
def svc() -> BatchAnalysisService:
    return BatchAnalysisService()


@pytest.fixture
def session(db):
    from apps.workbench.models import WorkbenchSession

    return WorkbenchSession.objects.create(title="批量回归测试会话")


def _word_file(name: str = "a.docx") -> MagicMock:
    f = MagicMock()
    f.name = name
    return f


def _create_job_with_items(session: Any, *, statuses: list[str]) -> BatchJob:
    """直接构造 job + items，绕过 create_job 的 Q 提交（用于 runner 幂等测试）。"""
    job = BatchJob.objects.create(
        session=session,
        job_type="doc_analysis",
        prompt="测试",
        llm_model="test-model",
        total_items=len(statuses),
    )
    for status in statuses:
        BatchJobItem.objects.create(job=job, file_name="x.docx", status=status)
    return job


class _RecordingPool(concurrent.futures.ThreadPoolExecutor):
    """真实线程池的记录版：shutdown 调用留痕，其余行为不变（不影响 asyncio）。"""

    shutdown_calls: ClassVar[list[tuple[tuple, dict]]] = []

    def shutdown(self, *args: Any, **kwargs: Any) -> None:
        self.shutdown_calls.append((args, kwargs))
        super().shutdown(*args, **kwargs)


@contextmanager
def _record_pool_shutdowns():
    _RecordingPool.shutdown_calls = []
    with patch("concurrent.futures.ThreadPoolExecutor", _RecordingPool):
        yield _RecordingPool.shutdown_calls


def _has_cancelling_shutdown(calls: list[tuple[tuple, dict]]) -> bool:
    return any(kwargs.get("wait") is False and kwargs.get("cancel_futures") is True for _, kwargs in calls)


class TestCreateJobTransaction:
    """create_job：job + items 同事务落库。"""

    def test_bulk_create_failure_rolls_back_job(self, svc, session) -> None:
        """bulk_create 失败时 job 一并回滚，不留无子项的僵尸任务记录。"""
        mock_item_model = MagicMock()
        mock_item_model.objects.bulk_create.side_effect = RuntimeError("bulk boom")

        with (
            patch("apps.workbench.services.batch_service.BatchJobItem", mock_item_model),
            pytest.raises(RuntimeError, match="bulk boom"),
        ):
            svc.create_job(
                session_id=session.id,
                prompt="测试",
                llm_model="test-model",
                files=[_word_file()],
            )

        assert not BatchJob.objects.filter(session=session).exists()


class TestCreateJobSubmitFailure:
    """create_job：Q 任务 submit 失败时标记 FAILED，不留永远 PENDING 的僵尸。"""

    def test_submit_failure_marks_job_failed(self, svc, session) -> None:
        # patch default_storage.save：避免 FileField pre_save 真实写文件到 media 目录
        with (
            patch.object(default_storage, "save", return_value="workbench/test/a.docx"),
            patch(
                "apps.core.dependencies.core.build_task_submission_service",
                side_effect=RuntimeError("submit boom"),
            ),
            pytest.raises(RuntimeError, match="submit boom"),
        ):
            svc.create_job(
                session_id=session.id,
                prompt="测试",
                llm_model="test-model",
                files=[SimpleUploadedFile("a.docx", b"content")],
            )

        job = BatchJob.objects.get(session=session)
        assert job.status == BatchJobStatus.FAILED
        assert job.error_message
        assert job.task_id == ""
        assert job.finished_at is not None
        assert BatchJobItem.objects.filter(job=job).count() == 1


@pytest.mark.django_db(transaction=True)
class TestRunBatchIdempotentItems:
    """_run_batch_async：已完成 item 不重跑（kill 后重跑不重复消耗 LLM token）。"""

    # async ORM 在独立连接上查询，需要真实提交（transaction=True）才能跨连接可见
    @pytest.fixture
    def session(self):
        from apps.workbench.models import WorkbenchSession

        return WorkbenchSession.objects.create(title="批量回归测试会话（事务型）")

    def test_completed_items_skipped_on_rerun(self, session) -> None:
        job = _create_job_with_items(session, statuses=[BatchJobStatus.COMPLETED, BatchJobStatus.COMPLETED])
        llm = MagicMock()

        with (
            patch("apps.core.llm.service.get_llm_service", return_value=llm),
            patch(f"{_MODULE}.generate_summary", new=AsyncMock(return_value="汇总")),
            patch(f"{_MODULE}.generate_detail_zip", new=AsyncMock(return_value=None)),
            _record_pool_shutdowns() as shutdown_calls,
        ):
            asyncio.run(_run_batch_async(UUID(str(job.id))))

        job.refresh_from_db()
        # 已完成 item 被跳过：LLM 从未被调用，item 状态保持 COMPLETED
        llm.chat.assert_not_called()
        assert BatchJobItem.objects.filter(job=job, status=BatchJobStatus.RUNNING).count() == 0
        # 汇总正常生成，任务直接完成
        assert job.status == BatchJobStatus.COMPLETED
        assert job.summary == "汇总"
        assert job.progress == 100


@pytest.mark.django_db(transaction=True)
class TestRunBatchPoolShutdownOnCancel:
    """_run_batch_async：取消路径也释放线程池（不泄漏 concurrency 个线程）。"""

    @pytest.fixture
    def session(self):
        from apps.workbench.models import WorkbenchSession

        return WorkbenchSession.objects.create(title="批量回归测试会话（事务型）")

    def test_cancelled_gather_still_shuts_down_pool(self, session) -> None:
        job = _create_job_with_items(session, statuses=[BatchJobStatus.PENDING])
        llm = MagicMock()

        async def _raising_gather(*coros: Any, **_kwargs: Any) -> None:
            for coro in coros:
                close = getattr(coro, "close", None)
                if close is not None:
                    close()
            raise asyncio.CancelledError

        with (
            patch("apps.core.llm.service.get_llm_service", return_value=llm),
            patch(f"{_MODULE}.generate_summary", new=AsyncMock(return_value="汇总")),
            patch(f"{_MODULE}.generate_detail_zip", new=AsyncMock(return_value=None)),
            patch("asyncio.gather", _raising_gather),
            _record_pool_shutdowns() as shutdown_calls,
        ):
            asyncio.run(_run_batch_async(UUID(str(job.id))))

        job.refresh_from_db()
        assert job.status == BatchJobStatus.CANCELLED
        assert _has_cancelling_shutdown(shutdown_calls), (
            f"未观察到 shutdown(wait=False, cancel_futures=True): {shutdown_calls}"
        )
        llm.chat.assert_not_called()


class TestRunBatchEntryTimeoutShutdown:
    """形式超时防护——超时后立即 shutdown(cancel_futures=True)，不等待线程自然结束。

    2026-10 桥接收敛后该语义下沉到 apps.core.infrastructure.sync_async_bridge，
    此处直接对桥的线程路径做回归（batch_runner 入口按 7200s 超时委托该桥）。
    """

    def test_entry_pool_shutdown_on_timeout(self) -> None:
        from apps.core.infrastructure.sync_async_bridge import run_coro_sync

        mock_pool = MagicMock()
        mock_future = MagicMock()
        mock_future.result.side_effect = concurrent.futures.TimeoutError
        mock_pool.submit.return_value = mock_future

        async def _never() -> None:
            await asyncio.sleep(0.05)

        with (
            patch("apps.core.infrastructure.sync_async_bridge._has_running_loop", return_value=True),
            patch("apps.core.infrastructure.sync_async_bridge.ThreadPoolExecutor", return_value=mock_pool),
            pytest.raises(concurrent.futures.TimeoutError),
        ):
            run_coro_sync(_never(), timeout=0.01)

        mock_pool.shutdown.assert_called_once_with(wait=False, cancel_futures=True)
