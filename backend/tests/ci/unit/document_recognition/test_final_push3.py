"""Final push coverage tests for document_recognition — data classes and DTOs."""

from __future__ import annotations

from datetime import datetime
from unittest.mock import Mock

import pytest


# ============================================================================
# document_recognition/services/data_classes.py tests
# ============================================================================


class TestDocumentType:
    def test_values(self):
        from apps.document_recognition.services.data_classes import DocumentType

        assert DocumentType.SUMMONS.value == "summons"
        assert DocumentType.EXECUTION_RULING.value == "execution"
        assert DocumentType.OTHER.value == "other"

    def test_from_string(self):
        from apps.document_recognition.services.data_classes import DocumentType

        assert DocumentType("summons") == DocumentType.SUMMONS


class TestRecognitionResult:
    def test_to_dict(self):
        from apps.document_recognition.services.data_classes import DocumentType, RecognitionResult

        result = RecognitionResult(
            document_type=DocumentType.SUMMONS,
            case_number="（2024）粤0606执386号",
            key_time=datetime(2024, 6, 15, 10, 0),
            raw_text="开庭传票",
            confidence=0.95,
            extraction_method="pdf_direct",
        )
        d = result.to_dict()
        assert d["document_type"] == "summons"
        assert d["case_number"] == "（2024）粤0606执386号"
        assert "2024-06-15" in d["key_time"]
        assert d["confidence"] == 0.95

    def test_to_dict_none_key_time(self):
        from apps.document_recognition.services.data_classes import DocumentType, RecognitionResult

        result = RecognitionResult(
            document_type=DocumentType.OTHER,
            case_number=None,
            key_time=None,
            raw_text="其他文书",
            confidence=0.5,
            extraction_method="ocr",
        )
        d = result.to_dict()
        assert d["key_time"] is None

    def test_from_dict_with_string_time(self):
        from apps.document_recognition.services.data_classes import RecognitionResult

        data = {
            "document_type": "summons",
            "case_number": "（2024）粤0606执386号",
            "key_time": "2024-06-15T10:00:00",
            "raw_text": "text",
            "confidence": 0.9,
            "extraction_method": "pdf_direct",
        }
        result = RecognitionResult.from_dict(data)
        assert result.key_time == datetime(2024, 6, 15, 10, 0)
        assert result.document_type.value == "summons"

    def test_from_dict_with_datetime_time(self):
        from apps.document_recognition.services.data_classes import RecognitionResult

        dt = datetime(2024, 6, 15, 10, 0)
        data = {
            "document_type": "execution",
            "key_time": dt,
            "raw_text": "",
            "confidence": 0.0,
            "extraction_method": "",
        }
        result = RecognitionResult.from_dict(data)
        assert result.key_time == dt

    def test_from_dict_no_key_time(self):
        from apps.document_recognition.services.data_classes import RecognitionResult

        data = {
            "document_type": "other",
            "raw_text": "text",
        }
        result = RecognitionResult.from_dict(data)
        assert result.key_time is None


class TestBindingResult:
    def test_to_dict(self):
        from apps.document_recognition.services.data_classes import BindingResult

        result = BindingResult(
            success=True,
            case_id=1,
            case_name="测试案件",
            case_log_id=10,
            message="绑定成功",
        )
        d = result.to_dict()
        assert d["success"] is True
        assert d["case_id"] == 1
        assert d["error_code"] is None

    def test_from_dict(self):
        from apps.document_recognition.services.data_classes import BindingResult

        data = {
            "success": False,
            "case_id": None,
            "message": "未找到",
            "error_code": "NOT_FOUND",
        }
        result = BindingResult.from_dict(data)
        assert result.success is False
        assert result.error_code == "NOT_FOUND"

    def test_success_result_factory(self):
        from apps.document_recognition.services.data_classes import BindingResult

        result = BindingResult.success_result(case_id=1, case_name="案件A", case_log_id=10)
        assert result.success is True
        assert result.case_id == 1
        assert "案件A" in result.message

    def test_failure_result_factory(self):
        from apps.document_recognition.services.data_classes import BindingResult

        result = BindingResult.failure_result(message="失败", error_code="ERR")
        assert result.success is False
        assert result.case_id is None
        assert result.error_code == "ERR"


