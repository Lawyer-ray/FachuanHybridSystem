"""Unit tests for BatchAnalysisService — additional coverage."""

from __future__ import annotations

import uuid
from datetime import timedelta
from unittest.mock import MagicMock, patch

import pytest
from django.utils import timezone

from apps.core.exceptions import NotFoundError, ValidationException
from apps.workbench.models import BatchJob, BatchJobItem, BatchJobStatus
from apps.workbench.services.batch_service import BatchAnalysisService, _is_excel


@pytest.fixture
def svc():
    return BatchAnalysisService()


@pytest.fixture
def session(db):
    from apps.workbench.models import WorkbenchSession
    return WorkbenchSession.objects.create(title="批量分析测试会话")


# ──────────── _is_excel helper ────────────


class TestIsExcel:
    def test_xlsx(self):
        assert _is_excel("data.xlsx") is True

    def test_xls(self):
        assert _is_excel("data.xls") is True

    def test_docx(self):
        assert _is_excel("file.docx") is False

    def test_no_extension(self):
        assert _is_excel("noext") is False

    def test_empty_string(self):
        assert _is_excel("") is False

    def test_none_like(self):
        assert _is_excel(".") is False

    def test_case_insensitive(self):
        assert _is_excel("Data.XLSX") is True

    def test_uppercase_xls(self):
        assert _is_excel("FILE.XLS") is True


# ──────────── validate_files ────────────


class TestValidateFiles:
    def test_empty_list_raises(self, svc):
        with pytest.raises(ValidationException):
            svc.validate_files([])

    def test_doc_valid(self, svc):
        f = MagicMock(name="test.doc")
        f.name = "test.doc"
        svc.validate_files([f])  # should not raise

    def test_docx_valid(self, svc):
        f = MagicMock(name="test.docx")
        f.name = "test.docx"
        svc.validate_files([f])

    def test_xls_valid(self, svc):
        f = MagicMock(name="test.xls")
        f.name = "test.xls"
        svc.validate_files([f])

    def test_xlsx_valid(self, svc):
        f = MagicMock(name="test.xlsx")
        f.name = "test.xlsx"
        svc.validate_files([f])

    def test_pdf_invalid(self, svc):
        f = MagicMock()
        f.name = "report.pdf"
        with pytest.raises(ValidationException, match="不支持"):
            svc.validate_files([f])

    def test_no_extension_invalid(self, svc):
        f = MagicMock()
        f.name = "noext"
        with pytest.raises(ValidationException, match="不支持"):
            svc.validate_files([f])

    def test_multiple_valid_files(self, svc):
        files = [MagicMock(name=f"file{i}.docx") for i in range(3)]
        for i, f in enumerate(files):
            f.name = f"file{i}.docx"
        svc.validate_files(files)


# ──────────── get_job_by_id ────────────


class TestGetJobById:
    def test_existing(self, svc, session):
        job = BatchJob.objects.create(
            session=session, job_type="doc_analysis", prompt="p", llm_model="m", total_items=1
        )
        result = svc.get_job_by_id(job.id)
        assert result.id == job.id

    def test_not_found(self, svc, db):
        with pytest.raises(NotFoundError):
            svc.get_job_by_id(uuid.uuid4())


# ──────────── get_job_progress ────────────


class TestGetJobProgress:
    def test_basic(self, svc, session):
        job = BatchJob.objects.create(
            session=session, job_type="doc_analysis", prompt="p", llm_model="m",
            total_items=2, status=BatchJobStatus.PENDING,
        )
        BatchJobItem.objects.create(job=job, file_name="a.docx")
        result_job, items = svc.get_job_progress(job.id)
        assert len(items) == 1
        assert result_job.id == job.id

    def test_eta_calculation(self, svc, session):
        job = BatchJob.objects.create(
            session=session, job_type="doc_analysis", prompt="p", llm_model="m",
            total_items=10,
            completed_items=5, failed_items=0,
            started_processing_at=timezone.now() - timedelta(minutes=5),
            status=BatchJobStatus.RUNNING,
        )
        result_job, _ = svc.get_job_progress(job.id)
        # speed_per_minute and eta_seconds should be calculated
        assert hasattr(result_job, "speed_per_minute")
        assert result_job.speed_per_minute > 0


# ──────────── list_batch_jobs ────────────


class TestListBatchJobs:
    def test_pagination(self, svc, session):
        for i in range(5):
            BatchJob.objects.create(
                session=session, job_type="doc_analysis",
                prompt=f"p{i}", llm_model="m", total_items=1,
            )
        result = svc.list_batch_jobs(session.id, page=1, page_size=2)
        assert result["count"] == 5
        assert len(result["items"]) == 2

    def test_empty(self, svc, session):
        result = svc.list_batch_jobs(session.id)
        assert result["count"] == 0
        assert result["items"] == []


# ──────────── get_active_items ────────────


class TestGetActiveItems:
    def test_filters_correct_statuses(self, svc, session):
        job = BatchJob.objects.create(
            session=session, job_type="doc_analysis", prompt="p", llm_model="m", total_items=3
        )
        BatchJobItem.objects.create(job=job, file_name="running.docx", status=BatchJobStatus.RUNNING)
        BatchJobItem.objects.create(job=job, file_name="completed.docx", status=BatchJobStatus.COMPLETED)
        BatchJobItem.objects.create(job=job, file_name="pending.docx", status=BatchJobStatus.PENDING)
        result = svc.get_active_items(job.id)
        names = set(result.values_list("file_name", flat=True))
        assert "running.docx" in names
        assert "completed.docx" in names
        assert "pending.docx" not in names


# ──────────── mark_completed / mark_failed ────────────


class TestMarkOperations:
    def test_mark_completed(self, svc, session):
        job = BatchJob.objects.create(
            session=session, job_type="doc_analysis", prompt="p", llm_model="m", total_items=1
        )
        svc.mark_completed(job.id, summary="done")
        job.refresh_from_db()
        assert job.status == BatchJobStatus.COMPLETED
        assert job.summary == "done"
        assert job.progress == 100

    def test_mark_failed(self, svc, session):
        job = BatchJob.objects.create(
            session=session, job_type="doc_analysis", prompt="p", llm_model="m", total_items=1
        )
        svc.mark_failed(job.id, error_message="oops")
        job.refresh_from_db()
        assert job.status == BatchJobStatus.FAILED
        assert job.error_message == "oops"

    def test_mark_failed_truncates_long_message(self, svc, session):
        job = BatchJob.objects.create(
            session=session, job_type="doc_analysis", prompt="p", llm_model="m", total_items=1
        )
        long_msg = "x" * 5000
        svc.mark_failed(job.id, error_message=long_msg)
        job.refresh_from_db()
        assert len(job.error_message) == 4000
