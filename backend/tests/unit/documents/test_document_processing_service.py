"""
DocumentProcessingServiceAdapter 单元测试

测试文档处理服务的核心功能
"""

from pathlib import Path
from unittest.mock import MagicMock, Mock, patch

import pytest

from apps.automation.services.document.document_processing_service_adapter import DocumentProcessingServiceAdapter
from apps.core.exceptions import AutomationExceptions, ValidationException


class TestDocumentProcessingServiceAdapter:
    """文档处理服务适配器测试"""

    def setup_method(self):
        """每个测试方法前执行"""
        self.service = DocumentProcessingServiceAdapter()

    @patch("apps.automation.services.document.document_processing.process_pdf")
    def test_extract_text_from_pdf_success(self, mock_process_pdf):
        """测试从 PDF 提取文本成功"""
        # 配置 Mock
        mock_process_pdf.return_value = (None, "这是PDF文本内容")

        # 执行测试
        result = self.service.extract_text_from_pdf(file_path="/path/to/test.pdf", limit=1000)

        # 断言结果
        assert result["text"] == "这是PDF文本内容"
        assert result["image_url"] is None
        assert result["file_path"] == "/path/to/test.pdf"
        assert result["file_type"] == "pdf"

        # 验证调用
        mock_process_pdf.assert_called_once_with("/path/to/test.pdf", 1000, None)

    @patch("apps.automation.services.document.document_processing.process_pdf")
    def test_extract_text_from_pdf_with_preview_page(self, mock_process_pdf):
        """测试从 PDF 提取文本并指定预览页"""
        # 配置 Mock
        mock_process_pdf.return_value = (None, "第二页内容")

        # 执行测试
        result = self.service.extract_text_from_pdf(file_path="/path/to/test.pdf", limit=500, preview_page=2)

        # 断言结果
        assert result["text"] == "第二页内容"

        # 验证调用
        mock_process_pdf.assert_called_once_with("/path/to/test.pdf", 500, 2)

    @patch("apps.automation.services.document.document_processing.process_pdf")
    def test_extract_text_from_pdf_failure(self, mock_process_pdf):
        """测试从 PDF 提取文本失败"""
        # 配置 Mock 抛出异常
        mock_process_pdf.side_effect = Exception("PDF 处理失败")

        # 断言抛出异常
        from apps.core.exceptions import ValidationException

        with pytest.raises(ValidationException) as exc_info:
            self.service.extract_text_from_pdf(file_path="/path/to/test.pdf")

        assert "PDF" in str(exc_info.value.message)
        assert "PDF 处理失败" in str(exc_info.value.message)

    @patch("apps.automation.services.document.document_processing.extract_docx_text")
    def test_extract_text_from_docx_success(self, mock_extract_docx):
        """测试从 DOCX 提取文本成功"""
        # 配置 Mock
        mock_extract_docx.return_value = "这是DOCX文本内容"

        # 执行测试
        result = self.service.extract_text_from_docx(file_path="/path/to/test.docx", limit=1000)

        # 断言结果
        assert result == "这是DOCX文本内容"

        # 验证调用
        mock_extract_docx.assert_called_once_with("/path/to/test.docx", limit=1000)

    @patch("apps.automation.services.document.document_processing.extract_docx_text")
    def test_extract_text_from_docx_no_limit(self, mock_extract_docx):
        """测试从 DOCX 提取文本不限制长度"""
        # 配置 Mock
        mock_extract_docx.return_value = "完整的DOCX内容"

        # 执行测试
        result = self.service.extract_text_from_docx(file_path="/path/to/test.docx")

        # 断言结果
        assert result == "完整的DOCX内容"

        # 验证调用
        mock_extract_docx.assert_called_once_with("/path/to/test.docx", limit=None)

    @patch("apps.automation.services.document.document_processing.extract_docx_text")
    def test_extract_text_from_docx_failure(self, mock_extract_docx):
        """测试从 DOCX 提取文本失败"""
        # 配置 Mock 抛出异常
        mock_extract_docx.side_effect = Exception("DOCX 处理失败")

        # 断言抛出异常
        from apps.core.exceptions import ValidationException

        with pytest.raises(ValidationException) as exc_info:
            self.service.extract_text_from_docx(file_path="/path/to/test.docx")

        assert "DOCX" in str(exc_info.value.message)
        assert "DOCX 处理失败" in str(exc_info.value.message)

    @patch("apps.automation.services.document.document_processing.extract_text_from_image_with_rapidocr")
    def test_extract_text_from_image_success(self, mock_ocr):
        """测试从图片提取文本成功（OCR）"""
        # 配置 Mock
        mock_ocr.return_value = "这是OCR识别的文本"

        # 执行测试
        result = self.service.extract_text_from_image(file_path="/path/to/test.jpg", limit=500)

        # 断言结果
        assert result == "这是OCR识别的文本"

        # 验证调用
        mock_ocr.assert_called_once_with("/path/to/test.jpg")

    @patch("apps.automation.services.document.document_processing.extract_text_from_image_with_rapidocr")
    def test_extract_text_from_image_with_limit(self, mock_ocr):
        """测试从图片提取文本并限制长度"""
        # 配置 Mock
        mock_ocr.return_value = "这是一段很长的OCR识别文本内容" * 100

        # 执行测试
        result = self.service.extract_text_from_image(file_path="/path/to/test.jpg", limit=50)

        # 断言结果
        assert len(result) == 50
        assert result == ("这是一段很长的OCR识别文本内容" * 100)[:50]

    @patch("apps.automation.services.document.document_processing.extract_text_from_image_with_rapidocr")
    def test_extract_text_from_image_failure(self, mock_ocr):
        """测试从图片提取文本失败"""
        # 配置 Mock 抛出异常
        mock_ocr.side_effect = Exception("OCR 识别失败")

        # 断言抛出异常
        from apps.core.exceptions import ValidationException

        with pytest.raises(ValidationException) as exc_info:
            self.service.extract_text_from_image(file_path="/path/to/test.jpg")

        assert "OCR" in str(exc_info.value.message)
        assert "OCR 识别失败" in str(exc_info.value.message)

    @patch("apps.automation.services.document.document_processing.process_uploaded_document")
    def test_process_uploaded_document_success(self, mock_process):
        """测试处理上传文档成功"""
        # 创建 Mock 上传文件
        mock_file = Mock()
        mock_file.name = "test.pdf"
        mock_file.size = 1024

        # 配置 Mock 返回值
        mock_result = Mock()
        mock_result.text = "文档内容"
        mock_result.image_url = None
        mock_process.return_value = mock_result

        # 执行测试
        result = self.service.process_uploaded_document(uploaded_file=mock_file, limit=1000)

        # 断言结果
        assert result["text"] == "文档内容"
        assert result["image_url"] is None
        assert result["file_name"] == "test.pdf"
        assert result["file_size"] == 1024

        # 验证调用
        mock_process.assert_called_once_with(mock_file, limit=1000, preview_page=None)

    @patch("apps.automation.services.document.document_processing.process_uploaded_document")
    def test_process_uploaded_document_with_preview(self, mock_process):
        """测试处理上传文档并指定预览页"""
        # 创建 Mock 上传文件
        mock_file = Mock()
        mock_file.name = "test.pdf"
        mock_file.size = 2048

        # 配置 Mock 返回值
        mock_result = Mock()
        mock_result.text = None
        mock_result.image_url = "/media/preview.png"
        mock_process.return_value = mock_result

        # 执行测试
        result = self.service.process_uploaded_document(uploaded_file=mock_file, limit=500, preview_page=2)

        # 断言结果
        assert result["text"] is None
        assert result["image_url"] == "/media/preview.png"

        # 验证调用
        mock_process.assert_called_once_with(mock_file, limit=500, preview_page=2)

    @patch("apps.automation.services.document.document_processing.process_uploaded_document")
    def test_process_uploaded_document_failure(self, mock_process):
        """测试处理上传文档失败"""
        # 创建 Mock 上传文件
        mock_file = Mock()
        mock_file.name = "test.pdf"

        # 配置 Mock 抛出异常
        mock_process.side_effect = Exception("文档处理失败")

        # 断言抛出异常
        from apps.core.exceptions import ValidationException

        with pytest.raises(ValidationException) as exc_info:
            self.service.process_uploaded_document(uploaded_file=mock_file)

        assert "文档" in str(exc_info.value.message)
        assert "文档处理失败" in str(exc_info.value.message)

    @patch("apps.automation.services.document.document_processing.extract_document_content")
    def test_extract_document_content_by_path_success(self, mock_extract):
        """测试根据路径提取文档内容成功"""
        # 配置 Mock 返回值
        mock_result = Mock()
        mock_result.text = "文档内容"
        mock_result.image_url = None
        mock_extract.return_value = mock_result

        # 执行测试
        result = self.service.extract_document_content_by_path(file_path="/path/to/test.pdf", limit=1000)

        # 断言结果
        assert result["text"] == "文档内容"
        assert result["image_url"] is None
        assert result["file_path"] == "/path/to/test.pdf"

        # 验证调用
        mock_extract.assert_called_once_with("/path/to/test.pdf", limit=1000, preview_page=None)

    @patch("apps.automation.services.document.document_processing.extract_document_content")
    def test_extract_document_content_by_path_with_preview(self, mock_extract):
        """测试根据路径提取文档内容并指定预览页"""
        # 配置 Mock 返回值
        mock_result = Mock()
        mock_result.text = "第三页内容"
        mock_result.image_url = None
        mock_extract.return_value = mock_result

        # 执行测试
        result = self.service.extract_document_content_by_path(file_path="/path/to/test.pdf", limit=500, preview_page=3)

        # 断言结果
        assert result["text"] == "第三页内容"

        # 验证调用
        mock_extract.assert_called_once_with("/path/to/test.pdf", limit=500, preview_page=3)

    @patch("apps.automation.services.document.document_processing.extract_document_content")
    def test_extract_document_content_by_path_failure(self, mock_extract):
        """测试根据路径提取文档内容失败"""
        # 配置 Mock 抛出异常
        mock_extract.side_effect = Exception("文件不存在")

        # 断言抛出异常
        with pytest.raises(ValidationException) as exc_info:
            self.service.extract_document_content_by_path(file_path="/path/to/test.pdf")

        assert "文档内容提取失败" in str(exc_info.value.message)

    @patch("apps.automation.services.document.document_processing.process_pdf")
    def test_extract_text_from_pdf_internal(self, mock_process_pdf):
        """测试内部接口：从 PDF 提取文本"""
        # 配置 Mock
        mock_process_pdf.return_value = (None, "内部接口文本")

        # 执行测试
        result = self.service.extract_text_from_pdf_internal(file_path="/path/to/test.pdf", limit=1000)

        # 断言结果
        assert result["text"] == "内部接口文本"

        # 验证调用
        mock_process_pdf.assert_called_once_with("/path/to/test.pdf", 1000, None)

    @patch("apps.automation.services.document.document_processing.extract_docx_text")
    def test_extract_text_from_docx_internal(self, mock_extract_docx):
        """测试内部接口：从 DOCX 提取文本"""
        # 配置 Mock
        mock_extract_docx.return_value = "内部接口DOCX文本"

        # 执行测试
        result = self.service.extract_text_from_docx_internal(file_path="/path/to/test.docx", limit=500)

        # 断言结果
        assert result == "内部接口DOCX文本"

        # 验证调用
        mock_extract_docx.assert_called_once_with("/path/to/test.docx", limit=500)

    @patch("apps.automation.services.document.document_processing.extract_text_from_image_with_rapidocr")
    def test_extract_text_from_image_internal(self, mock_ocr):
        """测试内部接口：从图片提取文本"""
        # 配置 Mock
        mock_ocr.return_value = "内部接口OCR文本"

        # 执行测试
        result = self.service.extract_text_from_image_internal(file_path="/path/to/test.jpg", limit=300)

        # 断言结果
        assert result == "内部接口OCR文本"

        # 验证调用
        mock_ocr.assert_called_once_with("/path/to/test.jpg")

    @patch("apps.automation.services.document.document_processing.process_uploaded_document")
    def test_process_uploaded_document_internal(self, mock_process):
        """测试内部接口：处理上传文档"""
        # 创建 Mock 上传文件
        mock_file = Mock()
        mock_file.name = "internal.pdf"
        mock_file.size = 512

        # 配置 Mock 返回值
        mock_result = Mock()
        mock_result.text = "内部接口文档内容"
        mock_result.image_url = None
        mock_process.return_value = mock_result

        # 执行测试
        result = self.service.process_uploaded_document_internal(uploaded_file=mock_file, limit=800)

        # 断言结果
        assert result["text"] == "内部接口文档内容"
        assert result["file_name"] == "internal.pdf"

        # 验证调用
        mock_process.assert_called_once_with(mock_file, limit=800, preview_page=None)

    @patch("apps.automation.services.document.document_processing.extract_document_content")
    def test_extract_document_content_by_path_internal(self, mock_extract):
        """测试内部接口：根据路径提取文档内容"""
        # 配置 Mock 返回值
        mock_result = Mock()
        mock_result.text = "内部接口路径文档内容"
        mock_result.image_url = None
        mock_extract.return_value = mock_result

        # 执行测试
        result = self.service.extract_document_content_by_path_internal(file_path="/path/to/internal.pdf", limit=600)

        # 断言结果
        assert result["text"] == "内部接口路径文档内容"
        assert result["file_path"] == "/path/to/internal.pdf"

        # 验证调用
        mock_extract.assert_called_once_with("/path/to/internal.pdf", limit=600, preview_page=None)