class TestNotificationResult:
    def test_to_dict(self):
        from apps.document_recognition.services.data_classes import NotificationResult

        now = datetime(2024, 6, 15, 10, 0)
        result = NotificationResult(success=True, message="ok", sent_at=now, file_sent=True)
        d = result.to_dict()
        assert d["success"] is True
        assert "2024-06-15" in d["sent_at"]
        assert d["file_sent"] is True

    def test_to_dict_no_sent_at(self):
        from apps.document_recognition.services.data_classes import NotificationResult

        result = NotificationResult(success=False, message="fail")
        d = result.to_dict()
        assert d["sent_at"] is None

    def test_from_dict_with_string_time(self):
        from apps.document_recognition.services.data_classes import NotificationResult

        data = {
            "success": True,
            "message": "ok",
            "sent_at": "2024-06-15T10:00:00",
            "file_sent": True,
        }
        result = NotificationResult.from_dict(data)
        assert result.sent_at == datetime(2024, 6, 15, 10, 0)

    def test_from_dict_with_datetime_time(self):
        from apps.document_recognition.services.data_classes import NotificationResult

        dt = datetime(2024, 6, 15, 10, 0)
        data = {"success": True, "sent_at": dt}
        result = NotificationResult.from_dict(data)
        assert result.sent_at == dt

    def test_success_result_factory(self):
        from apps.document_recognition.services.data_classes import NotificationResult

        now = datetime(2024, 6, 15, 10, 0)
        result = NotificationResult.success_result(sent_at=now, file_sent=True)
        assert result.success is True
        assert result.file_sent is True

    def test_failure_result_factory(self):
        from apps.document_recognition.services.data_classes import NotificationResult

        result = NotificationResult.failure_result(message="fail", error_code="ERR")
        assert result.success is False
        assert result.error_code == "ERR"


class TestRecognitionResponse:
    def test_to_dict(self):
        from apps.document_recognition.services.data_classes import (
            BindingResult,
            DocumentType,
            RecognitionResponse,
            RecognitionResult,
        )

        recognition = RecognitionResult(
            document_type=DocumentType.SUMMONS,
            case_number=None,
            key_time=None,
            raw_text="",
            confidence=0.8,
            extraction_method="ocr",
        )
        binding = BindingResult.success_result(1, "案件A", 10)
        response = RecognitionResponse(
            recognition=recognition,
            binding=binding,
            file_path="/path/to/file.pdf",
        )
        d = response.to_dict()
        assert d["file_path"] == "/path/to/file.pdf"
        assert d["binding"]["success"] is True

    def test_to_dict_no_binding(self):
        from apps.document_recognition.services.data_classes import (
            DocumentType,
            RecognitionResponse,
            RecognitionResult,
        )

        recognition = RecognitionResult(
            document_type=DocumentType.OTHER,
            case_number=None,
            key_time=None,
            raw_text="",
            confidence=0.5,
            extraction_method="ocr",
        )
        response = RecognitionResponse(recognition=recognition, binding=None, file_path="/file")
        d = response.to_dict()
        assert d["binding"] is None

    def test_from_dict(self):
        from apps.document_recognition.services.data_classes import RecognitionResponse

        data = {
            "recognition": {
                "document_type": "summons",
                "raw_text": "text",
                "confidence": 0.9,
                "extraction_method": "pdf_direct",
            },
            "binding": {
                "success": True,
                "case_id": 1,
                "case_name": "A",
                "case_log_id": 10,
                "message": "ok",
            },
            "file_path": "/test",
        }
        result = RecognitionResponse.from_dict(data)
        assert result.file_path == "/test"
        assert result.binding.success is True

    def test_from_dict_no_binding(self):
        from apps.document_recognition.services.data_classes import RecognitionResponse

        data = {
            "recognition": {
                "document_type": "other",
                "raw_text": "",
                "confidence": 0.0,
                "extraction_method": "",
            },
            "file_path": "/test",
        }
        result = RecognitionResponse.from_dict(data)
        assert result.binding is None
