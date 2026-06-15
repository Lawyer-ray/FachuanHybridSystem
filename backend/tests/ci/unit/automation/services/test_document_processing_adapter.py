"""Tests for automation.services.document.document_processing_service_adapter.

Covers: extract_text_from_pdf, extract_text_from_docx, extract_text_from_image,
process_uploaded_document, extract_document_content_by_path, and internal variants.
"""
from __future__ import annotations

from types import SimpleNamespace
from typing import Any
from unittest.mock import MagicMock, patch

import pytest


class TestDocumentProcessingServiceAdapterInit:
    def test_init(self):
        from apps.automation.services.document.document_processing_service_adapter import (
            DocumentProcessingServiceAdapter,
        )
        svc = DocumentProcessingServiceAdapter()
        assert svc is not None


class TestExtractTextFromPdf:
    def _make_svc(self):
        from apps.automation.services.document.document_processing_service_adapter import (
            DocumentProcessingServiceAdapter,
        )
        return DocumentProcessingServiceAdapter()

    def test_success(self):
        svc = self._make_svc()
        with patch("apps.automation.services.document.document_processing.process_pdf") as mock_proc:
            mock_proc.return_value = ("image_url", "extracted text")
            result = svc.extract_text_from_pdf("/path/to/file.pdf", limit=100, preview_page=1)
            assert result["text"] == "extracted text"
            assert result["image_url"] == "image_url"
            assert result["file_path"] == "/path/to/file.pdf"
            assert result["file_type"] == "pdf"

    def test_exception(self):
        svc = self._make_svc()
        with patch("apps.automation.services.document.document_processing.process_pdf") as mock_proc:
            mock_proc.side_effect = Exception("PDF error")
            with pytest.raises(Exception, match="PDF文件处理失败"):
                svc.extract_text_from_pdf("/path/to/file.pdf")


class TestExtractTextFromDocx:
    def _make_svc(self):
        from apps.automation.services.document.document_processing_service_adapter import (
            DocumentProcessingServiceAdapter,
        )
        return DocumentProcessingServiceAdapter()

    def test_success(self):
        svc = self._make_svc()
        with patch("apps.automation.services.document.document_processing.extract_docx_text") as mock_proc:
            mock_proc.return_value = "docx text"
            result = svc.extract_text_from_docx("/path/to/file.docx", limit=100)
            assert result == "docx text"

    def test_exception(self):
        svc = self._make_svc()
        with patch("apps.automation.services.document.document_processing.extract_docx_text") as mock_proc:
            mock_proc.side_effect = Exception("DOCX error")
            with pytest.raises(Exception, match="DOCX文件处理失败"):
                svc.extract_text_from_docx("/path/to/file.docx")


class TestExtractTextFromImage:
    def _make_svc(self):
        from apps.automation.services.document.document_processing_service_adapter import (
            DocumentProcessingServiceAdapter,
        )
        return DocumentProcessingServiceAdapter()

    def test_success_no_limit(self):
        svc = self._make_svc()
        with patch("apps.automation.services.document.document_processing.extract_text_from_image_with_rapidocr") as mock_proc:
            mock_proc.return_value = "OCR text"
            result = svc.extract_text_from_image("/path/to/img.png")
            assert result == "OCR text"

    def test_success_with_limit(self):
        svc = self._make_svc()
        with patch("apps.automation.services.document.document_processing.extract_text_from_image_with_rapidocr") as mock_proc:
            mock_proc.return_value = "A" * 200
            result = svc.extract_text_from_image("/path/to/img.png", limit=50)
            assert len(result) == 50

    def test_exception(self):
        svc = self._make_svc()
        with patch("apps.automation.services.document.document_processing.extract_text_from_image_with_rapidocr") as mock_proc:
            mock_proc.side_effect = Exception("OCR error")
            with pytest.raises(Exception, match="图片OCR处理失败"):
                svc.extract_text_from_image("/path/to/img.png")


