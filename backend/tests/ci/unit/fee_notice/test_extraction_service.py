"""FeeNoticeExtractionService tests with mocked dependencies."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from apps.fee_notice.services.extraction.extraction_service import FeeNoticeExtractionService


class TestFeeNoticeExtractionService:
    def test_init_defaults(self):
        svc = FeeNoticeExtractionService()
        assert svc._text_service is None
        assert svc._detector is None
        assert svc._extractor is None

    def test_init_with_injection(self):
        mock_text = MagicMock()
        mock_detector = MagicMock()
        mock_extractor = MagicMock()
        svc = FeeNoticeExtractionService(
            text_service=mock_text, detector=mock_detector, extractor=mock_extractor
        )
        assert svc.text_service is mock_text
        assert svc.detector is mock_detector
        assert svc.extractor is mock_extractor

    def test_is_supported_format(self):
        svc = FeeNoticeExtractionService()
        assert svc._is_supported_format("test.pdf") is True
        assert svc._is_supported_format("test.docx") is False
        assert svc._is_supported_format("test.PDF") is True

    def test_extract_from_files_unsupported_format(self):
        svc = FeeNoticeExtractionService()
        result = svc.extract_from_files(["test.docx"])
        assert len(result.errors) == 1
        assert result.errors[0]["code"] == "UNSUPPORTED_FORMAT"

    def test_extract_from_files_nonexistent(self):
        svc = FeeNoticeExtractionService()
        result = svc.extract_from_files(["/nonexistent/file.pdf"])
        assert len(result.errors) == 1
        assert result.errors[0]["code"] == "FILE_NOT_FOUND"

    def test_extract_from_files_empty_list(self):
        svc = FeeNoticeExtractionService()
        result = svc.extract_from_files([])
        assert result.total_files == 0
        assert result.notices == []

    def test_cleanup_temp_files(self):
        svc = FeeNoticeExtractionService()
        # Should not raise even with non-existent paths
        svc.cleanup_temp_files([Path("/tmp/nonexistent_file.pdf")])

    def test_extract_from_files_debug_mode(self):
        svc = FeeNoticeExtractionService()
        result = svc.extract_from_files(["/nonexistent/file.pdf"], debug=True)
        assert len(result.debug_logs) > 0

    def test_save_uploaded_files_unsupported(self):
        svc = FeeNoticeExtractionService()
        mock_file = MagicMock()
        mock_file.name = "test.docx"
        saved, errors = svc.save_uploaded_files([mock_file])
        assert len(errors) == 1
        assert "不支持" in errors[0]["error"]
