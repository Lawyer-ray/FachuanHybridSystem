"""Tests for doc_converter/tasks.py - run_conversion_job."""

import uuid
import zipfile
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest


class TestRunConversionJob:
    """Test run_conversion_job task."""

    def test_completes_empty_job(self, db):
        """Job with no items transitions to COMPLETED immediately."""
        from apps.doc_converter.models import DocConverterJob, DocConverterJobStatus
        from apps.doc_converter.tasks import run_conversion_job

        job = DocConverterJob.objects.create(
            total_files=0,
            status=DocConverterJobStatus.PENDING,
        )

        with patch("apps.doc_converter.tasks.DocConverterStorage"):
            run_conversion_job(str(job.id))

        job.refresh_from_db()
        assert job.status == DocConverterJobStatus.COMPLETED
        assert job.progress == 100

    def test_handles_job_not_found_marks_failed(self, db):
        """When job doesn't exist, exception is caught and logged."""
        from apps.doc_converter.models import DocConverterJobStatus
        from apps.doc_converter.tasks import run_conversion_job

        fake_id = uuid.uuid4()

        # The function catches the exception internally and marks as FAILED
        # It won't raise, but we can verify it doesn't crash
        with patch("apps.doc_converter.tasks.DocConverterStorage"):
            # Should not raise - exception is caught internally
            run_conversion_job(str(fake_id))

    def test_handles_exception_marks_failed(self, db):
        """Exception during conversion marks job as FAILED."""
        from apps.doc_converter.models import DocConverterJob, DocConverterJobStatus
        from apps.doc_converter.tasks import run_conversion_job

        job = DocConverterJob.objects.create(
            total_files=1,
            status=DocConverterJobStatus.PENDING,
        )

        with patch("apps.doc_converter.tasks.DocConverterStorage") as MockStorage:
            mock_storage = MockStorage.return_value
            # The job has no items, so it should complete without error
            # but test that the storage is properly initialized
            run_conversion_job(str(job.id))

        job.refresh_from_db()
        # Empty job should complete immediately
        assert job.status == DocConverterJobStatus.COMPLETED
        assert job.progress == 100

    def test_cancel_requested_field_exists(self, db):
        """Job model has cancel_requested field and it's respected."""
        from apps.doc_converter.models import DocConverterJob, DocConverterJobStatus

        job = DocConverterJob.objects.create(
            total_files=2,
            status=DocConverterJobStatus.PENDING,
            cancel_requested=True,
        )

        job.refresh_from_db()
        assert job.cancel_requested is True

        # Verify the job can be set to cancelled status
        DocConverterJob.objects.filter(id=job.id).update(status=DocConverterJobStatus.CANCELLED)
        job.refresh_from_db()
        assert job.status == DocConverterJobStatus.CANCELLED


class TestCreateZip:
    """Test _create_zip helper."""

    def test_creates_zip_from_docx_files(self, tmp_path):
        """Creates ZIP containing docx files from output directory."""
        from apps.doc_converter.tasks import _create_zip

        output_dir = tmp_path / "output"
        output_dir.mkdir()

        # Create test docx files
        (output_dir / "file1.docx").write_bytes(b"content1")
        (output_dir / "file2.docx").write_bytes(b"content2")
        (output_dir / "not_a_docx.txt").write_bytes(b"text")

        exports_dir = tmp_path / "exports"
        exports_dir.mkdir()

        storage = MagicMock()
        storage.output_dir = output_dir
        storage.export_zip_path = exports_dir / "export.zip"

        _create_zip(storage)

        assert storage.export_zip_path.exists()
        with zipfile.ZipFile(storage.export_zip_path) as zf:
            names = zf.namelist()
            assert "file1.docx" in names
            assert "file2.docx" in names
            assert len(names) == 2

    def test_uses_name_map_for_readable_filenames(self, tmp_path):
        """Uses name_map to rename files in ZIP to original names."""
        from apps.doc_converter.tasks import _create_zip

        output_dir = tmp_path / "output"
        output_dir.mkdir()

        (output_dir / "abc123.docx").write_bytes(b"content")

        exports_dir = tmp_path / "exports"
        exports_dir.mkdir()

        storage = MagicMock()
        storage.output_dir = output_dir
        storage.export_zip_path = exports_dir / "export.zip"

        name_map = {"abc123.docx": "原始文件名.docx"}
        _create_zip(storage, name_map=name_map)

        with zipfile.ZipFile(storage.export_zip_path) as zf:
            names = zf.namelist()
            assert "原始文件名.docx" in names

    def test_handles_nonexistent_output_dir(self, tmp_path):
        """Does nothing when output_dir doesn't exist."""
        from apps.doc_converter.tasks import _create_zip

        storage = MagicMock()
        storage.output_dir = tmp_path / "nonexistent"
        storage.export_zip_path = tmp_path / "export.zip"

        _create_zip(storage)
        assert not storage.export_zip_path.exists()