class TestProcessUploadedDocument:
    def _make_svc(self):
        from apps.automation.services.document.document_processing_service_adapter import (
            DocumentProcessingServiceAdapter,
        )
        return DocumentProcessingServiceAdapter()

    def test_success(self):
        svc = self._make_svc()
        uploaded_file = SimpleNamespace(name="test.pdf", size=1024)
        with patch("apps.automation.services.document.document_processing.process_uploaded_document") as mock_proc:
            mock_proc.return_value = SimpleNamespace(text="content", image_url="url")
            result = svc.process_uploaded_document(uploaded_file)
            assert result["text"] == "content"
            assert result["file_name"] == "test.pdf"
            assert result["file_size"] == 1024

    def test_exception(self):
        svc = self._make_svc()
        uploaded_file = SimpleNamespace(name="test.pdf", size=1024)
        with patch("apps.automation.services.document.document_processing.process_uploaded_document") as mock_proc:
            mock_proc.side_effect = Exception("error")
            with pytest.raises(Exception, match="文档内容提取失败"):
                svc.process_uploaded_document(uploaded_file)


class TestExtractDocumentContentByPath:
    def _make_svc(self):
        from apps.automation.services.document.document_processing_service_adapter import (
            DocumentProcessingServiceAdapter,
        )
        return DocumentProcessingServiceAdapter()

    def test_success(self):
        svc = self._make_svc()
        with patch("apps.automation.services.document.document_processing.extract_document_content") as mock_proc:
            mock_proc.return_value = SimpleNamespace(text="content", image_url="url")
            result = svc.extract_document_content_by_path("/path/to/file.pdf")
            assert result["text"] == "content"
            assert result["file_path"] == "/path/to/file.pdf"

    def test_exception(self):
        svc = self._make_svc()
        with patch("apps.automation.services.document.document_processing.extract_document_content") as mock_proc:
            mock_proc.side_effect = Exception("error")
            with pytest.raises(Exception, match="文档内容提取失败"):
                svc.extract_document_content_by_path("/path/to/file.pdf")


class TestInternalVariants:
    """Test that internal methods delegate to public methods."""

    def _make_svc(self):
        from apps.automation.services.document.document_processing_service_adapter import (
            DocumentProcessingServiceAdapter,
        )
        return DocumentProcessingServiceAdapter()

    def test_extract_text_from_pdf_internal(self):
        svc = self._make_svc()
        with patch.object(svc, "extract_text_from_pdf", return_value={"text": "ok"}) as mock:
            result = svc.extract_text_from_pdf_internal("/path/file.pdf", limit=10)
            mock.assert_called_once_with("/path/file.pdf", 10, None)
            assert result == {"text": "ok"}

    def test_extract_text_from_docx_internal(self):
        svc = self._make_svc()
        with patch.object(svc, "extract_text_from_docx", return_value="text") as mock:
            result = svc.extract_text_from_docx_internal("/path/file.docx", limit=10)
            mock.assert_called_once_with("/path/file.docx", 10)
            assert result == "text"

    def test_extract_text_from_image_internal(self):
        svc = self._make_svc()
        with patch.object(svc, "extract_text_from_image", return_value="ocr") as mock:
            result = svc.extract_text_from_image_internal("/path/img.png", limit=10)
            mock.assert_called_once_with("/path/img.png", 10)
            assert result == "ocr"

    def test_process_uploaded_document_internal(self):
        svc = self._make_svc()
        uploaded_file = SimpleNamespace(name="f.pdf")
        with patch.object(svc, "process_uploaded_document", return_value={"text": "ok"}) as mock:
            result = svc.process_uploaded_document_internal(uploaded_file, limit=10)
            mock.assert_called_once_with(uploaded_file, 10, None)
            assert result == {"text": "ok"}

    def test_extract_document_content_by_path_internal(self):
        svc = self._make_svc()
        with patch.object(svc, "extract_document_content_by_path", return_value={"text": "ok"}) as mock:
            result = svc.extract_document_content_by_path_internal("/path/file.pdf", limit=10)
            mock.assert_called_once_with("/path/file.pdf", 10, None)
            assert result == {"text": "ok"}
