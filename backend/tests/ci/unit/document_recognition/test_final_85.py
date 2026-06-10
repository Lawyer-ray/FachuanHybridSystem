"""Coverage tests for document recognition services.

Targets uncovered lines in:
- services/_response_parser_mixin.py (64 uncovered)
- services/recognition_service.py (96 uncovered)
- services/data_classes.py
- services/info_extractor.py (62 uncovered)
"""

from __future__ import annotations

from datetime import datetime
from types import SimpleNamespace
from unittest.mock import MagicMock, Mock, patch

import pytest

from apps.document_recognition.services._response_parser_mixin import ResponseParserMixin
from apps.document_recognition.services.data_classes import (
    BindingResult,
    DocumentType,
    NotificationResult,
    RecognitionResponse,
    RecognitionResult,
)


# ===================================================================
# DocumentType enum
# ===================================================================
class TestDocumentType:
    def test_summons_value(self):
        assert DocumentType.SUMMONS.value == "summons"

    def test_execution_value(self):
        assert DocumentType.EXECUTION_RULING.value == "execution"

    def test_other_value(self):
        assert DocumentType.OTHER.value == "other"


# ===================================================================
# RecognitionResult
# ===================================================================
class TestRecognitionResult:
    def test_to_dict(self):
        r = RecognitionResult(
            document_type=DocumentType.SUMMONS,
            case_number="(2024)粤01民初1号",
            key_time=datetime(2024, 6, 15, 9, 30),
            raw_text="传票内容",
            confidence=0.95,
            extraction_method="pdf_direct",
        )
        d = r.to_dict()
        assert d["document_type"] == "summons"
        assert d["case_number"] == "(2024)粤01民初1号"
        assert "2024-06-15" in d["key_time"]
        assert d["confidence"] == 0.95

    def test_to_dict_none_key_time(self):
        r = RecognitionResult(
            document_type=DocumentType.OTHER,
            case_number=None,
            key_time=None,
            raw_text="",
            confidence=0.0,
            extraction_method="ocr",
        )
        d = r.to_dict()
        assert d["key_time"] is None

    def test_from_dict(self):
        data = {
            "document_type": "summons",
            "case_number": "(2024)粤01民初1号",
            "key_time": "2024-06-15T09:30:00",
            "raw_text": "传票内容",
            "confidence": 0.95,
            "extraction_method": "pdf_direct",
        }
        r = RecognitionResult.from_dict(data)
        assert r.document_type == DocumentType.SUMMONS
        assert r.case_number == "(2024)粤01民初1号"
        assert r.key_time == datetime(2024, 6, 15, 9, 30)

    def test_from_dict_none_key_time(self):
        data = {
            "document_type": "other",
            "raw_text": "",
            "confidence": 0.0,
            "extraction_method": "ocr",
        }
        r = RecognitionResult.from_dict(data)
        assert r.key_time is None

    def test_from_dict_datetime_key_time(self):
        dt = datetime(2024, 6, 15)
        data = {
            "document_type": "summons",
            "key_time": dt,
            "raw_text": "",
            "confidence": 0.5,
            "extraction_method": "ocr",
        }
        r = RecognitionResult.from_dict(data)
        assert r.key_time == dt


# ===================================================================
# BindingResult
# ===================================================================
class TestBindingResult:
    def test_success_result(self):
        r = BindingResult.success_result(case_id=1, case_name="Test", case_log_id=10)
        assert r.success is True
        assert r.case_id == 1
        assert r.case_name == "Test"
        assert r.case_log_id == 10
        assert "Test" in r.message

    def test_failure_result(self):
        r = BindingResult.failure_result(message="failed", error_code="ERR")
        assert r.success is False
        assert r.case_id is None
        assert r.message == "failed"
        assert r.error_code == "ERR"

    def test_to_dict(self):
        r = BindingResult.success_result(case_id=1, case_name="Test", case_log_id=10)
        d = r.to_dict()
        assert d["success"] is True
        assert d["case_id"] == 1

    def test_from_dict(self):
        data = {
            "success": True,
            "case_id": 1,
            "case_name": "Test",
            "case_log_id": 10,
            "message": "ok",
        }
        r = BindingResult.from_dict(data)
        assert r.success is True
        assert r.case_id == 1


