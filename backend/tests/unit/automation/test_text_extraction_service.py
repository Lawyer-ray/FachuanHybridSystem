"""
TextExtractionService 单元测试

测试文本提取服务的基本功能。
"""

import os
import tempfile
from unittest.mock import MagicMock, patch

import pytest

from apps.automation.services.court_document_recognition import (
    SUPPORTED_EXTENSIONS,
    SUPPORTED_IMAGE_EXTENSIONS,
    SUPPORTED_PDF_EXTENSIONS,
    TextExtractionResult,
    TextExtractionService,
)
from apps.automation.services.court_document_recognition.text_extraction_service import (
    get_supported_extensions,
    is_supported_format,
)
from apps.core.exceptions import ValidationException
from apps.core.path import Path


class TestTextExtractionServiceBasic:
    """基本功能测试"""

    def test_service_instantiation(self):
        """测试服务实例化"""
        service = TextExtractionService()
        assert service is not None
        assert service._text_limit is None

    def test_service_with_text_limit(self):
        """测试带字数限制的服务实例化"""
        service = TextExtractionService(text_limit=1000)
        assert service._text_limit == 1000

    def test_supported_extensions(self):
        """测试支持的扩展名"""
        assert ".pdf" in SUPPORTED_EXTENSIONS
        assert ".jpg" in SUPPORTED_EXTENSIONS
        assert ".jpeg" in SUPPORTED_EXTENSIONS
        assert ".png" in SUPPORTED_EXTENSIONS
        assert ".doc" not in SUPPORTED_EXTENSIONS
        assert ".docx" not in SUPPORTED_EXTENSIONS


class TestIsSuportedFormat:
    """is_supported_format 方法测试"""

    def test_pdf_extension(self):
        """测试 PDF 扩展名"""
        assert is_supported_format(".pdf") is True
        assert is_supported_format(".PDF") is True

    def test_image_extensions(self):
        """测试图片扩展名"""
        assert is_supported_format(".jpg") is True
        assert is_supported_format(".jpeg") is True
        assert is_supported_format(".png") is True
        assert is_supported_format(".JPG") is True

    def test_unsupported_extensions(self):
        """测试不支持的扩展名"""
        assert is_supported_format(".doc") is False
        assert is_supported_format(".docx") is False
        assert is_supported_format(".txt") is False

    def test_file_path_with_extension(self):
        """测试完整文件路径"""
        assert is_supported_format("test.pdf") is True
        assert is_supported_format("/path/to/file.jpg") is True
        assert is_supported_format("document.doc") is False

    def test_get_supported_extensions(self):
        """测试获取支持的扩展名列表"""
        extensions = get_supported_extensions()
        assert isinstance(extensions, tuple)
        assert ".pdf" in extensions
        assert ".jpg" in extensions


class TestExtractTextValidation:
    """extract_text 方法验证测试"""

    def test_file_not_found(self):
        """测试文件不存在"""
        service = TextExtractionService()
        with pytest.raises(ValidationException) as exc_info:
            service.extract_text("/nonexistent/file.pdf")

        assert exc_info.value.code == "FILE_NOT_FOUND"

    def test_unsupported_format(self):
        """测试不支持的文件格式"""
        service = TextExtractionService()

        # 创建临时文件
        with tempfile.NamedTemporaryFile(suffix=".doc", delete=False) as f:
            f.write(b"test content")
            temp_path = f.name

        try:
            with pytest.raises(ValidationException) as exc_info:
                service.extract_text(temp_path)

            assert exc_info.value.code == "UNSUPPORTED_FILE_FORMAT"
        finally:
            os.unlink(temp_path)


class TestExtractFromPdf:
    """PDF 文本提取测试"""

    @patch(
        "apps.automation.services.court_document_recognition.text_extraction_service.TextExtractionService._extract_pdf_text_direct"
    )
    def test_pdf_direct_extraction_success(self, mock_extract):
        """测试 PDF 直接提取成功"""
        mock_extract.return_value = "这是从PDF直接提取的文字"

        service = TextExtractionService()

        # 创建临时 PDF 文件
        with tempfile.NamedTemporaryFile(suffix=".pdf", delete=False) as f:
            f.write(b"%PDF-1.4 test")
            temp_path = f.name

        try:
            result = service._extract_from_pdf(temp_path)

            assert result.success is True
            assert result.extraction_method == "pdf_direct"
            assert result.text == "这是从PDF直接提取的文字"
        finally:
            os.unlink(temp_path)

    @patch(
        "apps.automation.services.court_document_recognition.text_extraction_service.TextExtractionService._extract_pdf_text_direct"
    )
    @patch(
        "apps.automation.services.court_document_recognition.text_extraction_service.TextExtractionService._extract_pdf_with_ocr"
    )
    def test_pdf_fallback_to_ocr(self, mock_ocr, mock_direct):
        """测试 PDF 降级到 OCR"""
        mock_direct.return_value = ""  # 直接提取失败
        mock_ocr.return_value = TextExtractionResult(text="OCR识别的文字", extraction_method="ocr", success=True)

        service = TextExtractionService()

        with tempfile.NamedTemporaryFile(suffix=".pdf", delete=False) as f:
            f.write(b"%PDF-1.4 test")
            temp_path = f.name

        try:
            result = service._extract_from_pdf(temp_path)

            assert result.success is True
            assert result.extraction_method == "ocr"
            mock_ocr.assert_called_once()
        finally:
            os.unlink(temp_path)


class TestExtractFromImage:
    """图片文本提取测试"""

    @patch("apps.automation.services.document.document_processing.extract_text_from_image_with_rapidocr")
    def test_image_ocr_success(self, mock_ocr):
        """测试图片 OCR 成功"""
        mock_ocr.return_value = "图片中识别的文字"

        service = TextExtractionService()

        with tempfile.NamedTemporaryFile(suffix=".jpg", delete=False) as f:
            f.write(b"fake image content")
            temp_path = f.name

        try:
            result = service._extract_from_image(temp_path)

            assert result.success is True
            assert result.extraction_method == "ocr"
            assert result.text == "图片中识别的文字"
        finally:
            os.unlink(temp_path)

    @patch("apps.automation.services.document.document_processing.extract_text_from_image_with_rapidocr")
    def test_image_ocr_empty_result(self, mock_ocr):
        """测试图片 OCR 返回空结果"""
        mock_ocr.return_value = ""

        service = TextExtractionService()

        with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as f:
            f.write(b"fake image content")
            temp_path = f.name

        try:
            result = service._extract_from_image(temp_path)

            assert result.success is False
            assert result.extraction_method == "ocr"
            assert result.text == ""
        finally:
            os.unlink(temp_path)


class TestTextLimit:
    """文本限制测试"""

    @patch("apps.automation.services.document.document_processing.extract_text_from_image_with_rapidocr")
    def test_text_limit_applied(self, mock_ocr):
        """测试文本限制被应用"""
        long_text = "这是一段很长的文字" * 100
        mock_ocr.return_value = long_text

        service = TextExtractionService(text_limit=50)

        with tempfile.NamedTemporaryFile(suffix=".jpg", delete=False) as f:
            f.write(b"fake image content")
            temp_path = f.name

        try:
            result = service._extract_from_image(temp_path)

            assert len(result.text) == 50
        finally:
            os.unlink(temp_path)
