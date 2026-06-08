"""Unit tests for batch_printing.services.job.job_service module."""

from __future__ import annotations

import uuid
from unittest.mock import MagicMock, patch
from datetime import datetime

import pytest

from apps.core.exceptions import NotFoundError, ValidationException


class TestBatchPrintJobServiceBuildSummaryPayload:
    """测试 build_job_summary_payload"""

    def _make_service(self):
        return MagicMock()  # Will be replaced below

    def test_build_summary_payload_basic(self) -> None:
        from apps.batch_printing.services.job.job_service import BatchPrintJobService

        svc = BatchPrintJobService(
            rule_service=MagicMock(),
            preset_discovery_service=MagicMock(),
            file_prepare_service=MagicMock(),
            print_executor_service=MagicMock(),
        )
        job = MagicMock()
        job.id = uuid.uuid4()
        job.status = "pending"
        job.total_count = 5
        job.processed_count = 0
        job.success_count = 0
        job.failed_count = 0
        job.progress = 0
        job.cancel_requested = False
        job.task_id = "task-123"
        job.created_by = None
        job.created_by_id = None
        job.capability_payload = {"max_pages": 100}
        job.summary_payload = {}
        job.error_message = ""
        job.created_at = datetime.now()
        job.started_at = None
        job.finished_at = None

        payload = svc.build_job_summary_payload(job=job)
        assert payload["job_id"] == str(job.id)
        assert payload["status"] == "pending"
        assert payload["total_count"] == 5
        assert payload["task_id"] == "task-123"

    def test_build_summary_payload_with_creator(self) -> None:
        from apps.batch_printing.services.job.job_service import BatchPrintJobService

        svc = BatchPrintJobService(
            rule_service=MagicMock(),
            preset_discovery_service=MagicMock(),
            file_prepare_service=MagicMock(),
            print_executor_service=MagicMock(),
        )
        job = MagicMock()
        job.id = uuid.uuid4()
        job.status = "completed"
        job.total_count = 1
        job.processed_count = 1
        job.success_count = 1
        job.failed_count = 0
        job.progress = 100
        job.cancel_requested = False
        job.task_id = None
        job.created_by = MagicMock()
        job.created_by.username = "testuser"
        job.created_by.name = ""
        job.created_by.full_name = ""
        job.created_by_id = 1
        job.capability_payload = {}
        job.summary_payload = {}
        job.error_message = ""
        job.created_at = datetime.now()
        job.started_at = datetime.now()
        job.finished_at = datetime.now()

        payload = svc.build_job_summary_payload(job=job)
        assert payload["created_by_name"] == "testuser"


class TestBatchPrintJobServiceBuildItemPayload:
    """测试 build_job_item_payload"""

    def test_build_item_payload(self) -> None:
        from apps.batch_printing.services.job.job_service import BatchPrintJobService

        svc = BatchPrintJobService(
            rule_service=MagicMock(),
            preset_discovery_service=MagicMock(),
            file_prepare_service=MagicMock(),
            print_executor_service=MagicMock(),
        )
        item = MagicMock()
        item.id = 1
        item.order = 1
        item.source_original_name = "test.pdf"
        item.source_relpath = "media/test.pdf"
        item.prepared_relpath = None
        item.file_type = "pdf"
        item.status = "pending"
        item.matched_rule_id = None
        item.matched_keyword = ""
        item.target_preset_id = None
        item.target_printer_name = ""
        item.target_preset_name = ""
        item.cups_job_id = None
        item.error_message = ""
        item.started_at = None
        item.finished_at = None

        payload = svc.build_job_item_payload(item=item)
        assert payload["id"] == 1
        assert payload["filename"] == "test.pdf"
        assert payload["file_type"] == "pdf"


class TestBatchPrintJobServiceListJobs:
    """测试 list_jobs"""

    @pytest.mark.django_db
    def test_list_jobs_empty(self) -> None:
        from apps.batch_printing.services.job.job_service import BatchPrintJobService

        svc = BatchPrintJobService(
            rule_service=MagicMock(),
            preset_discovery_service=MagicMock(),
            file_prepare_service=MagicMock(),
            print_executor_service=MagicMock(),
        )
        jobs = svc.list_jobs()
        assert isinstance(jobs, list)


class TestBatchPrintJobServiceGetJob:
    """测试 get_job"""

    @pytest.mark.django_db
    def test_get_job_not_found(self) -> None:
        from apps.batch_printing.services.job.job_service import BatchPrintJobService

        svc = BatchPrintJobService(
            rule_service=MagicMock(),
            preset_discovery_service=MagicMock(),
            file_prepare_service=MagicMock(),
            print_executor_service=MagicMock(),
        )
        with pytest.raises(NotFoundError):
            svc.get_job(uuid.uuid4())


class TestBatchPrintJobServiceDeleteJob:
    """测试 delete_job"""

    @pytest.mark.django_db
    def test_delete_job_not_found(self) -> None:
        from apps.batch_printing.services.job.job_service import BatchPrintJobService

        svc = BatchPrintJobService(
            rule_service=MagicMock(),
            preset_discovery_service=MagicMock(),
            file_prepare_service=MagicMock(),
            print_executor_service=MagicMock(),
        )
        with pytest.raises(NotFoundError):
            svc.delete_job(job_id=uuid.uuid4())