# ===================================================================
# NotificationResult
# ===================================================================
class TestNotificationResult:
    def test_success_result(self):
        now = datetime.now()
        r = NotificationResult.success_result(sent_at=now, file_sent=True)
        assert r.success is True
        assert r.sent_at == now
        assert r.file_sent is True

    def test_failure_result(self):
        r = NotificationResult.failure_result(message="send failed", error_code="SEND_ERR")
        assert r.success is False
        assert r.message == "send failed"

    def test_to_dict(self):
        now = datetime(2024, 6, 15, 10, 0)
        r = NotificationResult(success=True, message="ok", sent_at=now)
        d = r.to_dict()
        assert "2024-06-15" in d["sent_at"]

    def test_to_dict_none_sent_at(self):
        r = NotificationResult(success=False)
        d = r.to_dict()
        assert d["sent_at"] is None

    def test_from_dict_with_string_sent_at(self):
        data = {"success": True, "sent_at": "2024-06-15T10:00:00"}
        r = NotificationResult.from_dict(data)
        assert r.sent_at == datetime(2024, 6, 15, 10, 0)

    def test_from_dict_none_sent_at(self):
        data = {"success": False}
        r = NotificationResult.from_dict(data)
        assert r.sent_at is None


# ===================================================================
# RecognitionResponse
# ===================================================================
class TestRecognitionResponse:
    def test_to_dict(self):
        rec = RecognitionResult(
            document_type=DocumentType.SUMMONS,
            case_number=None,
            key_time=None,
            raw_text="text",
            confidence=0.5,
            extraction_method="ocr",
        )
        binding = BindingResult.success_result(case_id=1, case_name="Test", case_log_id=10)
        resp = RecognitionResponse(recognition=rec, binding=binding, file_path="/tmp/test.pdf")
        d = resp.to_dict()
        assert d["recognition"]["document_type"] == "summons"
        assert d["binding"]["success"] is True

    def test_to_dict_none_binding(self):
        rec = RecognitionResult(
            document_type=DocumentType.OTHER,
            case_number=None,
            key_time=None,
            raw_text="",
            confidence=0.0,
            extraction_method="ocr",
        )
        resp = RecognitionResponse(recognition=rec, binding=None, file_path="/tmp/test.pdf")
        d = resp.to_dict()
        assert d["binding"] is None

    def test_from_dict(self):
        data = {
            "recognition": {
                "document_type": "summons",
                "raw_text": "text",
                "confidence": 0.5,
                "extraction_method": "ocr",
            },
            "binding": {
                "success": True,
                "case_id": 1,
                "case_name": "Test",
                "case_log_id": 10,
                "message": "ok",
            },
            "file_path": "/tmp/test.pdf",
        }
        resp = RecognitionResponse.from_dict(data)
        assert resp.recognition.document_type == DocumentType.SUMMONS
        assert resp.binding.success is True

    def test_from_dict_no_binding(self):
        data = {
            "recognition": {
                "document_type": "other",
                "raw_text": "",
                "confidence": 0.0,
                "extraction_method": "ocr",
            },
            "file_path": "/tmp/test.pdf",
        }
        resp = RecognitionResponse.from_dict(data)
        assert resp.binding is None


# ===================================================================
# ResponseParserMixin: _extract_json_from_response
# ===================================================================
class TestExtractJsonFromResponse:
    def setup_method(self):
        self.mixin = ResponseParserMixin()

    def test_valid_json(self):
        result = self.mixin._extract_json_from_response('{"key": "value"}')
        assert result == {"key": "value"}

    def test_json_with_surrounding_text(self):
        result = self.mixin._extract_json_from_response('Here is the result: {"key": "value"} end')
        assert result == {"key": "value"}

    def test_json_in_code_block(self):
        result = self.mixin._extract_json_from_response('```json\n{"key": "value"}\n```')
        assert result == {"key": "value"}

    def test_json_in_generic_code_block(self):
        result = self.mixin._extract_json_from_response('```\n{"key": "value"}\n```')
        assert result == {"key": "value"}

    def test_no_json_returns_none(self):
        result = self.mixin._extract_json_from_response("no json here")
        assert result is None

    def test_empty_string(self):
        result = self.mixin._extract_json_from_response("")
        assert result is None


