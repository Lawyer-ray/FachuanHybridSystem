"""Final coverage tests for invoice_recognition module."""

from __future__ import annotations

import io
from decimal import Decimal
from pathlib import Path
from unittest.mock import MagicMock, Mock, patch

import pytest
from django.core.exceptions import ValidationError

from apps.invoice_recognition.services.invoice_recognition_service import InvoiceRecognitionService


# ============================================================================
# _validate_file tests
# ============================================================================


class TestValidateFile:
    def _make_service(self):
        return InvoiceRecognitionService(
            ocr_service=MagicMock(),
            pdf_extractor=MagicMock(),
            parser=MagicMock(),
        )

    def test_valid_pdf(self):
        svc = self._make_service()
        f = Mock()
        f.name = "test.pdf"
        f.size = 1024
        svc._validate_file(f)  # should not raise

    def test_valid_jpg(self):
        svc = self._make_service()
        f = Mock()
        f.name = "photo.jpg"
        f.size = 2048
        svc._validate_file(f)

    def test_valid_png(self):
        svc = self._make_service()
        f = Mock()
        f.name = "image.png"
        f.size = 512
        svc._validate_file(f)

    def test_invalid_extension(self):
        svc = self._make_service()
        f = Mock()
        f.name = "file.docx"
        f.size = 1024
        with pytest.raises(ValidationError):
            svc._validate_file(f)

    def test_too_large(self):
        svc = self._make_service()
        f = Mock()
        f.name = "big.pdf"
        f.size = 25 * 1024 * 1024  # 25 MB > 20 MB limit
        with pytest.raises(ValidationError):
            svc._validate_file(f)

    def test_uppercase_extension(self):
        svc = self._make_service()
        f = Mock()
        f.name = "FILE.PDF"
        f.size = 100
        svc._validate_file(f)  # should not raise


# ============================================================================
# _process_image tests
# ============================================================================


class TestProcessImage:
    def test_calls_ocr(self):
        mock_ocr = MagicMock()
        mock_ocr.recognize.return_value = "OCR text"
        svc = InvoiceRecognitionService(
            ocr_service=mock_ocr,
            pdf_extractor=MagicMock(),
            parser=MagicMock(),
        )
        result = svc._process_image(Path("/fake/image.jpg"))
        assert result == "OCR text"
        mock_ocr.recognize.assert_called_once()


# ============================================================================
# _process_pdf tests
# ============================================================================


class TestProcessPdf:
    def test_direct_text_extraction(self):
        mock_extractor = MagicMock()
        mock_extractor.extract.return_value = "PDF text content"
        svc = InvoiceRecognitionService(
            ocr_service=MagicMock(),
            pdf_extractor=mock_extractor,
            parser=MagicMock(),
        )
        result = svc._process_pdf(Path("/fake/file.pdf"))
        assert result == "PDF text content"

    @patch("shutil.rmtree")
    def test_fallback_to_ocr(self, mock_rmtree):
        mock_extractor = MagicMock()
        mock_extractor.extract.return_value = None
        mock_extractor.pdf_to_images.return_value = [Path("/tmp/img1.png"), Path("/tmp/img2.png")], "/tmp/dir"
        mock_ocr = MagicMock()
        mock_ocr.recognize.side_effect = ["page1 text", "page2 text"]
        svc = InvoiceRecognitionService(
            ocr_service=mock_ocr,
            pdf_extractor=mock_extractor,
            parser=MagicMock(),
        )
        result = svc._process_pdf(Path("/fake/file.pdf"))
        assert "page1 text" in result
        assert "page2 text" in result


# ============================================================================
# _check_duplicate tests
# ============================================================================


class TestCheckDuplicate:
    def _make_record(self, **kwargs):
        record = MagicMock()
        record.invoice_number = kwargs.get("invoice_number", "INV001")
        record.task_id = kwargs.get("task_id", 1)
        record.id = kwargs.get("id", 10)
        record.total_amount = kwargs.get("total_amount", Decimal("100"))
        record.invoice_date = kwargs.get("invoice_date", "2025-01-01")
        record.original_filename = kwargs.get("original_filename", "test.pdf")
        return record

    @patch("apps.invoice_recognition.services.invoice_recognition_service.InvoiceRecord")
    def test_no_duplicate(self, MockRecord):
        MockRecord.objects.filter.return_value.first.return_value = None
        MockRecord.objects.filter.return_value.exclude.return_value.first.return_value = None
        svc = InvoiceRecognitionService(MagicMock(), MagicMock(), MagicMock())
        record = self._make_record()
        is_dup, dup_id = svc._check_duplicate(record)
        assert is_dup is False
        assert dup_id is None

    @patch("apps.invoice_recognition.services.invoice_recognition_service.InvoiceRecord")
    def test_duplicate_by_invoice_number_same_task(self, MockRecord):
        original = MagicMock()
        original.id = 5
        mock_qs = MagicMock()
        mock_qs.first.return_value = original
        MockRecord.objects.filter.return_value = mock_qs
        svc = InvoiceRecognitionService(MagicMock(), MagicMock(), MagicMock())
        record = self._make_record(invoice_number="INV001")
        is_dup, dup_id = svc._check_duplicate(record)
        assert is_dup is True
        assert dup_id == 5


# ============================================================================
# get_category_subtotal tests
# ============================================================================


class TestGetCategorySubtotal:
    @patch("apps.invoice_recognition.services.invoice_recognition_service.InvoiceRecord")
    def test_returns_aggregated_sum(self, MockRecord):
        MockRecord.objects.filter.return_value.aggregate.return_value = {"total": Decimal("500")}
        svc = InvoiceRecognitionService(MagicMock(), MagicMock(), MagicMock())
        result = svc.get_category_subtotal(1, "travel")
        assert result == Decimal("500")

    @patch("apps.invoice_recognition.services.invoice_recognition_service.InvoiceRecord")
    def test_returns_zero_when_none(self, MockRecord):
        MockRecord.objects.filter.return_value.aggregate.return_value = {"total": None}
        svc = InvoiceRecognitionService(MagicMock(), MagicMock(), MagicMock())
        result = svc.get_category_subtotal(1, "travel")
        assert result == Decimal("0")


# ============================================================================
# get_total_amount tests
# ============================================================================


class TestGetTotalAmount:
    @patch("apps.invoice_recognition.services.invoice_recognition_service.InvoiceRecord")
    def test_returns_total(self, MockRecord):
        MockRecord.objects.filter.return_value.aggregate.return_value = {"total": Decimal("1000")}
        svc = InvoiceRecognitionService(MagicMock(), MagicMock(), MagicMock())
        result = svc.get_total_amount(1)
        assert result == Decimal("1000")


# ============================================================================
# ALLOWED_EXTENSIONS tests
# ============================================================================


class TestAllowedExtensions:
    def test_contains_pdf(self):
        assert ".pdf" in InvoiceRecognitionService.ALLOWED_EXTENSIONS

    def test_contains_jpg(self):
        assert ".jpg" in InvoiceRecognitionService.ALLOWED_EXTENSIONS

    def test_contains_jpeg(self):
        assert ".jpeg" in InvoiceRecognitionService.ALLOWED_EXTENSIONS

    def test_contains_png(self):
        assert ".png" in InvoiceRecognitionService.ALLOWED_EXTENSIONS

    def test_max_file_size(self):
        assert InvoiceRecognitionService.MAX_FILE_SIZE == 20 * 1024 * 1024
