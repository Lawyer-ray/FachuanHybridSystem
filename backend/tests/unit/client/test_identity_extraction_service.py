"""
证件信息提取服务单元测试
"""

from unittest.mock import MagicMock, Mock, patch

import pytest

from apps.client.models import ClientIdentityDoc
from apps.client.services.identity_extraction.data_classes import (
    ExtractionResult,
    OCRExtractionError,
    OllamaExtractionError,
)
from apps.client.services.identity_extraction.extraction_service import IdentityExtractionService
from apps.core.exceptions import ServiceUnavailableError, ValidationException


def _make_llm_response(content: str) -> Mock:
    """构造 LLM 响应 mock。"""
    resp = Mock()
    resp.content = content
    return resp


class TestIdentityExtractionService:
    """证件信息提取服务测试"""

    def setup_method(self) -> None:
        """测试前准备"""
        self.mock_recognizer = Mock()
        self.service = IdentityExtractionService(
            recognizer=self.mock_recognizer, ollama_model="test_model", ollama_base_url="http://test.com"
        )

    def test_extract_success(self) -> None:
        """测试成功提取证件信息"""
        image_bytes = b"fake_image_data"
        doc_type = ClientIdentityDoc.ID_CARD
        raw_text = "姓名：张三\n身份证号：123456789012345678\n地址：北京市朝阳区"

        self.mock_recognizer.classification.return_value = raw_text

        llm_content = '```json\n{"name": "张三", "id_number": "123456789012345678", "address": "北京市朝阳区"}\n```'
        mock_llm = Mock()
        mock_llm.chat.return_value = _make_llm_response(llm_content)

        with patch(
            "apps.client.services.identity_extraction.extraction_service.get_llm_service",
            return_value=mock_llm,
        ):
            result = self.service.extract(image_bytes, doc_type)

        assert isinstance(result, ExtractionResult)
        assert result.doc_type == doc_type
        assert result.raw_text == raw_text
        assert result.extracted_data["name"] == "张三"
        assert result.extracted_data["id_number"] == "123456789012345678"
        assert result.extracted_data["address"] == "北京市朝阳区"
        assert result.confidence == 0.8
        assert result.extraction_method == "ocr_ollama"

    def test_extract_empty_image_bytes(self) -> None:
        """测试空图片数据"""
        with pytest.raises(ValidationException, match="图片数据不能为空"):
            self.service.extract(b"", ClientIdentityDoc.ID_CARD)

    def test_extract_empty_doc_type(self) -> None:
        """测试空证件类型"""
        with pytest.raises(ValidationException, match="证件类型不能为空"):
            self.service.extract(b"fake_image", "")

    def test_ocr_extraction_error(self) -> None:
        """测试 OCR 提取失败"""
        self.mock_recognizer.classification.side_effect = Exception("OCR failed")

        with pytest.raises(OCRExtractionError, match="OCR 提取失败"):
            self.service.extract(b"fake_image", ClientIdentityDoc.ID_CARD)

    def test_ocr_empty_result(self) -> None:
        """测试 OCR 返回空结果"""
        self.mock_recognizer.classification.return_value = ""

        with pytest.raises(OCRExtractionError, match="OCR 未能提取到有效文字"):
            self.service.extract(b"fake_image", ClientIdentityDoc.ID_CARD)

    def test_ollama_extraction_error(self) -> None:
        """测试 Ollama 提取失败"""
        self.mock_recognizer.classification.return_value = "test text"

        mock_llm = Mock()
        mock_llm.chat.side_effect = Exception("Ollama failed")

        with (
            patch(
                "apps.client.services.identity_extraction.extraction_service.get_llm_service",
                return_value=mock_llm,
            ),
            pytest.raises(OllamaExtractionError, match="Ollama 提取失败"),
        ):
            self.service.extract(b"fake_image", ClientIdentityDoc.ID_CARD)

    def test_ollama_empty_response(self) -> None:
        """测试 Ollama 返回空响应"""
        self.mock_recognizer.classification.return_value = "test text"

        mock_llm = Mock()
        mock_llm.chat.return_value = _make_llm_response("")

        with (
            patch(
                "apps.client.services.identity_extraction.extraction_service.get_llm_service",
                return_value=mock_llm,
            ),
            pytest.raises(OllamaExtractionError, match="Ollama 返回内容为空"),
        ):
            self.service.extract(b"fake_image", ClientIdentityDoc.ID_CARD)

    def test_ollama_invalid_json(self) -> None:
        """测试 Ollama 返回无效 JSON"""
        self.mock_recognizer.classification.return_value = "test text"

        mock_llm = Mock()
        mock_llm.chat.return_value = _make_llm_response("invalid json content")

        with (
            patch(
                "apps.client.services.identity_extraction.extraction_service.get_llm_service",
                return_value=mock_llm,
            ),
            pytest.raises(OllamaExtractionError, match="Ollama 返回的 JSON 格式错误"),
        ):
            self.service.extract(b"fake_image", ClientIdentityDoc.ID_CARD)

    def test_ollama_connection_error(self) -> None:
        """测试 Ollama 连接错误"""
        self.mock_recognizer.classification.return_value = "test text"

        mock_llm = Mock()
        mock_llm.chat.side_effect = ConnectionError("Connection failed")

        with (
            patch(
                "apps.client.services.identity_extraction.extraction_service.get_llm_service",
                return_value=mock_llm,
            ),
            pytest.raises(ServiceUnavailableError),
        ):
            self.service.extract(b"fake_image", ClientIdentityDoc.ID_CARD)

    def test_extract_with_code_block_json(self) -> None:
        """测试提取包含代码块的 JSON 响应"""
        self.mock_recognizer.classification.return_value = "test text"

        llm_content = (
            '这是提取的信息：\n```json\n{"name": "李四", "id_number": "987654321098765432"}\n```\n以上是结果。'  # noqa: E501
        )
        mock_llm = Mock()
        mock_llm.chat.return_value = _make_llm_response(llm_content)

        with patch(
            "apps.client.services.identity_extraction.extraction_service.get_llm_service",
            return_value=mock_llm,
        ):
            result = self.service.extract(b"fake_image", ClientIdentityDoc.ID_CARD)

        assert result.extracted_data["name"] == "李四"
        assert result.extracted_data["id_number"] == "987654321098765432"

    def test_extract_with_generic_code_block(self) -> None:
        """测试提取通用代码块的 JSON 响应"""
        self.mock_recognizer.classification.return_value = "test text"

        llm_content = '提取结果：\n```\n{"name": "王五", "address": "上海市浦东新区"}\n```'
        mock_llm = Mock()
        mock_llm.chat.return_value = _make_llm_response(llm_content)

        with patch(
            "apps.client.services.identity_extraction.extraction_service.get_llm_service",
            return_value=mock_llm,
        ):
            result = self.service.extract(b"fake_image", ClientIdentityDoc.ID_CARD)

        assert result.extracted_data["name"] == "王五"
        assert result.extracted_data["address"] == "上海市浦东新区"