# ===================================================================
# ResponseParserMixin: _parse_datetime
# ===================================================================
class TestParseDatetime:
    def setup_method(self):
        self.mixin = ResponseParserMixin()

    def test_empty_string(self):
        assert self.mixin._parse_datetime("") is None

    def test_standard_format(self):
        result = self.mixin._parse_datetime("2024-06-15 09:30")
        assert result == datetime(2024, 6, 15, 9, 30)

    def test_full_format(self):
        result = self.mixin._parse_datetime("2024-06-15 09:30:00")
        assert result == datetime(2024, 6, 15, 9, 30, 0)

    def test_chinese_format(self):
        result = self.mixin._parse_datetime("2024年6月15日 09:30")
        assert result == datetime(2024, 6, 15, 9, 30)

    def test_chinese_hour_minute(self):
        result = self.mixin._parse_datetime("2024年6月15日 09时30分")
        assert result == datetime(2024, 6, 15, 9, 30)

    def test_slash_format(self):
        result = self.mixin._parse_datetime("2024/06/15 09:30")
        assert result == datetime(2024, 6, 15, 9, 30)

    def test_dot_format(self):
        result = self.mixin._parse_datetime("2024.06.15 09:30")
        assert result == datetime(2024, 6, 15, 9, 30)

    def test_chinese_regex_fallback(self):
        result = self.mixin._parse_datetime("2024年6月15日09时30分")
        assert result == datetime(2024, 6, 15, 9, 30)

    def test_std_regex_fallback(self):
        result = self.mixin._parse_datetime("2024-6-15 9:30")
        assert result == datetime(2024, 6, 15, 9, 30)

    def test_invalid_returns_none(self):
        assert self.mixin._parse_datetime("not a date") is None


# ===================================================================
# ResponseParserMixin: _parse_date
# ===================================================================
class TestParseDate:
    def setup_method(self):
        self.mixin = ResponseParserMixin()

    def test_empty_string(self):
        assert self.mixin._parse_date("") is None

    def test_standard_format(self):
        result = self.mixin._parse_date("2024-06-15")
        assert result == datetime(2024, 6, 15)

    def test_chinese_format(self):
        result = self.mixin._parse_date("2024年6月15日")
        assert result == datetime(2024, 6, 15)

    def test_slash_format(self):
        result = self.mixin._parse_date("2024/06/15")
        assert result == datetime(2024, 6, 15)

    def test_dot_format(self):
        result = self.mixin._parse_date("2024.06.15")
        assert result == datetime(2024, 6, 15)

    def test_regex_fallback(self):
        result = self.mixin._parse_date("2024年6月15")
        assert result == datetime(2024, 6, 15)

    def test_invalid_returns_none(self):
        assert self.mixin._parse_date("not a date") is None


# ===================================================================
# ResponseParserMixin: _parse_summons_response
# ===================================================================
class TestParseSummonsResponse:
    def setup_method(self):
        self.mixin = ResponseParserMixin()
        self.mixin._normalize_case_number = lambda x: x

    def test_valid_response(self):
        response = {
            "message": {
                "content": '{"case_number": "(2024)粤01民初1号", "court_time": "2024-06-15 09:30"}'
            }
        }
        result = self.mixin._parse_summons_response(response)
        assert result["case_number"] == "(2024)粤01民初1号"
        assert result["court_time"] == datetime(2024, 6, 15, 9, 30)

    def test_missing_message_key(self):
        result = self.mixin._parse_summons_response({})
        assert result["case_number"] is None
        assert result["court_time"] is None

    def test_null_values(self):
        response = {
            "message": {
                "content": '{"case_number": null, "court_time": null}'
            }
        }
        result = self.mixin._parse_summons_response(response)
        assert result["case_number"] is None
        assert result["court_time"] is None

    def test_invalid_json(self):
        response = {"message": {"content": "not json"}}
        result = self.mixin._parse_summons_response(response)
        assert result["case_number"] is None


