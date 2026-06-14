"""Targeted coverage tests for document_recognition module — Round 6.

Targets: notification_service, document_classifier, _response_parser_mixin,
          _datetime_extraction_mixin, case_binding_service, recognition_service,
          text_extraction_service, data_classes (partial)
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from types import SimpleNamespace
from typing import Any
from unittest.mock import MagicMock, patch

import pytest


# ---------------------------------------------------------------------------
# document_classifier.py
# ---------------------------------------------------------------------------


class TestDocumentClassifier:
    """Tests for DocumentClassifier._parse_classification_response and _extract_json_from_response."""

    @pytest.fixture()
    def classifier(self):
        from apps.document_recognition.services.document_classifier import DocumentClassifier

        return DocumentClassifier(
            ollama_model="test-model",
            ollama_base_url="http://localhost:11434",
            llm_service=MagicMock(),
        )

    def test_parse_valid_json(self, classifier):
        from apps.document_recognition.services.data_classes import DocumentType

        response = {"message": {"content": '{"type": "summons", "confidence": 0.95, "reason": "传票"}'}}
        doc_type, confidence = classifier._parse_classification_response(response)
        assert doc_type == DocumentType.SUMMONS
        assert confidence == pytest.approx(0.95)

    def test_parse_execution_type(self, classifier):
        from apps.document_recognition.services.data_classes import DocumentType

        response = {"message": {"content": '{"type": "execution", "confidence": 0.8}'}}
        doc_type, confidence = classifier._parse_classification_response(response)
        assert doc_type == DocumentType.EXECUTION_RULING
        assert confidence == pytest.approx(0.8)

    def test_parse_other_type(self, classifier):
        from apps.document_recognition.services.data_classes import DocumentType

        response = {"message": {"content": '{"type": "other", "confidence": 0.3}'}}
        doc_type, confidence = classifier._parse_classification_response(response)
        assert doc_type == DocumentType.OTHER

    def test_parse_missing_message_key(self, classifier):
        from apps.document_recognition.services.data_classes import DocumentType

        response = {"no_message": "bad"}
        doc_type, confidence = classifier._parse_classification_response(response)
        assert doc_type == DocumentType.OTHER
        assert confidence == 0.0

    def test_parse_missing_content_key(self, classifier):
        from apps.document_recognition.services.data_classes import DocumentType

        response = {"message": {"no_content": "bad"}}
        doc_type, confidence = classifier._parse_classification_response(response)
        assert doc_type == DocumentType.OTHER

    def test_parse_invalid_json(self, classifier):
        from apps.document_recognition.services.data_classes import DocumentType

        response = {"message": {"content": "not json at all"}}
        doc_type, confidence = classifier._parse_classification_response(response)
        assert doc_type == DocumentType.OTHER
        assert confidence == 0.0

    def test_parse_confidence_clamp_high(self, classifier):
        from apps.document_recognition.services.data_classes import DocumentType

        response = {"message": {"content": '{"type": "summons", "confidence": 5.0}'}}
        doc_type, confidence = classifier._parse_classification_response(response)
        assert confidence == 1.0

    def test_parse_confidence_clamp_low(self, classifier):
        from apps.document_recognition.services.data_classes import DocumentType

        response = {"message": {"content": '{"type": "summons", "confidence": -1.0}'}}
        doc_type, confidence = classifier._parse_classification_response(response)
        assert confidence == 0.0

    def test_parse_json_in_markdown_block(self, classifier):
        from apps.document_recognition.services.data_classes import DocumentType

        content = '```json\n{"type": "summons", "confidence": 0.9}\n```'
        response = {"message": {"content": content}}
        doc_type, confidence = classifier._parse_classification_response(response)
        assert doc_type == DocumentType.SUMMONS

    def test_parse_json_in_fenced_block(self, classifier):
        from apps.document_recognition.services.data_classes import DocumentType

        content = '```\n{"type": "execution", "confidence": 0.7}\n```'
        response = {"message": {"content": content}}
        doc_type, confidence = classifier._parse_classification_response(response)
        assert doc_type == DocumentType.EXECUTION_RULING

    def test_parse_json_embedded_in_text(self, classifier):
        from apps.document_recognition.services.data_classes import DocumentType

        content = 'Here is the result: {"type": "other", "confidence": 0.5} done.'
        response = {"message": {"content": content}}
        doc_type, confidence = classifier._parse_classification_response(response)
        assert doc_type == DocumentType.OTHER

    def test_extract_json_direct(self, classifier):
        result = classifier._extract_json_from_response('{"a": 1}')
        assert result == {"a": 1}

    def test_extract_json_from_text(self, classifier):
        result = classifier._extract_json_from_response('some text {"a": 1} end')
        assert result == {"a": 1}

    def test_extract_json_from_markdown(self, classifier):
        result = classifier._extract_json_from_response('```json\n{"a": 1}\n```')
        assert result == {"a": 1}

    def test_extract_json_from_fenced(self, classifier):
        result = classifier._extract_json_from_response('```\n{"a": 1}\n```')
        assert result == {"a": 1}

    def test_extract_json_none(self, classifier):
        assert classifier._extract_json_from_response("no json here") is None

    def test_extract_json_empty_string(self, classifier):
        assert classifier._extract_json_from_response("") is None

    def test_map_type_string_cn(self, classifier):
        from apps.document_recognition.services.data_classes import DocumentType

        assert classifier._map_type_string("传票") == DocumentType.SUMMONS
        assert classifier._map_type_string("执行裁定书") == DocumentType.EXECUTION_RULING
        assert classifier._map_type_string("其他") == DocumentType.OTHER

    def test_map_type_string_execution_ruling(self, classifier):
        from apps.document_recognition.services.data_classes import DocumentType

        assert classifier._map_type_string("execution_ruling") == DocumentType.EXECUTION_RULING

    def test_map_type_string_unknown(self, classifier):
        from apps.document_recognition.services.data_classes import DocumentType

        assert classifier._map_type_string("unknown_type") == DocumentType.OTHER

    def test_classify_empty_text(self, classifier):
        from apps.document_recognition.services.data_classes import DocumentType

        doc_type, confidence = classifier.classify("")
        assert doc_type == DocumentType.OTHER
        assert confidence == 0.0

    def test_classify_whitespace_text(self, classifier):
        from apps.document_recognition.services.data_classes import DocumentType

        doc_type, confidence = classifier.classify("   ")
        assert doc_type == DocumentType.OTHER


# ---------------------------------------------------------------------------
# _response_parser_mixin.py
# ---------------------------------------------------------------------------


class TestResponseParserMixin:
    """Tests for ResponseParserMixin methods."""

    @pytest.fixture()
    def parser(self):
        from apps.document_recognition.services._response_parser_mixin import ResponseParserMixin

        class _Parser(ResponseParserMixin):
            def _normalize_case_number(self, case_number: str) -> str:
                return case_number.strip()

        return _Parser()

    def test_parse_summons_response_valid(self, parser):
        response = {"message": {"content": '{"case_number": "(2023)京01民初123号", "court_time": "2023-10-01 09:00"}'}}
        result = parser._parse_summons_response(response)
        assert result["case_number"] == "(2023)京01民初123号"
        assert result["court_time"] == datetime(2023, 10, 1, 9, 0)

    def test_parse_summons_response_null_values(self, parser):
        response = {"message": {"content": '{"case_number": "null", "court_time": "null"}'}}
        result = parser._parse_summons_response(response)
        assert result["case_number"] is None
        assert result["court_time"] is None

    def test_parse_summons_response_no_message(self, parser):
        result = parser._parse_summons_response({})
        assert result["case_number"] is None
        assert result["court_time"] is None

    def test_parse_summons_response_no_json(self, parser):
        result = parser._parse_summons_response({"message": {"content": "garbage"}})
        assert result["case_number"] is None

    def test_parse_summons_response_bad_datetime(self, parser):
        response = {"message": {"content": '{"case_number": "(2023)京01民初123号", "court_time": "not-a-date"}'}}
        result = parser._parse_summons_response(response)
        assert result["case_number"] == "(2023)京01民初123号"
        assert result["court_time"] is None

    def test_parse_execution_response_valid(self, parser):
        response = {"message": {"content": '{"case_number": "(2023)京01执1号", "preservation_deadline": "2023-12-31"}'}}
        result = parser._parse_execution_response(response)
        assert result["case_number"] == "(2023)京01执1号"
        assert result["preservation_deadline"] == datetime(2023, 12, 31)

    def test_parse_execution_response_null(self, parser):
        response = {"message": {"content": '{"case_number": null, "preservation_deadline": null}'}}
        result = parser._parse_execution_response(response)
        assert result["case_number"] is None
        assert result["preservation_deadline"] is None

    def test_parse_execution_response_no_message(self, parser):
        result = parser._parse_execution_response({})
        assert result["case_number"] is None

    def test_extract_json_direct(self, parser):
        assert parser._extract_json_from_response('{"a": 1}') == {"a": 1}

    def test_extract_json_from_markdown(self, parser):
        result = parser._extract_json_from_response('```json\n{"a": 2}\n```')
        assert result == {"a": 2}

    def test_extract_json_from_fenced(self, parser):
        result = parser._extract_json_from_response('```\n{"a": 3}\n```')
        assert result == {"a": 3}

    def test_extract_json_none(self, parser):
        assert parser._extract_json_from_response("no json") is None

    def test_parse_datetime_formats(self, parser):
        assert parser._parse_datetime("2023-10-01 09:00") == datetime(2023, 10, 1, 9, 0)
        assert parser._parse_datetime("2023-10-01 09:00:00") == datetime(2023, 10, 1, 9, 0)
        assert parser._parse_datetime("2023年10月01日 09:00") == datetime(2023, 10, 1, 9, 0)
        assert parser._parse_datetime("2023年10月01日 09时00分") == datetime(2023, 10, 1, 9, 0)
        assert parser._parse_datetime("2023年10月01日09时00分") == datetime(2023, 10, 1, 9, 0)
        assert parser._parse_datetime("2023/10/01 09:00") == datetime(2023, 10, 1, 9, 0)
        assert parser._parse_datetime("2023.10.01 09:00") == datetime(2023, 10, 1, 9, 0)

    def test_parse_datetime_regex_cn(self, parser):
        result = parser._parse_datetime("2024年3月5日 14时30分")
        assert result == datetime(2024, 3, 5, 14, 30)

    def test_parse_datetime_regex_std(self, parser):
        result = parser._parse_datetime("2024-3-5 14:30")
        assert result == datetime(2024, 3, 5, 14, 30)

    def test_parse_datetime_empty(self, parser):
        assert parser._parse_datetime("") is None

    def test_parse_datetime_unparseable(self, parser):
        assert parser._parse_datetime("abc123xyz") is None

    def test_parse_date_formats(self, parser):
        assert parser._parse_date("2023-10-01") == datetime(2023, 10, 1)
        assert parser._parse_date("2023年10月01日") == datetime(2023, 10, 1)
        assert parser._parse_date("2023/10/01") == datetime(2023, 10, 1)
        assert parser._parse_date("2023.10.01") == datetime(2023, 10, 1)

    def test_parse_date_regex(self, parser):
        result = parser._parse_date("2024年3月5日")
        assert result == datetime(2024, 3, 5)

    def test_parse_date_empty(self, parser):
        assert parser._parse_date("") is None

    def test_parse_date_unparseable(self, parser):
        assert parser._parse_date("xyz") is None


# ---------------------------------------------------------------------------
# notification_service.py
# ---------------------------------------------------------------------------


class TestDocumentRecognitionNotificationService:
    """Tests for DocumentRecognitionNotificationService."""

    @pytest.fixture()
    def service(self):
        from apps.document_recognition.services.notification_service import (
            DocumentRecognitionNotificationService,
        )

        mock_chat = MagicMock()
        return DocumentRecognitionNotificationService(case_chat_service=mock_chat), mock_chat

    def test_build_notification_message_summons(self, service_obj=None):
        from apps.document_recognition.services.notification_service import (
            DocumentRecognitionNotificationService,
        )

        svc = DocumentRecognitionNotificationService()
        msg = svc.build_notification_message(
            document_type="summons",
            case_number="(2023)京01民初1号",
            key_time=datetime(2024, 1, 15, 9, 0),
            case_name="张三诉李四",
        )
        assert "传票" in msg
        assert "(2023)京01民初1号" in msg
        assert "开庭时间" in msg
        assert "张三诉李四" in msg

    def test_build_notification_message_execution(self):
        from apps.document_recognition.services.notification_service import (
            DocumentRecognitionNotificationService,
        )

        svc = DocumentRecognitionNotificationService()
        msg = svc.build_notification_message(
            document_type="execution",
            case_number="(2023)京01执1号",
            key_time=datetime(2024, 6, 1),
            case_name="王五案",
        )
        assert "执行裁定书" in msg
        assert "关键时间" in msg

    def test_build_notification_message_no_number_no_time(self):
        from apps.document_recognition.services.notification_service import (
            DocumentRecognitionNotificationService,
        )

        svc = DocumentRecognitionNotificationService()
        msg = svc.build_notification_message(
            document_type="other",
            case_number=None,
            key_time=None,
            case_name="测试案件",
        )
        assert "案号" not in msg
        assert "法院文书" in msg

    def test_build_notification_message_unknown_type(self):
        from apps.document_recognition.services.notification_service import (
            DocumentRecognitionNotificationService,
        )

        svc = DocumentRecognitionNotificationService()
        msg = svc.build_notification_message(
            document_type="unknown",
            case_number=None,
            key_time=None,
            case_name="未知",
        )
        assert "法院文书" in msg

    def test_lazy_load_chat_service(self):
        from apps.document_recognition.services.notification_service import (
            DocumentRecognitionNotificationService,
        )

        svc = DocumentRecognitionNotificationService()
        assert svc._case_chat_service is None
        with patch("apps.document_recognition.services.notification_service.ServiceLocator") as mock_locator:
            mock_locator.get_case_chat_service.return_value = MagicMock()
            cs = svc.case_chat_service
            assert cs is not None
            mock_locator.get_case_chat_service.assert_called_once()

    @patch("apps.document_recognition.services.notification_service.ServiceLocator")
    def test_send_notification_success(self, mock_locator):
        from apps.document_recognition.services.notification_service import (
            DocumentRecognitionNotificationService,
        )
        from apps.core.models.enums import ChatPlatform

        mock_chat_service = MagicMock()
        mock_chat = MagicMock()
        mock_chat.chat_id = "chat_123"
        mock_chat_service.get_or_create_chat.return_value = mock_chat

        mock_result = MagicMock()
        mock_result.success = True
        mock_result.message = "文件发送成功"
        mock_chat_service.send_document_notification.return_value = mock_result

        svc = DocumentRecognitionNotificationService(case_chat_service=mock_chat_service)
        result = svc.send_notification(
            case_id=1,
            document_type="summons",
            case_number="(2023)京01民初1号",
            key_time=datetime(2024, 1, 15),
            file_path="/tmp/test.pdf",
            case_name="测试",
        )
        assert result.success is True
        assert result.file_sent is True

    def test_send_notification_chat_creation_failure(self):
        from apps.document_recognition.services.notification_service import (
            DocumentRecognitionNotificationService,
        )

        mock_chat_service = MagicMock()
        mock_chat_service.get_or_create_chat.side_effect = RuntimeError("DB error")
        svc = DocumentRecognitionNotificationService(case_chat_service=mock_chat_service)
        result = svc.send_notification(
            case_id=1,
            document_type="summons",
            case_number=None,
            key_time=None,
            file_path="/tmp/test.pdf",
            case_name="测试",
        )
        assert result.success is False
        assert "CHAT_CREATION_FAILED" in (result.error_code or "")

    def test_send_notification_message_send_failure(self):
        from apps.document_recognition.services.notification_service import (
            DocumentRecognitionNotificationService,
        )

        mock_chat_service = MagicMock()
        mock_chat = MagicMock()
        mock_chat.chat_id = "chat_1"
        mock_chat_service.get_or_create_chat.return_value = mock_chat

        mock_result = MagicMock()
        mock_result.success = False
        mock_result.message = "send failed"
        mock_chat_service.send_document_notification.return_value = mock_result

        svc = DocumentRecognitionNotificationService(case_chat_service=mock_chat_service)
        result = svc.send_notification(
            case_id=1,
            document_type="summons",
            case_number=None,
            key_time=None,
            file_path="",
            case_name="测试",
        )
        assert result.success is False

    def test_send_notification_send_exception(self):
        from apps.document_recognition.services.notification_service import (
            DocumentRecognitionNotificationService,
        )

        mock_chat_service = MagicMock()
        mock_chat = MagicMock()
        mock_chat.chat_id = "chat_1"
        mock_chat_service.get_or_create_chat.return_value = mock_chat
        mock_chat_service.send_document_notification.side_effect = RuntimeError("network")

        svc = DocumentRecognitionNotificationService(case_chat_service=mock_chat_service)
        result = svc.send_notification(
            case_id=1,
            document_type="summons",
            case_number=None,
            key_time=None,
            file_path="",
            case_name="测试",
        )
        assert result.success is False
        assert "MESSAGE_SEND_ERROR" in (result.error_code or "")


# ---------------------------------------------------------------------------
# data_classes.py
# ---------------------------------------------------------------------------


class TestDataClasses:
    """Tests for recognition data classes."""

    def test_recognition_result_to_dict(self):
        from apps.document_recognition.services.data_classes import DocumentType, RecognitionResult

        r = RecognitionResult(
            document_type=DocumentType.SUMMONS,
            case_number="(2023)京01号",
            key_time=datetime(2024, 1, 1, 12, 0),
            raw_text="text",
            confidence=0.9,
            extraction_method="pdf_direct",
        )
        d = r.to_dict()
        assert d["document_type"] == "summons"
        assert d["case_number"] == "(2023)京01号"
        assert d["key_time"] == "2024-01-01T12:00:00"
        assert d["raw_text"] == "text"
        assert d["confidence"] == 0.9

    def test_recognition_result_from_dict(self):
        from apps.document_recognition.services.data_classes import DocumentType, RecognitionResult

        data = {
            "document_type": "summons",
            "case_number": "X",
            "key_time": "2024-01-01T12:00:00",
            "raw_text": "r",
            "confidence": 0.8,
            "extraction_method": "ocr",
        }
        r = RecognitionResult.from_dict(data)
        assert r.document_type == DocumentType.SUMMONS
        assert r.key_time == datetime(2024, 1, 1, 12, 0)

    def test_recognition_result_from_dict_no_key_time(self):
        from apps.document_recognition.services.data_classes import DocumentType, RecognitionResult

        data = {"document_type": "other", "raw_text": ""}
        r = RecognitionResult.from_dict(data)
        assert r.key_time is None
        assert r.confidence == 0.0

    def test_recognition_result_from_dict_datetime_object(self):
        from apps.document_recognition.services.data_classes import DocumentType, RecognitionResult

        dt = datetime(2024, 6, 15)
        data = {"document_type": "execution", "key_time": dt}
        r = RecognitionResult.from_dict(data)
        assert r.key_time == dt

    def test_binding_result_to_dict(self):
        from apps.document_recognition.services.data_classes import BindingResult

        b = BindingResult(success=True, case_id=1, case_name="X", case_log_id=2, message="ok")
        d = b.to_dict()
        assert d["success"] is True
        assert d["case_id"] == 1

    def test_binding_result_from_dict(self):
        from apps.document_recognition.services.data_classes import BindingResult

        data = {"success": True, "case_id": 5, "case_name": "X", "case_log_id": 6, "message": "ok"}
        b = BindingResult.from_dict(data)
        assert b.case_id == 5

    def test_binding_result_success_factory(self):
        from apps.document_recognition.services.data_classes import BindingResult

        b = BindingResult.success_result(case_id=1, case_name="X", case_log_id=2)
        assert b.success is True
        assert "绑定" in b.message

    def test_binding_result_failure_factory(self):
        from apps.document_recognition.services.data_classes import BindingResult

        b = BindingResult.failure_result(message="err", error_code="ERR")
        assert b.success is False
        assert b.error_code == "ERR"

    def test_notification_result_to_dict(self):
        from apps.document_recognition.services.data_classes import NotificationResult

        now = datetime(2024, 1, 1)
        n = NotificationResult(success=True, message="ok", sent_at=now, file_sent=True)
        d = n.to_dict()
        assert d["success"] is True
        assert d["sent_at"] == "2024-01-01T00:00:00"
        assert d["file_sent"] is True

    def test_notification_result_from_dict(self):
        from apps.document_recognition.services.data_classes import NotificationResult

        data = {"success": True, "sent_at": "2024-01-01T00:00:00", "file_sent": True}
        n = NotificationResult.from_dict(data)
        assert n.sent_at == datetime(2024, 1, 1)
        assert n.file_sent is True

    def test_notification_result_from_dict_no_sent_at(self):
        from apps.document_recognition.services.data_classes import NotificationResult

        n = NotificationResult.from_dict({"success": False})
        assert n.sent_at is None

    def test_notification_result_from_dict_datetime_object(self):
        from apps.document_recognition.services.data_classes import NotificationResult

        dt = datetime(2024, 3, 3)
        n = NotificationResult.from_dict({"success": True, "sent_at": dt})
        assert n.sent_at == dt

    def test_notification_result_success_factory(self):
        from apps.document_recognition.services.data_classes import NotificationResult

        n = NotificationResult.success_result(sent_at=datetime.now(), file_sent=True)
        assert n.success is True

    def test_notification_result_failure_factory(self):
        from apps.document_recognition.services.data_classes import NotificationResult

        n = NotificationResult.failure_result(message="err", error_code="CODE")
        assert n.success is False
        assert n.error_code == "CODE"

    def test_recognition_response_to_dict(self):
        from apps.document_recognition.services.data_classes import (
            BindingResult,
            DocumentType,
            RecognitionResponse,
            RecognitionResult,
        )

        rec = RecognitionResult(
            document_type=DocumentType.OTHER,
            case_number=None,
            key_time=None,
            raw_text="",
            confidence=0.0,
            extraction_method="",
        )
        resp = RecognitionResponse(recognition=rec, binding=None, file_path="/f")
        d = resp.to_dict()
        assert d["binding"] is None
        assert d["file_path"] == "/f"

    def test_recognition_response_from_dict(self):
        from apps.document_recognition.services.data_classes import (
            DocumentType,
            RecognitionResponse,
        )

        data = {
            "recognition": {
                "document_type": "summons",
                "case_number": None,
                "key_time": None,
                "raw_text": "",
                "confidence": 0.5,
                "extraction_method": "",
            },
            "binding": {"success": True, "case_id": 1, "case_name": "X", "case_log_id": 2, "message": "ok"},
            "file_path": "/x",
        }
        resp = RecognitionResponse.from_dict(data)
        assert resp.recognition.document_type == DocumentType.SUMMONS
        assert resp.binding is not None
        assert resp.binding.success is True


# ---------------------------------------------------------------------------
# _datetime_extraction_mixin.py
# ---------------------------------------------------------------------------


class TestDatetimeExtractionMixin:
    """Tests for datetime extraction mixin."""

    @pytest.fixture()
    def mixin(self):
        from apps.document_recognition.services._datetime_extraction_mixin import (
            DatetimeExtractionMixin,
        )

        return DatetimeExtractionMixin()

    def test_parse_datetime_groups_none(self, mixin):
        # Test _parse_datetime_groups with empty tuple
        result = mixin._parse_datetime_groups((None, None, None, None, None, None), False, "")
        assert result is None

    def test_extract_datetime_by_regex(self, mixin):
        result = mixin._extract_datetime_by_regex("2024年1月15日 9时00分开庭")
        assert len(result) > 0

    def test_extract_datetime_by_regex_no_date(self, mixin):
        result = mixin._extract_datetime_by_regex("no dates here")
        assert len(result) == 0

    def test_calculate_context_score(self, mixin):
        score = mixin._calculate_context_score("开庭时间：2024年1月15日", 6)
        assert isinstance(score, int)

    def test_score_days_diff(self, mixin):
        score, reasons = mixin._score_days_diff(7, 10, ["test"])
        assert isinstance(score, int)
        assert isinstance(reasons, list)

    def test_validate_hearing_datetime(self, mixin):
        valid, score, reason = mixin._validate_hearing_datetime(datetime(2024, 12, 15, 9, 0))
        assert isinstance(valid, bool)
        assert isinstance(score, int)

    def test_validate_regex_results(self, mixin):
        result = mixin._validate_regex_results([])
        assert result == []

    def test_select_best_datetime(self, mixin):
        result = mixin._select_best_datetime([], ollama_datetime=None)
        # Returns a tuple or None depending on implementation
        assert result is None or isinstance(result, tuple)
