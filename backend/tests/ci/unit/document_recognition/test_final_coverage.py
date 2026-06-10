"""Final coverage tests for document_recognition module."""

from __future__ import annotations

from datetime import datetime
from unittest.mock import MagicMock, Mock, patch

import pytest

from apps.document_recognition.services.data_classes import (
    BindingResult,
    DocumentType,
    NotificationResult,
    RecognitionResponse,
    RecognitionResult,
)
from apps.document_recognition.services.case_binding_service import CaseBindingService


# ============================================================================
# DocumentType tests
# ============================================================================


class TestDocumentType:
    def test_values(self):
        assert DocumentType.SUMMONS == "summons"
        assert DocumentType.EXECUTION_RULING == "execution"
        assert DocumentType.OTHER == "other"

    def test_str_behavior(self):
        # str enum's str() returns the full repr
        assert DocumentType.SUMMONS.value == "summons"

    def test_from_value(self):
        assert DocumentType("summons") == DocumentType.SUMMONS
        assert DocumentType("execution") == DocumentType.EXECUTION_RULING


# ============================================================================
# RecognitionResult tests
# ============================================================================


class TestRecognitionResult:
    def test_to_dict(self):
        dt = datetime(2025, 6, 1, 10, 0)
        r = RecognitionResult(
            document_type=DocumentType.SUMMONS,
            case_number="(2025)粤01号",
            key_time=dt,
            raw_text="text",
            confidence=0.9,
            extraction_method="pdf_direct",
        )
        d = r.to_dict()
        assert d["document_type"] == "summons"
        assert "2025-06-01" in d["key_time"]
        assert d["confidence"] == 0.9

    def test_to_dict_no_key_time(self):
        r = RecognitionResult(
            document_type=DocumentType.OTHER,
            case_number=None,
            key_time=None,
            raw_text="",
            confidence=0.0,
            extraction_method="",
        )
        d = r.to_dict()
        assert d["key_time"] is None

    def test_from_dict_with_str_key_time(self):
        data = {
            "document_type": "summons",
            "case_number": "cn",
            "key_time": "2025-06-01T10:00:00",
            "raw_text": "text",
            "confidence": 0.8,
        }
        r = RecognitionResult.from_dict(data)
        assert r.key_time is not None
        assert r.key_time.year == 2025

    def test_from_dict_with_none_key_time(self):
        data = {
            "document_type": "other",
            "key_time": None,
        }
        r = RecognitionResult.from_dict(data)
        assert r.key_time is None

    def test_from_dict_with_datetime_key_time(self):
        dt = datetime(2025, 3, 15)
        data = {
            "document_type": "execution",
            "key_time": dt,
        }
        r = RecognitionResult.from_dict(data)
        assert r.key_time == dt


# ============================================================================
# BindingResult tests
# ============================================================================


class TestBindingResult:
    def test_success_result(self):
        r = BindingResult.success_result(case_id=1, case_name="Test", case_log_id=10)
        assert r.success is True
        assert r.case_id == 1
        assert r.case_name == "Test"
        assert r.case_log_id == 10
        assert "Test" in r.message

    def test_failure_result(self):
        r = BindingResult.failure_result(message="not found", error_code="CASE_NOT_FOUND")
        assert r.success is False
        assert r.case_id is None
        assert r.error_code == "CASE_NOT_FOUND"

    def test_to_dict(self):
        r = BindingResult.success_result(1, "Test", 10)
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
        assert r.case_name == "Test"


# ============================================================================
# NotificationResult tests
# ============================================================================


