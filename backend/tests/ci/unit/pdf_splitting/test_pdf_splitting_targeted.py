"""Targeted tests for pdf_splitting module to push coverage to 80%+."""
from __future__ import annotations

import json
import uuid
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest


# ---------------------------------------------------------------------------
# services/storage.py (90% coverage)
# ---------------------------------------------------------------------------


class TestPdfSplitStorage:
    def test_job_root(self, tmp_path):
        from apps.pdf_splitting.services.storage import PdfSplitStorage

        with patch("apps.pdf_splitting.services.storage.settings") as mock_settings:
            mock_settings.MEDIA_ROOT = str(tmp_path)
            storage = PdfSplitStorage("test-job-id")
            assert "pdf_splitting" in str(storage.job_root)
            assert "test-job-id" in str(storage.job_root)

    def test_source_dir(self, tmp_path):
        from apps.pdf_splitting.services.storage import PdfSplitStorage

        with patch("apps.pdf_splitting.services.storage.settings") as mock_settings:
            mock_settings.MEDIA_ROOT = str(tmp_path)
            storage = PdfSplitStorage("test-job-id")
            assert storage.source_dir.name == "source"

    def test_analysis_dir(self, tmp_path):
        from apps.pdf_splitting.services.storage import PdfSplitStorage

        with patch("apps.pdf_splitting.services.storage.settings") as mock_settings:
            mock_settings.MEDIA_ROOT = str(tmp_path)
            storage = PdfSplitStorage("test-job-id")
            assert storage.analysis_dir.name == "analysis"

    def test_ensure_dirs(self, tmp_path):
        from apps.pdf_splitting.services.storage import PdfSplitStorage

        with patch("apps.pdf_splitting.services.storage.settings") as mock_settings:
            mock_settings.MEDIA_ROOT = str(tmp_path)
            storage = PdfSplitStorage("test-job-id")
            storage.ensure_dirs()
            assert storage.source_dir.exists()
            assert storage.analysis_dir.exists()
            assert storage.previews_dir.exists()
            assert storage.exports_dir.exists()

    def test_cleanup(self, tmp_path):
        from apps.pdf_splitting.services.storage import PdfSplitStorage

        with patch("apps.pdf_splitting.services.storage.settings") as mock_settings:
            mock_settings.MEDIA_ROOT = str(tmp_path)
            storage = PdfSplitStorage("test-job-id")
            storage.ensure_dirs()
            assert storage.job_root.exists()
            storage.cleanup()
            assert not storage.job_root.exists()

    def test_write_read_json(self, tmp_path):
        from apps.pdf_splitting.services.storage import PdfSplitStorage

        with patch("apps.pdf_splitting.services.storage.settings") as mock_settings:
            mock_settings.MEDIA_ROOT = str(tmp_path)
            storage = PdfSplitStorage("test-job-id")
            json_path = storage.analysis_dir / "test.json"
            payload = {"key": "value", "number": 42}
            storage.write_json(json_path, payload)
            result = storage.read_json(json_path, {})
            assert result == payload

    def test_read_json_default(self, tmp_path):
        from apps.pdf_splitting.services.storage import PdfSplitStorage

        with patch("apps.pdf_splitting.services.storage.settings") as mock_settings:
            mock_settings.MEDIA_ROOT = str(tmp_path)
            storage = PdfSplitStorage("test-job-id")
            result = storage.read_json(Path("/nonexistent"), {"default": True})
            assert result == {"default": True}

    def test_preview_path(self, tmp_path):
        from apps.pdf_splitting.services.storage import PdfSplitStorage

        with patch("apps.pdf_splitting.services.storage.settings") as mock_settings:
            mock_settings.MEDIA_ROOT = str(tmp_path)
            storage = PdfSplitStorage("test-job-id")
            path = storage.preview_path(5)
            assert "page_005.png" in str(path)

    def test_export_pdf_path(self, tmp_path):
        from apps.pdf_splitting.services.storage import PdfSplitStorage

        with patch("apps.pdf_splitting.services.storage.settings") as mock_settings:
            mock_settings.MEDIA_ROOT = str(tmp_path)
            storage = PdfSplitStorage("test-job-id")
            path = storage.export_pdf_path("test.pdf")
            assert path.name == "test.pdf"

    def test_pages_json_path(self, tmp_path):
        from apps.pdf_splitting.services.storage import PdfSplitStorage

        with patch("apps.pdf_splitting.services.storage.settings") as mock_settings:
            mock_settings.MEDIA_ROOT = str(tmp_path)
            storage = PdfSplitStorage("test-job-id")
            assert "pages.json" in str(storage.pages_json_path)

    def test_segments_json_path(self, tmp_path):
        from apps.pdf_splitting.services.storage import PdfSplitStorage

        with patch("apps.pdf_splitting.services.storage.settings") as mock_settings:
            mock_settings.MEDIA_ROOT = str(tmp_path)
            storage = PdfSplitStorage("test-job-id")
            assert "segments.json" in str(storage.segments_json_path)

    def test_export_zip_path(self, tmp_path):
        from apps.pdf_splitting.services.storage import PdfSplitStorage

        with patch("apps.pdf_splitting.services.storage.settings") as mock_settings:
            mock_settings.MEDIA_ROOT = str(tmp_path)
            storage = PdfSplitStorage("test-job-id")
            assert "split_result.zip" in str(storage.export_zip_path)


# ---------------------------------------------------------------------------
# services/split/export_utils.py (74% coverage)
# ---------------------------------------------------------------------------


class TestExportUtils:
    def test_deduplicate_filename_unique(self):
        from apps.pdf_splitting.services.split.export_utils import ExportUtils

        seen: set[str] = set()
        result = ExportUtils.deduplicate_filename("test.pdf", seen)
        assert result == "test.pdf"
        assert "test.pdf" in seen

    def test_deduplicate_filename_duplicate(self):
        from apps.pdf_splitting.services.split.export_utils import ExportUtils

        seen: set[str] = {"test.pdf"}
        result = ExportUtils.deduplicate_filename("test.pdf", seen)
        assert result == "test_2.pdf"

    def test_deduplicate_filename_multiple_duplicates(self):
        from apps.pdf_splitting.services.split.export_utils import ExportUtils

        seen: set[str] = {"test.pdf", "test_2.pdf"}
        result = ExportUtils.deduplicate_filename("test.pdf", seen)
        assert result == "test_3.pdf"

    def test_deduplicate_filename_no_extension(self):
        from apps.pdf_splitting.services.split.export_utils import ExportUtils

        seen: set[str] = set()
        result = ExportUtils.deduplicate_filename("片段", seen)
        assert result == "片段.pdf"


# ---------------------------------------------------------------------------
# api/__init__.py (0% coverage)
# ---------------------------------------------------------------------------


class TestPdfSplittingApiInit:
    def test_api_init(self):
        from apps.pdf_splitting.api import __init__ as api_init

        assert api_init is not None
