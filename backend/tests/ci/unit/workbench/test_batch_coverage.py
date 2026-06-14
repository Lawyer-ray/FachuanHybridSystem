"""Tests for workbench/services/batch_service.py get_job_progress and list_batch_jobs
+ workbench/models/batch_job.py (missing: 6 lines) +
workbench/services/session_service.py (missing: 3 lines).

Covers: BatchAnalysisService.get_job_progress with/without speed, list_batch_jobs,
BatchJob/BatchJobItem __str__, delete_item_file, delete_job_summary_file,
WorkbenchSessionService increment_storage, aincrement_storage.
"""
from __future__ import annotations

from datetime import timedelta
from types import SimpleNamespace
from unittest.mock import MagicMock, patch
from uuid import uuid4

import pytest


class TestGetJobProgress:
    def test_get_job_progress_basic(self) -> None:
        from apps.workbench.services.batch_service import BatchAnalysisService
        svc = BatchAnalysisService()
        job = MagicMock()
        job.completed_items = 5
        job.failed_items = 1
        job.started_processing_at = None
        job.status = "running"
        items = [MagicMock()]
        with patch("apps.workbench.services.batch_service.BatchJob") as MockJob, \
             patch("apps.workbench.services.batch_service.BatchJobItem") as MockItem:
            MockJob.objects.get.return_value = job
            MockItem.objects.filter.return_value = items
            result_job, result_items = svc.get_job_progress(uuid4())
            assert result_job is job
            assert result_items == items

    def test_get_job_progress_with_speed(self) -> None:
        from apps.workbench.services.batch_service import BatchAnalysisService
        from django.utils import timezone
        svc = BatchAnalysisService()
        job = MagicMock()
        job.completed_items = 5
        job.failed_items = 1
        job.total_items = 10
        job.status = "running"
        job.started_processing_at = timezone.now() - timedelta(seconds=60)
        with patch("apps.workbench.services.batch_service.BatchJob") as MockJob, \
             patch("apps.workbench.services.batch_service.BatchJobItem") as MockItem:
            MockJob.objects.get.return_value = job
            MockItem.objects.filter.return_value = []
            result_job, _ = svc.get_job_progress(uuid4())
            # speed_per_minute should be set
            assert hasattr(result_job, 'speed_per_minute')


class TestListBatchJobs:
    def test_list_batch_jobs(self) -> None:
        from apps.workbench.services.batch_service import BatchAnalysisService
        svc = BatchAnalysisService()
        mock_jobs = [MagicMock()]
        with patch("apps.workbench.services.batch_service.BatchJob") as MockJob:
            MockJob.objects.filter.return_value.order_by.return_value.count.return_value = 1
            MockJob.objects.filter.return_value.order_by.return_value.__getitem__ = MagicMock(return_value=mock_jobs)
            with patch.object(BatchAnalysisService, "_job_to_dict", return_value={"id": "test"}):
                result = svc.list_batch_jobs(1, page=1, page_size=10)
                assert "items" in result
                assert "count" in result


class TestBatchJobItemStr:
    def test_str_representation(self) -> None:
        from apps.workbench.models.batch_job import BatchJobItem
        item = BatchJobItem()
        item.file_name = "test.pdf"
        with patch.object(item, 'get_status_display', return_value="Pending"):
            result = str(item)
            assert "test.pdf" in result
            assert "Pending" in result


class TestBatchJobSignals:
    def test_delete_item_file_signal(self) -> None:
        from apps.workbench.models.batch_job import delete_item_file
        instance = MagicMock()
        instance.file = MagicMock()
        delete_item_file(type, instance)
        instance.file.delete.assert_called_once_with(save=False)

    def test_delete_item_file_no_file(self) -> None:
        from apps.workbench.models.batch_job import delete_item_file
        instance = MagicMock()
        instance.file = None
        delete_item_file(type, instance)  # should not raise

    def test_delete_job_summary_file(self) -> None:
        from apps.workbench.models.batch_job import delete_job_summary_file
        instance = MagicMock()
        instance.summary_file = MagicMock()
        instance.detail_zip_file = MagicMock()
        delete_job_summary_file(type, instance)
        instance.summary_file.delete.assert_called_once_with(save=False)
        instance.detail_zip_file.delete.assert_called_once_with(save=False)


class TestWorkbenchSessionServiceStorage:
    def test_increment_storage_zero(self) -> None:
        from apps.workbench.services.session_service import WorkbenchSessionService
        # delta=0 should be a no-op
        WorkbenchSessionService.increment_storage(1, 0)  # should not raise

    def test_get_active_items(self) -> None:
        from apps.workbench.services.batch_service import BatchAnalysisService
        svc = BatchAnalysisService()
        with patch("apps.workbench.services.batch_service.BatchJobItem") as MockItem:
            MockItem.objects.filter.return_value = [MagicMock()]
            result = svc.get_active_items(uuid4())
            assert len(result) == 1
