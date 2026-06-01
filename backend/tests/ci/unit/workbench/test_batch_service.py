"""Unit tests for BatchAnalysisService."""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from apps.core.exceptions import NotFoundError, ValidationException
from apps.workbench.models import BatchJob, BatchJobItem, BatchJobStatus
from apps.workbench.services.batch_service import BatchAnalysisService


@pytest.fixture
def svc() -> BatchAnalysisService:
    return BatchAnalysisService()


@pytest.fixture
def session(db):
    from apps.workbench.models import WorkbenchSession

    return WorkbenchSession.objects.create(title="批量测试会话")


class TestValidateFiles:
    def test_empty_files_raises(self, svc) -> None:
        with pytest.raises(ValidationError := ValidationException):
            svc.validate_files([])

    def test_unsupported_extension_raises(self, svc) -> None:
        f = MagicMock()
        f.name = "test.pdf"
        with pytest.raises(ValidationException, match="不支持"):
            svc.validate_files([f])

    def test_valid_docx(self, svc) -> None:
        f = MagicMock()
        f.name = "test.docx"
        svc.validate_files([f])  # Should not raise

    def test_valid_xlsx(self, svc) -> None:
        f = MagicMock()
        f.name = "test.xlsx"
        svc.validate_files([f])  # Should not raise


class TestGetJobById:
    def test_existing_job(self, svc, session) -> None:
        job = BatchJob.objects.create(
            session=session,
            job_type="doc_analysis",
            prompt="测试",
            llm_model="gpt-4",
            total_items=1,
        )
        result = svc.get_job_by_id(job.id)
        assert result.id == job.id

    def test_nonexistent_raises(self, svc) -> None:
        import uuid

        with pytest.raises(NotFoundError):
            svc.get_job_by_id(uuid.uuid4())


class TestMarkCompleted:
    def test_mark_completed(self, svc, session) -> None:
        job = BatchJob.objects.create(
            session=session,
            job_type="doc_analysis",
            prompt="测试",
            llm_model="gpt-4",
            total_items=1,
        )
        svc.mark_completed(job.id, summary="完成")
        job.refresh_from_db()
        assert job.status == BatchJobStatus.COMPLETED
        assert job.summary == "完成"
        assert job.progress == 100


class TestMarkFailed:
    def test_mark_failed(self, svc, session) -> None:
        job = BatchJob.objects.create(
            session=session,
            job_type="doc_analysis",
            prompt="测试",
            llm_model="gpt-4",
            total_items=1,
        )
        svc.mark_failed(job.id, error_message="出错了")
        job.refresh_from_db()
        assert job.status == BatchJobStatus.FAILED
        assert job.error_message == "出错了"


class TestListBatchJobs:
    def test_list_returns_session_jobs(self, svc, session) -> None:
        BatchJob.objects.create(
            session=session, job_type="doc_analysis", prompt="测试1", llm_model="gpt-4", total_items=1
        )
        BatchJob.objects.create(
            session=session, job_type="doc_analysis", prompt="测试2", llm_model="gpt-4", total_items=1
        )
        result = svc.list_batch_jobs(session.id)
        assert result["count"] == 2
        assert len(result["items"]) == 2

    def test_list_empty(self, svc, session) -> None:
        result = svc.list_batch_jobs(session.id)
        assert result["count"] == 0
        assert result["items"] == []


class TestRetryFailed:
    def test_retry_with_failed_items(self, svc, session) -> None:
        job = BatchJob.objects.create(
            session=session,
            job_type="doc_analysis",
            prompt="测试",
            llm_model="gpt-4",
            total_items=2,
            status=BatchJobStatus.FAILED,
            failed_items=1,
        )
        BatchJobItem.objects.create(
            job=job,
            file_name="fail.docx",
            status=BatchJobStatus.FAILED,
            error="timeout",
        )
        result = svc.retry_failed(job.id)
        assert result["success"] is True
        assert result["retry_count"] == 1

    def test_retry_without_failed_items(self, svc, session) -> None:
        job = BatchJob.objects.create(
            session=session,
            job_type="doc_analysis",
            prompt="测试",
            llm_model="gpt-4",
            total_items=1,
            status=BatchJobStatus.COMPLETED,
        )
        result = svc.retry_failed(job.id)
        assert result["success"] is False

    def test_retry_running_job_fails(self, svc, session) -> None:
        job = BatchJob.objects.create(
            session=session,
            job_type="doc_analysis",
            prompt="测试",
            llm_model="gpt-4",
            total_items=1,
            status=BatchJobStatus.RUNNING,
        )
        result = svc.retry_failed(job.id)
        assert result["success"] is False