class TestNotificationResult:
    def test_success_result(self):
        dt = datetime(2025, 1, 1, 12, 0)
        r = NotificationResult.success_result(sent_at=dt, file_sent=True)
        assert r.success is True
        assert r.file_sent is True
        assert r.sent_at == dt

    def test_failure_result(self):
        r = NotificationResult.failure_result(message="fail", error_code="ERR")
        assert r.success is False
        assert r.error_code == "ERR"

    def test_to_dict(self):
        dt = datetime(2025, 1, 1)
        r = NotificationResult(success=True, sent_at=dt)
        d = r.to_dict()
        assert "2025-01-01" in d["sent_at"]

    def test_to_dict_no_sent_at(self):
        r = NotificationResult(success=False)
        d = r.to_dict()
        assert d["sent_at"] is None

    def test_from_dict(self):
        data = {"success": True, "sent_at": "2025-01-01T00:00:00", "file_sent": True}
        r = NotificationResult.from_dict(data)
        assert r.sent_at is not None

    def test_from_dict_none_sent_at(self):
        data = {"success": False, "sent_at": None}
        r = NotificationResult.from_dict(data)
        assert r.sent_at is None

    def test_from_dict_datetime_sent_at(self):
        dt = datetime(2025, 6, 1)
        data = {"success": True, "sent_at": dt}
        r = NotificationResult.from_dict(data)
        assert r.sent_at == dt


# ============================================================================
# RecognitionResponse tests
# ============================================================================


class TestRecognitionResponse:
    def test_to_dict(self):
        rec = RecognitionResult(
            document_type=DocumentType.SUMMONS,
            case_number="cn",
            key_time=None,
            raw_text="",
            confidence=0.5,
            extraction_method="ocr",
        )
        resp = RecognitionResponse(recognition=rec, binding=None, file_path="/path")
        d = resp.to_dict()
        assert d["binding"] is None
        assert d["file_path"] == "/path"

    def test_to_dict_with_binding(self):
        rec = RecognitionResult(
            document_type=DocumentType.SUMMONS,
            case_number="cn",
            key_time=None,
            raw_text="",
            confidence=0.5,
            extraction_method="ocr",
        )
        binding = BindingResult.success_result(1, "Case", 10)
        resp = RecognitionResponse(recognition=rec, binding=binding, file_path="/p")
        d = resp.to_dict()
        assert d["binding"]["success"] is True

    def test_from_dict(self):
        data = {
            "recognition": {
                "document_type": "other",
                "key_time": None,
            },
            "binding": None,
            "file_path": "/path",
        }
        resp = RecognitionResponse.from_dict(data)
        assert resp.file_path == "/path"
        assert resp.binding is None

    def test_from_dict_with_binding(self):
        data = {
            "recognition": {"document_type": "summons", "key_time": None},
            "binding": {"success": True, "case_id": 1, "case_name": "C", "case_log_id": 10, "message": "ok"},
            "file_path": "/p",
        }
        resp = RecognitionResponse.from_dict(data)
        assert resp.binding is not None
        assert resp.binding.success is True


# ============================================================================
# CaseBindingService tests (unit-level, mock ICaseService)
# ============================================================================


class TestCaseBindingServiceFindCase:
    def _make_service(self):
        mock_case_service = MagicMock()
        return CaseBindingService(case_service=mock_case_service), mock_case_service

    def test_empty_case_number(self):
        svc, _ = self._make_service()
        assert svc.find_case_by_number("") is None
        assert svc.find_case_by_number("   ") is None
        assert svc.find_case_by_number(None) is None

    def test_found_case(self):
        svc, mock_cs = self._make_service()
        mock_cs.search_cases_by_case_number_internal.return_value = [MagicMock(id=42)]
        result = svc.find_case_by_number("(2025)粤01号")
        assert result == 42

    def test_not_found(self):
        svc, mock_cs = self._make_service()
        mock_cs.search_cases_by_case_number_internal.return_value = []
        assert svc.find_case_by_number("unknown") is None

    def test_exception_returns_none(self):
        svc, mock_cs = self._make_service()
        mock_cs.search_cases_by_case_number_internal.side_effect = Exception("boom")
        assert svc.find_case_by_number("cn") is None


