"""Unit tests for pdf_splitting.services.job_service module."""

from __future__ import annotations

import uuid
from unittest.mock import MagicMock, patch

import pytest

from apps.core.exceptions import ValidationException


class TestPdfSplitJobServiceNormalizeSplitMode:
    """测试 _normalize_split_mode"""

    def _make_service(self):
        with patch("apps.pdf_splitting.services.job_service.build_task_submission_service"):
            from apps.pdf_splitting.services.job_service import PdfSplitJobService

            return PdfSplitJobService()

    def test_valid_mode(self) -> None:
        from apps.pdf_splitting.models import PdfSplitMode

        svc = self._make_service()
        assert svc._normalize_split_mode("content_analysis") == PdfSplitMode.CONTENT_ANALYSIS

    def test_empty_defaults(self) -> None:
        from apps.pdf_splitting.models import PdfSplitMode

        svc = self._make_service()
        assert svc._normalize_split_mode("") == PdfSplitMode.CONTENT_ANALYSIS

    def test_none_defaults(self) -> None:
        from apps.pdf_splitting.models import PdfSplitMode

        svc = self._make_service()
        assert svc._normalize_split_mode(None) == PdfSplitMode.CONTENT_ANALYSIS

    def test_invalid_defaults(self) -> None:
        from apps.pdf_splitting.models import PdfSplitMode

        svc = self._make_service()
        assert svc._normalize_split_mode("invalid") == PdfSplitMode.CONTENT_ANALYSIS


class TestPdfSplitJobServiceNormalizeOcrProfile:
    """测试 _normalize_ocr_profile"""

    def _make_service(self):
        with patch("apps.pdf_splitting.services.job_service.build_task_submission_service"):
            from apps.pdf_splitting.services.job_service import PdfSplitJobService

            return PdfSplitJobService()

    def test_valid_profile(self) -> None:
        from apps.pdf_splitting.models import PdfSplitOcrProfile

        svc = self._make_service()
        assert svc._normalize_ocr_profile("balanced") == PdfSplitOcrProfile.BALANCED

    def test_empty_defaults(self) -> None:
        from apps.pdf_splitting.models import PdfSplitOcrProfile

        svc = self._make_service()
        assert svc._normalize_ocr_profile("") == PdfSplitOcrProfile.BALANCED

    def test_invalid_defaults(self) -> None:
        from apps.pdf_splitting.models import PdfSplitOcrProfile

        svc = self._make_service()
        assert svc._normalize_ocr_profile("invalid") == PdfSplitOcrProfile.BALANCED


class TestPdfSplitJobServiceIsAbsolutePath:
    """测试 _is_absolute_path"""

    def _make_service(self):
        with patch("apps.pdf_splitting.services.job_service.build_task_submission_service"):
            from apps.pdf_splitting.services.job_service import PdfSplitJobService

            return PdfSplitJobService()

    def test_unix_absolute(self) -> None:
        svc = self._make_service()
        assert svc._is_absolute_path("/usr/local/bin") is True

    def test_windows_absolute(self) -> None:
        svc = self._make_service()
        assert svc._is_absolute_path("C:\\Users\\test") is True

    def test_relative(self) -> None:
        svc = self._make_service()
        assert svc._is_absolute_path("relative/path") is False

    def test_unc_path(self) -> None:
        svc = self._make_service()
        assert svc._is_absolute_path("\\\\server\\share") is True


class TestPdfSplitJobServiceValidateLocalPdfPath:
    """测试 _validate_local_pdf_path"""

    def _make_service(self):
        with patch("apps.pdf_splitting.services.job_service.build_task_submission_service"):
            from apps.pdf_splitting.services.job_service import PdfSplitJobService

            return PdfSplitJobService()

    def test_empty_path_raises(self) -> None:
        svc = self._make_service()
        with pytest.raises(ValidationException):
            svc._validate_local_pdf_path("")

    def test_smb_path_raises(self) -> None:
        svc = self._make_service()
        with pytest.raises(ValidationException):
            svc._validate_local_pdf_path("smb://server/share")

    def test_relative_path_raises(self) -> None:
        svc = self._make_service()
        with pytest.raises(ValidationException):
            svc._validate_local_pdf_path("relative/path.pdf")

    def test_nonexistent_path_raises(self) -> None:
        svc = self._make_service()
        with pytest.raises(ValidationException):
            svc._validate_local_pdf_path("/nonexistent/path/file.pdf")


class TestPdfSplitJobServiceNormalizeConfirmedSegments:
    """测试 _normalize_confirmed_segments"""

    def _make_service(self):
        with patch("apps.pdf_splitting.services.job_service.build_task_submission_service"):
            from apps.pdf_splitting.services.job_service import PdfSplitJobService

            return PdfSplitJobService()

    def test_empty_items_raises(self) -> None:
        svc = self._make_service()
        with pytest.raises(ValidationException):
            svc._normalize_confirmed_segments(items=[], total_pages=10)

    def test_invalid_page_start_raises(self) -> None:
        svc = self._make_service()
        items = [{"page_start": "abc", "page_end": 5}]
        with pytest.raises(ValidationException):
            svc._normalize_confirmed_segments(items=items, total_pages=10)

    def test_page_range_invalid_raises(self) -> None:
        svc = self._make_service()
        items = [{"page_start": 5, "page_end": 3}]
        with pytest.raises(ValidationException):
            svc._normalize_confirmed_segments(items=items, total_pages=10)

    def test_page_exceeds_total_raises(self) -> None:
        svc = self._make_service()
        items = [{"page_start": 1, "page_end": 20}]
        with pytest.raises(ValidationException):
            svc._normalize_confirmed_segments(items=items, total_pages=10)

    def test_valid_segments(self) -> None:
        svc = self._make_service()
        items = [{"page_start": 1, "page_end": 5, "segment_type": "evidence"}]
        result = svc._normalize_confirmed_segments(items=items, total_pages=10)
        assert len(result) >= 1
        assert result[0]["page_start"] == 1
        assert result[0]["page_end"] == 5

    def test_fills_gaps(self) -> None:
        svc = self._make_service()
        items = [{"page_start": 1, "page_end": 3, "segment_type": "evidence"}]
        result = svc._normalize_confirmed_segments(items=items, total_pages=10)
        # Should have original + gap fill
        assert len(result) >= 2
        # Last segment should fill to page 10
        assert result[-1]["page_end"] == 10

    def test_overlap_raises(self) -> None:
        svc = self._make_service()
        items = [
            {"page_start": 1, "page_end": 5, "segment_type": "evidence"},
            {"page_start": 3, "page_end": 8, "segment_type": "evidence"},
        ]
        with pytest.raises(ValidationException):
            svc._normalize_confirmed_segments(items=items, total_pages=10)

    def test_default_filename_for_unrecognized(self) -> None:
        svc = self._make_service()
        items = [{"page_start": 1, "page_end": 5}]
        result = svc._normalize_confirmed_segments(items=items, total_pages=5)
        assert "未识别材料" in result[0]["filename"]

    def test_pdf_extension_added(self) -> None:
        svc = self._make_service()
        items = [{"page_start": 1, "page_end": 5, "segment_type": "evidence", "filename": "test"}]
        result = svc._normalize_confirmed_segments(items=items, total_pages=5)
        assert result[0]["filename"].endswith(".pdf")
