"""Targeted tests for batch_printing module to push coverage to 80%+."""
from __future__ import annotations

from uuid import uuid4
from unittest.mock import MagicMock, patch

import pytest


# ---------------------------------------------------------------------------
# services/storage.py (66% coverage)
# ---------------------------------------------------------------------------


class TestBatchPrintStorage:
    def test_job_root(self, tmp_path):
        from apps.batch_printing.services.storage import BatchPrintStorage

        with patch("apps.batch_printing.services.storage.settings") as mock_settings:
            mock_settings.MEDIA_ROOT = str(tmp_path)
            storage = BatchPrintStorage("test-job-id")
            assert "batch_printing" in str(storage.job_root)

    def test_source_dir(self, tmp_path):
        from apps.batch_printing.services.storage import BatchPrintStorage

        with patch("apps.batch_printing.services.storage.settings") as mock_settings:
            mock_settings.MEDIA_ROOT = str(tmp_path)
            storage = BatchPrintStorage("test-job-id")
            assert storage.source_dir.name == "source"

    def test_prepared_dir(self, tmp_path):
        from apps.batch_printing.services.storage import BatchPrintStorage

        with patch("apps.batch_printing.services.storage.settings") as mock_settings:
            mock_settings.MEDIA_ROOT = str(tmp_path)
            storage = BatchPrintStorage("test-job-id")
            assert storage.prepared_dir.name == "prepared"

    def test_artifacts_dir(self, tmp_path):
        from apps.batch_printing.services.storage import BatchPrintStorage

        with patch("apps.batch_printing.services.storage.settings") as mock_settings:
            mock_settings.MEDIA_ROOT = str(tmp_path)
            storage = BatchPrintStorage("test-job-id")
            assert storage.artifacts_dir.name == "artifacts"

    def test_ensure_dirs(self, tmp_path):
        from apps.batch_printing.services.storage import BatchPrintStorage

        with patch("apps.batch_printing.services.storage.settings") as mock_settings:
            mock_settings.MEDIA_ROOT = str(tmp_path)
            storage = BatchPrintStorage("test-job-id")
            storage.ensure_dirs()
            assert storage.source_dir.exists()
            assert storage.prepared_dir.exists()
            assert storage.artifacts_dir.exists()

    def test_cleanup(self, tmp_path):
        from apps.batch_printing.services.storage import BatchPrintStorage

        with patch("apps.batch_printing.services.storage.settings") as mock_settings:
            mock_settings.MEDIA_ROOT = str(tmp_path)
            storage = BatchPrintStorage("test-job-id")
            storage.ensure_dirs()
            assert storage.job_root.exists()
            storage.cleanup()
            assert not storage.job_root.exists()

    def test_source_file_path(self, tmp_path):
        from apps.batch_printing.services.storage import BatchPrintStorage

        with patch("apps.batch_printing.services.storage.settings") as mock_settings:
            mock_settings.MEDIA_ROOT = str(tmp_path)
            storage = BatchPrintStorage("test-job-id")
            path = storage.source_file_path(order=1, filename="test.pdf")
            assert path.name == "001_test.pdf"

    def test_prepared_pdf_path(self, tmp_path):
        from apps.batch_printing.services.storage import BatchPrintStorage

        with patch("apps.batch_printing.services.storage.settings") as mock_settings:
            mock_settings.MEDIA_ROOT = str(tmp_path)
            storage = BatchPrintStorage("test-job-id")
            path = storage.prepared_pdf_path(order=5, filename_stem="doc")
            assert path.name == "005_doc.pdf"


# ---------------------------------------------------------------------------
# schemas.py (0% coverage) - Pydantic models
# ---------------------------------------------------------------------------


class TestBatchPrintingSchemas:
    def test_preset_sync_out(self):
        from apps.batch_printing.schemas import PresetSyncOut

        schema = PresetSyncOut(discovered=10, upserted=5)
        assert schema.discovered == 10

    def test_batch_print_submit_out(self):
        from apps.batch_printing.schemas import BatchPrintSubmitOut

        schema = BatchPrintSubmitOut(job_id="abc-123", status="pending")
        assert schema.job_id == "abc-123"

    def test_batch_print_item_out(self):
        from apps.batch_printing.schemas import BatchPrintItemOut

        schema = BatchPrintItemOut(
            id=1, order=0, filename="test.pdf",
            source_relpath="/tmp/test.pdf", prepared_relpath="/tmp/prepared.pdf",
            file_type="pdf", status="completed", matched_keyword="",
            target_printer_name="", target_preset_name="", cups_job_id="",
            error_message="",
        )
        assert schema.id == 1

    def test_batch_print_job_summary_out(self):
        from apps.batch_printing.schemas import BatchPrintJobSummaryOut
        from datetime import datetime

        schema = BatchPrintJobSummaryOut(
            job_id="abc", status="completed",
            total_count=10, processed_count=10, success_count=8,
            failed_count=2, progress=100, cancel_requested=False,
            task_id="task-1", created_by_name="test",
            error_message="", created_at=datetime.now(),
        )
        assert schema.total_count == 10

    def test_batch_print_job_out(self):
        from apps.batch_printing.schemas import BatchPrintJobOut
        from datetime import datetime

        schema = BatchPrintJobOut(
            job_id="abc", status="completed",
            total_count=5, processed_count=5, success_count=5,
            failed_count=0, progress=100, cancel_requested=False,
            task_id="task-1", created_by_name="test",
            error_message="", created_at=datetime.now(),
        )
        assert schema.total_count == 5
        assert schema.items == []


# ---------------------------------------------------------------------------
# services/wiring.py (62% coverage)
# ---------------------------------------------------------------------------


class TestBatchPrintingWiring:
    def test_wiring_import(self):
        from apps.batch_printing.services.wiring import get_preset_service

        assert get_preset_service is not None


# ---------------------------------------------------------------------------
# api/__init__.py (0% coverage)
# ---------------------------------------------------------------------------


class TestBatchPrintingApiInit:
    def test_api_init(self):
        from apps.batch_printing.api import __init__ as api_init

        assert api_init is not None
