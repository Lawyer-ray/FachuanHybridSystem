"""
文书分类器单元测试

测试 DocumentClassifier 的基本功能。
"""

from unittest.mock import MagicMock, patch

import pytest

from apps.automation.services.court_document_recognition import DocumentClassifier, DocumentType


class TestDocumentClassifier:
    """DocumentClassifier 单元测试"""

    def test_init_with_defaults(self):
        """测试使用默认配置初始化"""
        with patch(
            "apps.automation.services.court_document_recognition.document_classifier.get_ollama_model"
        ) as mock_model, patch(
            "apps.automation.services.court_document_recognition.document_classifier.get_ollama_base_url"
        ) as mock_url:
            mock_model.return_value = "test-model"
            mock_url.return_value = "http://localhost:11434"

            classifier = DocumentClassifier()

            assert classifier.ollama_model == "test-model"
            assert classifier.ollama_base_url == "http://localhost:11434"

    def test_init_with_custom_config(self):
        """测试使用自定义配置初始化"""
        classifier = DocumentClassifier(
            ollama_model="custom-model",
            ollama_base_url="http://custom:11434",
        )

        assert classifier.ollama_model == "custom-model"
        assert classifier.ollama_base_url == "http://custom:11434"

    def test_classify_empty_text(self):
        """测试空文本返回 OTHER 类型"""
        classifier = DocumentClassifier(
            ollama_model="test-model",
            ollama_base_url="http://localhost:11434",
        )

        doc_type, confidence = classifier.classify("")

        assert doc_type == DocumentType.OTHER
        assert confidence == 0.0

    def test_classify_whitespace_text(self):
        """测试纯空白文本返回 OTHER 类型"""
        classifier = DocumentClassifier(
            ollama_model="test-model",
            ollama_base_url="http://localhost:11434",
        )

        doc_type, confidence = classifier.classify("   \n\t  ")

        assert doc_type == DocumentType.OTHER
        assert confidence == 0.0

    @patch("apps.automation.services.court_document_recognition.document_classifier.chat")
    def test_classify_summons(self, mock_chat):
        """测试识别传票"""
        mock_chat.return_value = {
            "message": {"content": '{"type": "summons", "confidence": 0.95, "reason": "包含开庭时间"}'}
        }

        classifier = DocumentClassifier(
            ollama_model="test-model",
            ollama_base_url="http://localhost:11434",
        )

        doc_type, confidence = classifier.classify("传票内容：开庭时间 2024-03-15 09:30")

        assert doc_type == DocumentType.SUMMONS
        assert confidence == 0.95
        mock_chat.assert_called_once()

    @patch("apps.automation.services.court_document_recognition.document_classifier.chat")
    def test_classify_execution_ruling(self, mock_chat):
        """测试识别执行裁定书"""
        mock_chat.return_value = {
            "message": {"content": '{"type": "execution", "confidence": 0.88, "reason": "包含财产保全"}'}
        }

        classifier = DocumentClassifier(
            ollama_model="test-model",
            ollama_base_url="http://localhost:11434",
        )

        doc_type, confidence = classifier.classify("执行裁定书：财产保全到期时间 2024-06-01")

        assert doc_type == DocumentType.EXECUTION_RULING
        assert confidence == 0.88

    @patch("apps.automation.services.court_document_recognition.document_classifier.chat")
    def test_classify_other(self, mock_chat):
        """测试识别其他类型"""
        mock_chat.return_value = {
            "message": {"content": '{"type": "other", "confidence": 0.6, "reason": "无法确定类型"}'}
        }

        classifier = DocumentClassifier(
            ollama_model="test-model",
            ollama_base_url="http://localhost:11434",
        )

        doc_type, confidence = classifier.classify("一些普通文书内容")

        assert doc_type == DocumentType.OTHER
        assert confidence == 0.6

    @patch("apps.automation.services.court_document_recognition.document_classifier.chat")
    def test_classify_with_markdown_json(self, mock_chat):
        """测试处理 markdown 格式的 JSON 响应"""
        mock_chat.return_value = {"message": {"content": '```json\n{"type": "summons", "confidence": 0.9}\n```'}}

        classifier = DocumentClassifier(
            ollama_model="test-model",
            ollama_base_url="http://localhost:11434",
        )

        doc_type, confidence = classifier.classify("传票内容")

        assert doc_type == DocumentType.SUMMONS
        assert confidence == 0.9

    @patch("apps.automation.services.court_document_recognition.document_classifier.chat")
    def test_classify_with_extra_text(self, mock_chat):
        """测试处理包含额外文本的响应"""
        mock_chat.return_value = {
            "message": {
                "content": '根据分析，这是一份传票。\n{"type": "summons", "confidence": 0.85}\n以上是分析结果。'
            }
        }

        classifier = DocumentClassifier(
            ollama_model="test-model",
            ollama_base_url="http://localhost:11434",
        )

        doc_type, confidence = classifier.classify("传票内容")

        assert doc_type == DocumentType.SUMMONS
        assert confidence == 0.85

    @patch("apps.automation.services.court_document_recognition.document_classifier.chat")
    def test_classify_invalid_json_response(self, mock_chat):
        """测试处理无效 JSON 响应"""
        mock_chat.return_value = {"message": {"content": "这不是有效的 JSON 响应"}}

        classifier = DocumentClassifier(
            ollama_model="test-model",
            ollama_base_url="http://localhost:11434",
        )

        doc_type, confidence = classifier.classify("一些文书内容")

        assert doc_type == DocumentType.OTHER
        assert confidence == 0.0

    @patch("apps.automation.services.court_document_recognition.document_classifier.chat")
    def test_classify_missing_message_key(self, mock_chat):
        """测试处理缺少 message 键的响应"""
        mock_chat.return_value = {"other_key": "value"}

        classifier = DocumentClassifier(
            ollama_model="test-model",
            ollama_base_url="http://localhost:11434",
        )

        doc_type, confidence = classifier.classify("一些文书内容")

        assert doc_type == DocumentType.OTHER
        assert confidence == 0.0

    @patch("apps.automation.services.court_document_recognition.document_classifier.chat")
    def test_classify_connection_error(self, mock_chat):
        """测试 Ollama 连接错误"""
        from apps.core.exceptions import ServiceUnavailableError

        mock_chat.side_effect = ConnectionError("无法连接到 Ollama 服务")

        classifier = DocumentClassifier(
            ollama_model="test-model",
            ollama_base_url="http://localhost:11434",
        )

        with pytest.raises(ServiceUnavailableError) as exc_info:
            classifier.classify("一些文书内容")

        assert exc_info.value.code == "OLLAMA_SERVICE_UNAVAILABLE"
        assert "AI 服务暂时不可用" in exc_info.value.message

    @patch("apps.automation.services.court_document_recognition.document_classifier.chat")
    def test_classify_confidence_clamping(self, mock_chat):
        """测试置信度限制在 0-1 范围"""
        # 测试超过 1 的置信度
        mock_chat.return_value = {"message": {"content": '{"type": "summons", "confidence": 1.5}'}}

        classifier = DocumentClassifier(
            ollama_model="test-model",
            ollama_base_url="http://localhost:11434",
        )

        doc_type, confidence = classifier.classify("传票内容")

        assert confidence == 1.0

        # 测试负数置信度
        mock_chat.return_value = {"message": {"content": '{"type": "summons", "confidence": -0.5}'}}

        doc_type, confidence = classifier.classify("传票内容")

        assert confidence == 0.0

    def test_map_type_string_chinese(self):
        """测试中文类型字符串映射"""
        classifier = DocumentClassifier(
            ollama_model="test-model",
            ollama_base_url="http://localhost:11434",
        )

        assert classifier._map_type_string("传票") == DocumentType.SUMMONS
        assert classifier._map_type_string("执行裁定书") == DocumentType.EXECUTION_RULING
        assert classifier._map_type_string("其他") == DocumentType.OTHER

    def test_map_type_string_english(self):
        """测试英文类型字符串映射"""
        classifier = DocumentClassifier(
            ollama_model="test-model",
            ollama_base_url="http://localhost:11434",
        )

        assert classifier._map_type_string("summons") == DocumentType.SUMMONS
        assert classifier._map_type_string("SUMMONS") == DocumentType.SUMMONS
        assert classifier._map_type_string("execution") == DocumentType.EXECUTION_RULING
        assert classifier._map_type_string("execution_ruling") == DocumentType.EXECUTION_RULING
        assert classifier._map_type_string("other") == DocumentType.OTHER

    def test_map_type_string_unknown(self):
        """测试未知类型字符串映射"""
        classifier = DocumentClassifier(
            ollama_model="test-model",
            ollama_base_url="http://localhost:11434",
        )

        assert classifier._map_type_string("unknown") == DocumentType.OTHER
        assert classifier._map_type_string("") == DocumentType.OTHER
        assert classifier._map_type_string("random") == DocumentType.OTHER

    @patch("apps.automation.services.court_document_recognition.document_classifier.chat")
    def test_classify_long_text_truncation(self, mock_chat):
        """测试长文本截断"""
        mock_chat.return_value = {"message": {"content": '{"type": "summons", "confidence": 0.9}'}}

        classifier = DocumentClassifier(
            ollama_model="test-model",
            ollama_base_url="http://localhost:11434",
        )

        # 创建超过 3000 字符的文本
        long_text = "传票内容" * 1000

        doc_type, confidence = classifier.classify(long_text)

        assert doc_type == DocumentType.SUMMONS
        # 验证调用时文本被截断
        call_args = mock_chat.call_args
        messages = call_args[1]["messages"]
        # 提示词中的文本应该被截断
        assert len(messages[0]["content"]) < len(long_text) + 1000  # 加上提示词模板长度
