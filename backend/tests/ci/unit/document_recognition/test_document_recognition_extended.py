"""Extended tests for document_recognition services - document_classifier."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from apps.document_recognition.services.document_classifier import DocumentClassifier
from apps.document_recognition.services.data_classes import DocumentType


class TestDocumentClassifier:
    def setup_method(self):
        self.mock_llm = MagicMock()
        self.classifier = DocumentClassifier(
            ollama_model="test-model",
            ollama_base_url="http://localhost:11434",
            llm_service=self.mock_llm,
        )

    def test_classify_empty_text(self):
        doc_type, confidence = self.classifier.classify("")
        assert doc_type == DocumentType.OTHER
        assert confidence == 0.0

    def test_classify_none_text(self):
        doc_type, confidence = self.classifier.classify(None)  # type: ignore[arg-type]
        assert doc_type == DocumentType.OTHER
        assert confidence == 0.0

    def test_parse_classification_response_summons(self):
        response = {
            "message": {
                "content": '{"type": "summons", "confidence": 0.9, "reason": "包含开庭时间"}'
            }
        }
        doc_type, confidence = self.classifier._parse_classification_response(response)
        assert doc_type == DocumentType.SUMMONS
        assert confidence == 0.9

    def test_parse_classification_response_execution(self):
        response = {
            "message": {
                "content": '{"type": "execution", "confidence": 0.85, "reason": "执行裁定"}'
            }
        }
        doc_type, confidence = self.classifier._parse_classification_response(response)
        assert doc_type == DocumentType.EXECUTION_RULING
        assert confidence == 0.85

    def test_parse_classification_response_other(self):
        response = {
            "message": {
                "content": '{"type": "other", "confidence": 0.7, "reason": "无法确定"}'
            }
        }
        doc_type, confidence = self.classifier._parse_classification_response(response)
        assert doc_type == DocumentType.OTHER
        assert confidence == 0.7

    def test_parse_classification_response_no_message(self):
        response = {}
        doc_type, confidence = self.classifier._parse_classification_response(response)
        assert doc_type == DocumentType.OTHER
        assert confidence == 0.0

    def test_parse_classification_response_no_content(self):
        response = {"message": {}}
        doc_type, confidence = self.classifier._parse_classification_response(response)
        assert doc_type == DocumentType.OTHER

    def test_parse_classification_response_confidence_clamped(self):
        response = {
            "message": {
                "content": '{"type": "summons", "confidence": 1.5}'
            }
        }
        doc_type, confidence = self.classifier._parse_classification_response(response)
        assert confidence <= 1.0

    def test_extract_json_from_response_direct(self):
        result = self.classifier._extract_json_from_response('{"type": "summons"}')
        assert result == {"type": "summons"}

    def test_extract_json_from_response_markdown(self):
        result = self.classifier._extract_json_from_response('```json\n{"type": "summons"}\n```')
        assert result == {"type": "summons"}

    def test_extract_json_from_response_plain_markdown(self):
        result = self.classifier._extract_json_from_response('```\n{"type": "summons"}\n```')
        assert result == {"type": "summons"}

    def test_extract_json_from_response_with_text(self):
        result = self.classifier._extract_json_from_response(
            'Here is the result: {"type": "summons"} done'
        )
        assert result == {"type": "summons"}

    def test_extract_json_from_response_invalid(self):
        result = self.classifier._extract_json_from_response("not json at all")
        assert result is None

    def test_map_type_string_summons(self):
        assert self.classifier._map_type_string("summons") == DocumentType.SUMMONS

    def test_map_type_string_chinese_summons(self):
        assert self.classifier._map_type_string("传票") == DocumentType.SUMMONS

    def test_map_type_string_execution(self):
        assert self.classifier._map_type_string("execution") == DocumentType.EXECUTION_RULING

    def test_map_type_string_chinese_execution(self):
        assert self.classifier._map_type_string("执行裁定书") == DocumentType.EXECUTION_RULING

    def test_map_type_string_other(self):
        assert self.classifier._map_type_string("other") == DocumentType.OTHER

    def test_map_type_string_unknown(self):
        assert self.classifier._map_type_string("unknown_type") == DocumentType.OTHER


class TestDocumentClassifierFunctions:
    @patch("apps.document_recognition.services.document_classifier.LLMConfig")
    def test_get_ollama_model(self, mock_config):
        mock_config.get_ollama_model.return_value = "test-model"
        from apps.document_recognition.services.document_classifier import get_ollama_model

        result = get_ollama_model()
        assert result == "test-model"

    @patch("apps.document_recognition.services.document_classifier.LLMConfig")
    def test_get_ollama_base_url(self, mock_config):
        mock_config.get_ollama_base_url.return_value = "http://localhost:11434"
        from apps.document_recognition.services.document_classifier import get_ollama_base_url

        result = get_ollama_base_url()
        assert result == "http://localhost:11434"

    def test_chat_function(self):
        from apps.document_recognition.services.document_classifier import chat

        mock_service = MagicMock()
        mock_response = MagicMock()
        mock_response.content = "test response"
        mock_service.chat.return_value = mock_response
        result = chat(messages=[{"role": "user", "content": "test"}], llm_service=mock_service)
        assert "message" in result
        assert result["message"]["content"] == "test response"


class TestDocumentType:
    def test_summons(self):
        assert DocumentType.SUMMONS.value == "summons"

    def test_execution(self):
        assert DocumentType.EXECUTION_RULING.value == "execution"

    def test_other(self):
        assert DocumentType.OTHER.value == "other"