class TestDocumentProcessingServiceEdgeCases:
    """文档处理服务边界情况测试"""

    def setup_method(self):
        """每个测试方法前执行"""
        self.service = DocumentProcessingServiceAdapter()

    @patch("apps.automation.services.document.document_processing.process_pdf")
    def test_extract_text_from_pdf_empty_result(self, mock_process_pdf):
        """测试从 PDF 提取文本返回空结果"""
        # 配置 Mock 返回空文本
        mock_process_pdf.return_value = (None, "")

        # 执行测试
        result = self.service.extract_text_from_pdf(file_path="/path/to/empty.pdf")

        # 断言结果
        assert result["text"] == ""
        assert result["image_url"] is None

    @patch("apps.automation.services.document.document_processing.process_pdf")
    def test_extract_text_from_pdf_with_image_url(self, mock_process_pdf):
        """测试从 PDF 提取文本返回预览图"""
        # 配置 Mock 返回预览图（无文本）
        mock_process_pdf.return_value = ("/media/preview.png", None)

        # 执行测试
        result = self.service.extract_text_from_pdf(file_path="/path/to/test.pdf")

        # 断言结果
        assert result["text"] is None
        assert result["image_url"] == "/media/preview.png"

    @patch("apps.automation.services.document.document_processing.extract_docx_text")
    def test_extract_text_from_docx_empty_result(self, mock_extract_docx):
        """测试从 DOCX 提取文本返回空结果"""
        # 配置 Mock 返回空文本
        mock_extract_docx.return_value = ""

        # 执行测试
        result = self.service.extract_text_from_docx(file_path="/path/to/empty.docx")

        # 断言结果
        assert result == ""

    @patch("apps.automation.services.document.document_processing.extract_text_from_image_with_rapidocr")
    def test_extract_text_from_image_no_limit(self, mock_ocr):
        """测试从图片提取文本不限制长度"""
        # 配置 Mock
        long_text = "这是一段很长的文本" * 1000
        mock_ocr.return_value = long_text

        # 执行测试
        result = self.service.extract_text_from_image(file_path="/path/to/test.jpg", limit=None)

        # 断言结果（无限制时返回完整文本）
        assert result == long_text

    @patch("apps.automation.services.document.document_processing.process_uploaded_document")
    def test_process_uploaded_document_no_name_attribute(self, mock_process):
        """测试处理上传文档时文件对象无 name 属性"""
        # 创建 Mock 上传文件（无 name 属性）
        mock_file = Mock(spec=[])

        # 配置 Mock 返回值
        mock_result = Mock()
        mock_result.text = "文档内容"
        mock_result.image_url = None
        mock_process.return_value = mock_result

        # 执行测试
        result = self.service.process_uploaded_document(uploaded_file=mock_file)

        # 断言结果
        assert result["text"] == "文档内容"
        assert result["file_name"] is None
        assert result["file_size"] is None

    @patch("apps.automation.services.document.document_processing.extract_document_content")
    def test_extract_document_content_by_path_with_special_chars(self, mock_extract):
        """测试提取包含特殊字符的文件路径"""
        # 配置 Mock 返回值
        mock_result = Mock()
        mock_result.text = "特殊字符文件内容"
        mock_result.image_url = None
        mock_extract.return_value = mock_result

        # 执行测试
        special_path = "/path/to/文件名 (1) [副本].pdf"
        result = self.service.extract_document_content_by_path(file_path=special_path)

        # 断言结果
        assert result["text"] == "特殊字符文件内容"
        assert result["file_path"] == special_path

    @patch("apps.automation.services.document.document_processing.process_pdf")
    def test_extract_text_from_pdf_zero_limit(self, mock_process_pdf):
        """测试从 PDF 提取文本限制为 0"""
        # 配置 Mock
        mock_process_pdf.return_value = (None, "")

        # 执行测试
        result = self.service.extract_text_from_pdf(file_path="/path/to/test.pdf", limit=0)

        # 断言结果
        assert result["text"] == ""

        # 验证调用
        mock_process_pdf.assert_called_once_with("/path/to/test.pdf", 0, None)

    @patch("apps.automation.services.document.document_processing.extract_text_from_image_with_rapidocr")
    def test_extract_text_from_image_exact_limit(self, mock_ocr):
        """测试从图片提取文本长度恰好等于限制"""
        # 配置 Mock
        mock_ocr.return_value = "12345"

        # 执行测试
        result = self.service.extract_text_from_image(file_path="/path/to/test.jpg", limit=5)

        # 断言结果
        assert result == "12345"
        assert len(result) == 5

    @patch("apps.automation.services.document.document_processing.extract_document_content")
    def test_extract_document_content_by_path_error_details(self, mock_extract):
        """测试提取文档内容失败时错误详情"""
        # 配置 Mock 抛出异常
        mock_extract.side_effect = ValueError("不支持的文件格式")

        # 断言抛出异常
        with pytest.raises(ValidationException) as exc_info:
            self.service.extract_document_content_by_path(file_path="/path/to/test.xyz")

        # 验证异常详情
        assert exc_info.value.code == "DOCUMENT_CONTENT_EXTRACTION_FAILED"
        assert "/path/to/test.xyz" in str(exc_info.value.errors)
