"""Tests for invoice_recognition: quick_recognition_service and recognition_result."""
from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest
from django.core.exceptions import ValidationError
from django.core.files.uploadedfile import SimpleUploadedFile

from apps.invoice_recognition.services.invoice_parser import InvoiceParser, ParsedInvoice
from apps.invoice_recognition.services.quick_recognition_service import QuickRecognitionService
from apps.invoice_recognition.services.recognition_result import RecognitionResult


# ---------------------------------------------------------------------------
# RecognitionResult
# ---------------------------------------------------------------------------


class TestRecognitionResultDataclass:
    def test_defaults(self) -> None:
        r = RecognitionResult(filename="test.pdf", success=True)
        assert r.data is None
        assert r.error is None

    def test_with_data(self) -> None:
        inv = ParsedInvoice(invoice_code="12345")
        r = RecognitionResult(filename="inv.pdf", success=True, data=inv)
        assert r.data.invoice_code == "12345"

    def test_with_error(self) -> None:
        r = RecognitionResult(filename="bad.pdf", success=False, error="bad file")
        assert r.error == "bad file"


# ---------------------------------------------------------------------------
# QuickRecognitionService
# ---------------------------------------------------------------------------


class TestQuickRecognitionValidateFile:
    def _svc(self) -> QuickRecognitionService:
        return QuickRecognitionService(
            ocr_service=MagicMock(),
            pdf_extractor=MagicMock(),
            parser=InvoiceParser(),
        )

    def test_valid_pdf(self) -> None:
        svc = self._svc()
        f = SimpleUploadedFile("test.pdf", b"content", content_type="application/pdf")
        # Should not raise
        svc._validate_file(f)

    def test_valid_jpg(self) -> None:
        svc = self._svc()
        f = SimpleUploadedFile("test.jpg", b"content", content_type="image/jpeg")
        svc._validate_file(f)

    def test_invalid_extension(self) -> None:
        svc = self._svc()
        f = SimpleUploadedFile("test.docx", b"content", content_type="application/msword")
        with pytest.raises(ValidationError, match="不支持的文件格式"):
            svc._validate_file(f)

    def test_too_large_file(self) -> None:
        svc = self._svc()
        big_content = b"x" * (21 * 1024 * 1024)  # 21 MB
        f = SimpleUploadedFile("big.pdf", big_content, content_type="application/pdf")
        with pytest.raises(ValidationError, match="超过限制"):
            svc._validate_file(f)


class TestQuickRecognitionRecognizeFiles:
    def test_validation_error_returns_failure(self) -> None:
        svc = QuickRecognitionService(
            ocr_service=MagicMock(),
            pdf_extractor=MagicMock(),
            parser=InvoiceParser(),
        )
        f = SimpleUploadedFile("test.docx", b"content", content_type="application/msword")
        results = svc.recognize_files([f])
        assert len(results) == 1
        assert results[0].success is False
        assert "不支持的文件格式" in results[0].error

    def test_empty_files(self) -> None:
        svc = QuickRecognitionService(
            ocr_service=MagicMock(),
            pdf_extractor=MagicMock(),
            parser=InvoiceParser(),
        )
        results = svc.recognize_files([])
        assert results == []

    def test_generic_exception_returns_failure(self) -> None:
        mock_parser = MagicMock()
        mock_parser.parse.side_effect = RuntimeError("boom")
        svc = QuickRecognitionService(
            ocr_service=MagicMock(),
            pdf_extractor=MagicMock(),
            parser=mock_parser,
        )
        f = SimpleUploadedFile("test.jpg", b"content", content_type="image/jpeg")
        results = svc.recognize_files([f])
        assert len(results) == 1
        assert results[0].success is False
        assert "识别失败" in results[0].error
