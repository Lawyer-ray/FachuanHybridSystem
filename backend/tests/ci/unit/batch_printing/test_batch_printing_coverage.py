"""batch_printing 模块 0% 覆盖率文件单元测试

覆盖文件:
- apps/batch_printing/tasks.py
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch
from uuid import UUID

import pytest


class TestExecuteBatchPrintJob:
    """execute_batch_print_job 任务测试"""

    @patch("apps.batch_printing.tasks.get_batch_print_job_service")
    def test_execute_job_success(self, mock_get_svc):
        from apps.batch_printing.tasks import execute_batch_print_job

        mock_service = MagicMock()
        mock_get_svc.return_value = mock_service

        execute_batch_print_job("12345678-1234-5678-1234-567812345678")
        mock_service.execute_job.assert_called_once()

    @patch("apps.batch_printing.tasks.BatchPrintJob")
    @patch("apps.batch_printing.tasks.get_batch_print_job_service")
    def test_execute_job_failure_updates_status(self, mock_get_svc, mock_model):
        from apps.batch_printing.tasks import execute_batch_print_job

        mock_service = MagicMock()
        mock_service.execute_job.side_effect = RuntimeError("boom")
        mock_get_svc.return_value = mock_service

        job_id = "12345678-1234-5678-1234-567812345678"
        execute_batch_print_job(job_id)

        mock_model.objects.filter.assert_called_once()
        update_call = mock_model.objects.filter.return_value.update
        update_call.assert_called_once()
        kwargs = update_call.call_args[1]
        assert kwargs["error_message"] == "boom"

    @patch("apps.batch_printing.tasks.BatchPrintJob")
    @patch("apps.batch_printing.tasks.get_batch_print_job_service")
    def test_execute_job_failure_truncates_error(self, mock_get_svc, mock_model):
        from apps.batch_printing.tasks import execute_batch_print_job

        mock_service = MagicMock()
        long_error = "x" * 2000
        mock_service.execute_job.side_effect = RuntimeError(long_error)
        mock_get_svc.return_value = mock_service

        execute_batch_print_job("12345678-1234-5678-1234-567812345678")
        update_call = mock_model.objects.filter.return_value.update
        kwargs = update_call.call_args[1]
        assert len(kwargs["error_message"]) == 1000

    @patch("apps.batch_printing.tasks.get_batch_print_job_service")
    def test_execute_job_passes_uuid(self, mock_get_svc):
        from apps.batch_printing.tasks import execute_batch_print_job

        mock_service = MagicMock()
        mock_get_svc.return_value = mock_service

        job_id = "aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee"
        execute_batch_print_job(job_id)

        call_kwargs = mock_service.execute_job.call_args[1]
        assert call_kwargs["job_id"] == UUID(job_id)
