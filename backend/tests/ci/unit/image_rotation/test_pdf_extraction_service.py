"""image_rotation/services/pdf_extraction_service.py 单元测试。"""

from __future__ import annotations

import base64
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest

from apps.image_rotation.services.pdf_extraction_service import PDFExtractionService


@pytest.fixture
def service() -> PDFExtractionService:
    mock_orientation = MagicMock()
    mock_orientation.detect_orientation.return_value = {"rotation": 0, "confidence": 0.9, "method": "onnx"}
    return PDFExtractionService(orientation_service=mock_orientation)


# ── orientation_service lazy loading ───────────────────────────────────


class TestOrientationServiceLazy:
    def test_default_none(self) -> None:
        svc = PDFExtractionService()
        assert svc._orientation_service is None

    def test_lazy_load(self) -> None:
        svc = PDFExtractionService()
        with patch(
            "apps.image_rotation.services.pdf_extraction_service.PDFExtractionService.orientation_service",
            new_callable=lambda: property(lambda self: MagicMock()),
        ):
            pass


# ── _validate_page_count ───────────────────────────────────────────────


class TestValidatePageCount:
    def test_zero_pages(self) -> None:
        svc = PDFExtractionService()
        result = svc._validate_page_count(0, "test.pdf")
        assert result is not None
        assert "没有页面" in result["message"]

    def test_too_many_pages(self) -> None:
        svc = PDFExtractionService()
        result = svc._validate_page_count(200, "test.pdf")
        assert result is not None
        assert "超过 100 页" in result["message"]

    def test_valid_pages(self) -> None:
        svc = PDFExtractionService()
        result = svc._validate_page_count(5, "test.pdf")
        assert result is None


# ── detect_single_page_orientation ────────────────────────────────────


class TestDetectSinglePageOrientation:
    def test_valid_image(self, service: PDFExtractionService) -> None:
        fake_b64 = base64.b64encode(b"fake_png_data").decode()
        result = service.detect_single_page_orientation(fake_b64)
        assert "rotation" in result
        assert result["rotation"] == 0

    def test_with_data_url_prefix(self, service: PDFExtractionService) -> None:
        fake_b64 = base64.b64encode(b"fake_png").decode()
        result = service.detect_single_page_orientation(f"data:image/png;base64,{fake_b64}")
        assert "rotation" in result

    def test_invalid_data(self) -> None:
        svc = PDFExtractionService()
        result = svc.detect_single_page_orientation("not_base64!!!")
        assert result["rotation"] == 0
        assert result["method"] == "error"


# ── _detect_page_orientation ──────────────────────────────────────────


class TestDetectPageOrientation:
    def test_onnx_success(self) -> None:
        mock_svc = MagicMock()
        mock_svc.detect_orientation.return_value = {"rotation": 90, "confidence": 0.85, "method": "onnx"}
        svc = PDFExtractionService()
        with patch(
            "apps.image_rotation.services.orientation.onnx_service.get_onnx_orientation_service",
            return_value=mock_svc,
        ):
            result = svc._detect_page_orientation(b"image_data")
            assert result["rotation"] == 90

    def test_onnx_exception(self) -> None:
        svc = PDFExtractionService()
        with patch(
            "apps.image_rotation.services.orientation.onnx_service.get_onnx_orientation_service",
            side_effect=Exception("onnx error"),
        ):
            result = svc._detect_page_orientation(b"data")
            assert result["rotation"] == 0
            assert result["method"] == "default"


# ── _open_pdf_document error paths ────────────────────────────────────