class TestCaseBindingServiceFormatLogContent:
    def test_summons_with_key_time(self):
        svc = CaseBindingService.__new__(CaseBindingService)
        dt = datetime(2025, 6, 1, 9, 30)
        content = svc.format_log_content(DocumentType.SUMMONS, "cn", dt, "text")
        assert "传票" in content
        assert "开庭时间" in content
        assert "2025-06-01" in content

    def test_execution_ruling_with_key_time(self):
        svc = CaseBindingService.__new__(CaseBindingService)
        dt = datetime(2025, 12, 31)
        content = svc.format_log_content(DocumentType.EXECUTION_RULING, "cn", dt, "text")
        assert "执行裁定书" in content
        assert "保全到期时间" in content

    def test_other_type(self):
        svc = CaseBindingService.__new__(CaseBindingService)
        content = svc.format_log_content(DocumentType.OTHER, "cn", None, "text")
        assert "其他文书" in content

    def test_long_text_truncated(self):
        svc = CaseBindingService.__new__(CaseBindingService)
        long_text = "x" * 1000
        content = svc.format_log_content(DocumentType.OTHER, "cn", None, long_text)
        assert "..." in content

    def test_no_case_number(self):
        svc = CaseBindingService.__new__(CaseBindingService)
        content = svc.format_log_content(DocumentType.SUMMONS, None, None, "text")
        assert "案号" not in content

    def test_no_raw_text(self):
        svc = CaseBindingService.__new__(CaseBindingService)
        content = svc.format_log_content(DocumentType.SUMMONS, "cn", None, "")
        assert "文书内容摘要" not in content


class TestCaseBindingServiceBindDocument:
    def _make_service(self):
        mock_cs = MagicMock()
        return CaseBindingService(case_service=mock_cs), mock_cs

    def test_empty_case_number(self):
        svc, _ = self._make_service()
        result = svc.bind_document_to_case("", DocumentType.OTHER, "c", None, "/f")
        assert result.success is False
        assert result.error_code == "CASE_NUMBER_NOT_FOUND"

    def test_no_matching_case(self):
        svc, mock_cs = self._make_service()
        mock_cs.search_cases_by_case_number_internal.return_value = []
        result = svc.bind_document_to_case("cn", DocumentType.OTHER, "c", None, "/f")
        assert result.success is False

    def test_case_dto_none(self):
        svc, mock_cs = self._make_service()
        mock_cs.search_cases_by_case_number_internal.return_value = [MagicMock(id=1)]
        mock_cs.get_case_by_id_internal.return_value = None
        result = svc.bind_document_to_case("cn", DocumentType.OTHER, "c", None, "/f")
        assert result.success is False


class TestCaseBindingServiceUpdateLogReminder:
    def test_summons_reminder_type(self):
        svc, mock_cs = self._make_service()
        svc._update_log_reminder(1, datetime(2025, 1, 1), DocumentType.SUMMONS)
        mock_cs.update_case_log_reminder_internal.assert_called_once()
        call_kwargs = mock_cs.update_case_log_reminder_internal.call_args[1]
        assert call_kwargs["reminder_type"] == "hearing"

    def test_execution_reminder_type(self):
        svc, mock_cs = self._make_service()
        svc._update_log_reminder(1, datetime(2025, 1, 1), DocumentType.EXECUTION_RULING)
        call_kwargs = mock_cs.update_case_log_reminder_internal.call_args[1]
        assert call_kwargs["reminder_type"] == "asset_preservation_expires"

    def test_other_reminder_type(self):
        svc, mock_cs = self._make_service()
        svc._update_log_reminder(1, datetime(2025, 1, 1), DocumentType.OTHER)
        call_kwargs = mock_cs.update_case_log_reminder_internal.call_args[1]
        assert call_kwargs["reminder_type"] == "other"

    def test_update_failure(self):
        svc, mock_cs = self._make_service()
        mock_cs.update_case_log_reminder_internal.return_value = False
        svc._update_log_reminder(1, datetime(2025, 1, 1), DocumentType.SUMMONS)  # should not raise

    def _make_service(self):
        mock_cs = MagicMock()
        return CaseBindingService(case_service=mock_cs), mock_cs