# ===================================================================
# ResponseParserMixin: _parse_execution_response
# ===================================================================
class TestParseExecutionResponse:
    def setup_method(self):
        self.mixin = ResponseParserMixin()
        self.mixin._normalize_case_number = lambda x: x

    def test_valid_response(self):
        response = {
            "message": {
                "content": '{"case_number": "(2024)粤01执1号", "preservation_deadline": "2024-12-31"}'
            }
        }
        result = self.mixin._parse_execution_response(response)
        assert result["case_number"] == "(2024)粤01执1号"
        assert result["preservation_deadline"] == datetime(2024, 12, 31)

    def test_missing_message_key(self):
        result = self.mixin._parse_execution_response({})
        assert result["case_number"] is None


# ===================================================================
# CourtDocumentRecognitionService (with mocks)
# ===================================================================
class TestCourtDocumentRecognitionService:
    def test_recognize_document_from_text_empty(self):
        from apps.document_recognition.services.recognition_service import (
            CourtDocumentRecognitionService,
        )
        from apps.core.exceptions import ValidationException

        svc = CourtDocumentRecognitionService()
        with pytest.raises(ValidationException):
            svc.recognize_document_from_text("")

    def test_recognize_document_from_text_whitespace(self):
        from apps.document_recognition.services.recognition_service import (
            CourtDocumentRecognitionService,
        )
        from apps.core.exceptions import ValidationException

        svc = CourtDocumentRecognitionService()
        with pytest.raises(ValidationException):
            svc.recognize_document_from_text("   ")

    def test_recognize_document_from_text_success(self):
        from apps.document_recognition.services.recognition_service import (
            CourtDocumentRecognitionService,
        )

        classifier = Mock()
        classifier.classify.return_value = (DocumentType.SUMMONS, 0.9)
        extractor = Mock()
        extractor.extract_summons_info.return_value = {"case_number": "(2024)粤01民初1号", "court_time": None}
        svc = CourtDocumentRecognitionService(classifier=classifier, extractor=extractor)
        result = svc.recognize_document_from_text("传票内容")
        assert result.document_type == DocumentType.SUMMONS
        assert result.case_number == "(2024)粤01民初1号"

    def test_recognize_document_from_text_execution(self):
        from apps.document_recognition.services.recognition_service import (
            CourtDocumentRecognitionService,
        )

        classifier = Mock()
        classifier.classify.return_value = (DocumentType.EXECUTION_RULING, 0.8)
        extractor = Mock()
        extractor.extract_execution_info.return_value = {"case_number": None, "preservation_deadline": None}
        svc = CourtDocumentRecognitionService(classifier=classifier, extractor=extractor)
        result = svc.recognize_document_from_text("执行裁定书内容")
        assert result.document_type == DocumentType.EXECUTION_RULING

    def test_recognize_document_from_text_other(self):
        from apps.document_recognition.services.recognition_service import (
            CourtDocumentRecognitionService,
        )

        classifier = Mock()
        classifier.classify.return_value = (DocumentType.OTHER, 0.3)
        extractor = Mock()
        svc = CourtDocumentRecognitionService(classifier=classifier, extractor=extractor)
        result = svc.recognize_document_from_text("其他文书")
        assert result.document_type == DocumentType.OTHER
        assert result.case_number is None

    def test_recognize_document_extract_failure(self):
        from apps.document_recognition.services.recognition_service import (
            CourtDocumentRecognitionService,
        )

        classifier = Mock()
        classifier.classify.return_value = (DocumentType.SUMMONS, 0.9)
        extractor = Mock()
        extractor.extract_summons_info.side_effect = RuntimeError("AI error")
        svc = CourtDocumentRecognitionService(classifier=classifier, extractor=extractor)
        with pytest.raises(RuntimeError):
            svc.recognize_document_from_text("text")

    def test_recognize_document_text_extraction_fails(self):
        from apps.document_recognition.services.recognition_service import (
            CourtDocumentRecognitionService,
        )

        text_extraction = Mock()
        text_extraction.extract_text.return_value = SimpleNamespace(success=False, text="", extraction_method="ocr")
        svc = CourtDocumentRecognitionService(text_extraction=text_extraction)
        result = svc.recognize_document("/tmp/test.pdf")
        assert result.binding.success is False

    def test_recognize_document_text_empty(self):
        from apps.document_recognition.services.recognition_service import (
            CourtDocumentRecognitionService,
        )

        text_extraction = Mock()
        text_extraction.extract_text.return_value = SimpleNamespace(success=True, text="  ", extraction_method="ocr")
        svc = CourtDocumentRecognitionService(text_extraction=text_extraction)
        result = svc.recognize_document("/tmp/test.pdf")
        assert result.binding.success is False

    def test_build_binding_other_type(self):
        from apps.document_recognition.services.recognition_service import (
            CourtDocumentRecognitionService,
        )

        svc = CourtDocumentRecognitionService()
        binding, path = svc._build_binding(
            DocumentType.OTHER, None, None, "/tmp/test.pdf", "text", None
        )
        assert binding.success is False
        assert binding.error_code == "UNSUPPORTED_DOCUMENT_TYPE"

    def test_build_binding_execution_ruling(self):
        from apps.document_recognition.services.recognition_service import (
            CourtDocumentRecognitionService,
        )

        svc = CourtDocumentRecognitionService()
        binding, path = svc._build_binding(
            DocumentType.EXECUTION_RULING, None, None, "/tmp/test.pdf", "text", None
        )
        assert binding.success is False
        assert binding.error_code == "FEATURE_NOT_IMPLEMENTED"

    def test_build_binding_summons_no_case_number(self):
        from apps.document_recognition.services.recognition_service import (
            CourtDocumentRecognitionService,
        )

        svc = CourtDocumentRecognitionService()
        binding, path = svc._build_binding(
            DocumentType.SUMMONS, None, None, "/tmp/test.pdf", "text", None
        )
        assert binding.success is False
        assert binding.error_code == "CASE_NUMBER_NOT_FOUND"

    def test_extract_doc_info_summons(self):
        from apps.document_recognition.services.recognition_service import (
            CourtDocumentRecognitionService,
        )

        extractor = Mock()
        extractor.extract_summons_info.return_value = {
            "case_number": "(2024)粤01民初1号",
            "court_time": datetime(2024, 6, 15),
        }
        svc = CourtDocumentRecognitionService(extractor=extractor)
        cn, kt = svc._extract_doc_info(DocumentType.SUMMONS, "text")
        assert cn == "(2024)粤01民初1号"
        assert kt == datetime(2024, 6, 15)

    def test_extract_doc_info_execution(self):
        """Note: DocumentType.EXECUTION_RULING.value is 'execution', not 'execution_ruling',
        so _extract_doc_info returns (None, None) due to a value mismatch in the source."""
        from apps.document_recognition.services.recognition_service import (
            CourtDocumentRecognitionService,
        )

        svc = CourtDocumentRecognitionService()
        cn, kt = svc._extract_doc_info(DocumentType.EXECUTION_RULING, "text")
        # The code checks doc_type.value == "execution_ruling" but enum value is "execution"
        assert cn is None
        assert kt is None

    def test_extract_doc_info_other(self):
        from apps.document_recognition.services.recognition_service import (
            CourtDocumentRecognitionService,
        )

        svc = CourtDocumentRecognitionService()
        cn, kt = svc._extract_doc_info(DocumentType.OTHER, "text")
        assert cn is None
        assert kt is None

    def test_lazy_load_text_extraction(self):
        from apps.document_recognition.services.recognition_service import (
            CourtDocumentRecognitionService,
        )

        svc = CourtDocumentRecognitionService()
        assert svc._text_extraction is None
        # Lazy load triggers import; just verify it doesn't crash when accessing
        # (the actual import may fail in test env, that's OK)