class TestOpenPdfDocument:
    def test_base64_decode_error(self) -> None:
        svc = PDFExtractionService()
        result = svc._open_pdf_document("not_valid_base64!!!", "test.pdf")
        assert result["success"] is False
        assert "解码失败" in result["message"]

    def test_file_too_large(self) -> None:
        svc = PDFExtractionService()
        # Create base64 data that decodes to > 50MB
        large_data = b"x" * (50 * 1024 * 1024 + 1)
        b64 = base64.b64encode(large_data).decode()
        result = svc._open_pdf_document(b64, "large.pdf")
        assert result["success"] is False
        assert "50MB" in result["message"]

    def test_strips_data_prefix(self) -> None:
        svc = PDFExtractionService()
        small_pdf = b"\x00" * 100
        b64 = base64.b64encode(small_pdf).decode()
        mock_fitz = MagicMock()
        mock_fitz.open.return_value = MagicMock()
        with patch.dict("sys.modules", {"fitz": mock_fitz}):
            result = svc._open_pdf_document(f"data:application/pdf;base64,{b64}", "test.pdf")
            mock_fitz.open.assert_called_once()


# ── _extract_all_pages_without_detection ───────────────────────────────


class TestExtractWithoutDetection:
    def test_extracts_pages(self, service: PDFExtractionService) -> None:
        page = MagicMock()
        page.rect = SimpleNamespace(width=595, height=842)
        doc = [page]
        with patch.object(service, "_extract_page_image", return_value=b"png_data"):
            result = service._extract_all_pages_without_detection(doc, "test.pdf", 1)
            assert len(result) == 1
            assert result[0]["page_number"] == 1
            assert result[0]["rotation"] == 0


# ── _extract_all_pages_with_detection ─────────────────────────────────


class TestExtractWithDetection:
    def test_extracts_pages(self, service: PDFExtractionService) -> None:
        page = MagicMock()
        page.rect = SimpleNamespace(width=595, height=842)
        doc = [page]
        with patch.object(service, "_extract_page_image", return_value=b"png_data"), \
             patch.object(service, "_detect_page_orientation", return_value={"rotation": 0, "confidence": 0.9}):
            result = service._extract_all_pages_with_detection(doc, "test.pdf", 1)
            assert len(result) == 1

    def test_page_exception_logged(self, service: PDFExtractionService) -> None:
        bad_page = MagicMock()
        bad_page.__getitem__ = MagicMock(side_effect=Exception("page error"))
        doc = MagicMock()
        doc.__len__ = MagicMock(return_value=1)
        doc.__getitem__ = MagicMock(side_effect=Exception("page error"))
        result = service._extract_all_pages_with_detection(doc, "test.pdf", 1)
        assert len(result) == 0


# ── extract_pages ──────────────────────────────────────────────────────


class TestExtractPages:
    def test_open_error_returns_dict(self) -> None:
        svc = PDFExtractionService()
        error_result = {"success": False, "filename": "x.pdf", "message": "error", "pages": []}
        with patch.object(svc, "_open_pdf_document", return_value=error_result):
            result = svc.extract_pages("bad", "x.pdf")
            assert result["success"] is False

    def test_empty_pages(self) -> None:
        svc = PDFExtractionService()
        mock_doc = MagicMock()
        mock_doc.__len__ = MagicMock(return_value=2)
        mock_doc.__getitem__ = MagicMock(side_effect=Exception("fail"))
        mock_doc.close = MagicMock()
        with patch.object(svc, "_open_pdf_document", return_value=mock_doc):
            result = svc.extract_pages("data", "test.pdf")
            assert result["success"] is False
            mock_doc.close.assert_called()

    def test_success(self) -> None:
        svc = PDFExtractionService()
        mock_doc = MagicMock()
        mock_doc.__len__ = MagicMock(return_value=2)
        mock_doc.close = MagicMock()
        pages = [{"page_number": 1}, {"page_number": 2}]
        with patch.object(svc, "_open_pdf_document", return_value=mock_doc), \
             patch.object(svc, "_extract_all_pages_with_detection", return_value=pages):
            result = svc.extract_pages("data", "test.pdf")
            assert result["success"] is True
            assert len(result["pages"]) == 2
            mock_doc.close.assert_called()


# ── Constants ─────────────────────────────────────────────────────────


class TestConstants:
    def test_max_pdf_size(self) -> None:
        assert PDFExtractionService.MAX_PDF_SIZE == 50 * 1024 * 1024

    def test_max_pages(self) -> None:
        assert PDFExtractionService.MAX_PAGES == 100

    def test_dpi(self) -> None:
        assert PDFExtractionService.DPI == 150
