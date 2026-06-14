"""Tests for document_recognition services: data_classes and case_binding."""
from __future__ import annotations

from datetime import datetime
from typing import Any
from unittest.mock import MagicMock, patch

import pytest

from apps.core.exceptions import NotFoundError
from apps.document_recognition.services.data_classes import (
    BindingResult,
    DocumentType,
    NotificationResult,
    RecognitionResponse,
    RecognitionResult,
)
from apps.document_recognition.services.case_binding_service import CaseBindingService


# ---------------------------------------------------------------------------
# DocumentType
# ---------------------------------------------------------------------------


class TestDocumentType:
    def test_values(self) -> None:
        assert DocumentType.SUMMONS.value == "summons"
        assert DocumentType.EXECUTION_RULING.value == "execution"
        assert DocumentType.OTHER.value == "other"

    def test_from_string(self) -> None:
        assert DocumentType("summons") == DocumentType.SUMMONS
        assert DocumentType("execution") == DocumentType.EXECUTION_RULING

    def test_invalid_string(self) -> None:
        with pytest.raises(ValueError):
            DocumentType("invalid")


# ---------------------------------------------------------------------------
# RecognitionResult
# ---------------------------------------------------------------------------


class TestRecognitionResult:
    def test_to_dict(self) -> None:
        dt = datetime(2024, 1, 15, 10, 30)
        r = RecognitionResult(
            document_type=DocumentType.SUMMONS,
            case_number="(2024)京01民初1号",
            key_time=dt,
            raw_text="some text",
            confidence=0.95,
            extraction_method="pdf_direct",
        )
        d = r.to_dict()
        assert d["document_type"] == "summons"
        assert d["case_number"] == "(2024)京01民初1号"
        assert d["key_time"] == dt.isoformat()
        assert d["confidence"] == 0.95

    def test_to_dict_no_key_time(self) -> None:
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

    def test_from_dict(self) -> None:
        dt = datetime(2024, 1, 15, 10, 30)
        data = {
            "document_type": "summons",
            "case_number": "(2024)京01民初1号",
            "key_time": dt.isoformat(),
            "raw_text": "some text",
            "confidence": 0.95,
            "extraction_method": "pdf_direct",
        }
        r = RecognitionResult.from_dict(data)
        assert r.document_type == DocumentType.SUMMONS
        assert r.key_time == dt

    def test_from_dict_no_key_time(self) -> None:
        data = {"document_type": "other"}
        r = RecognitionResult.from_dict(data)
        assert r.key_time is None
        assert r.case_number is None

    def test_from_dict_datetime_object(self) -> None:
        dt = datetime(2024, 1, 15, 10, 30)
        data = {"document_type": "execution", "key_time": dt}
        r = RecognitionResult.from_dict(data)
        assert r.key_time == dt


# ---------------------------------------------------------------------------
# BindingResult
# ---------------------------------------------------------------------------


class TestBindingResult:
    def test_to_dict(self) -> None:
        b = BindingResult(
            success=True,
            case_id=1,
            case_name="test",
            case_log_id=10,
            message="ok",
        )
        d = b.to_dict()
        assert d["success"] is True
        assert d["case_id"] == 1

    def test_from_dict(self) -> None:
        data = {
            "success": True,
            "case_id": 1,
            "case_name": "test",
            "case_log_id": 10,
            "message": "ok",
        }
        b = BindingResult.from_dict(data)
        assert b.success is True
        assert b.case_id == 1

    def test_from_dict_defaults(self) -> None:
        b = BindingResult.from_dict({})
        assert b.success is False
        assert b.message == ""

    def test_success_result(self) -> None:
        b = BindingResult.success_result(1, "案件名", 10)
        assert b.success is True
        assert b.case_id == 1
        assert "案件名" in b.message

    def test_failure_result(self) -> None:
        b = BindingResult.failure_result("not found", "NOT_FOUND")
        assert b.success is False
        assert b.error_code == "NOT_FOUND"


# ---------------------------------------------------------------------------
# NotificationResult
# ---------------------------------------------------------------------------


class TestNotificationResult:
    def test_to_dict(self) -> None:
        dt = datetime(2024, 1, 15, 10, 30)
        n = NotificationResult(success=True, message="ok", sent_at=dt, file_sent=True)
        d = n.to_dict()
        assert d["success"] is True
        assert d["sent_at"] == dt.isoformat()
        assert d["file_sent"] is True

    def test_to_dict_no_sent_at(self) -> None:
        n = NotificationResult(success=False, message="failed")
        d = n.to_dict()
        assert d["sent_at"] is None

    def test_from_dict(self) -> None:
        dt = datetime(2024, 1, 15, 10, 30)
        data = {
            "success": True,
            "message": "ok",
            "sent_at": dt.isoformat(),
            "file_sent": True,
        }
        n = NotificationResult.from_dict(data)
        assert n.success is True
        assert n.sent_at == dt

    def test_from_dict_datetime_object(self) -> None:
        dt = datetime(2024, 1, 15, 10, 30)
        n = NotificationResult.from_dict({"success": True, "sent_at": dt})
        assert n.sent_at == dt

    def test_from_dict_no_sent_at(self) -> None:
        n = NotificationResult.from_dict({"success": False})
        assert n.sent_at is None

    def test_success_result(self) -> None:
        dt = datetime(2024, 1, 15, 10, 30)
        n = NotificationResult.success_result(dt, file_sent=True)
        assert n.success is True
        assert n.file_sent is True
        assert "成功" in n.message

    def test_failure_result(self) -> None:
        n = NotificationResult.failure_result("error", "ERR")
        assert n.success is False
        assert n.error_code == "ERR"


# ---------------------------------------------------------------------------
# RecognitionResponse
# ---------------------------------------------------------------------------


class TestRecognitionResponse:
    def test_to_dict(self) -> None:
        rec = RecognitionResult(
            document_type=DocumentType.SUMMONS,
            case_number="test",
            key_time=None,
            raw_text="",
            confidence=0.9,
            extraction_method="pdf_direct",
        )
        resp = RecognitionResponse(recognition=rec, binding=None, file_path="/tmp/test.pdf")
        d = resp.to_dict()
        assert d["recognition"]["document_type"] == "summons"
        assert d["binding"] is None
        assert d["file_path"] == "/tmp/test.pdf"

    def test_to_dict_with_binding(self) -> None:
        rec = RecognitionResult(
            document_type=DocumentType.SUMMONS,
            case_number="test",
            key_time=None,
            raw_text="",
            confidence=0.9,
            extraction_method="pdf_direct",
        )
        binding = BindingResult(success=True, case_id=1, case_name="c", case_log_id=2, message="ok")
        resp = RecognitionResponse(recognition=rec, binding=binding, file_path="/tmp/test.pdf")
        d = resp.to_dict()
        assert d["binding"]["success"] is True

    def test_from_dict(self) -> None:
        data = {
            "recognition": {
                "document_type": "summons",
                "confidence": 0.9,
                "extraction_method": "pdf_direct",
            },
            "binding": {
                "success": True,
                "case_id": 1,
                "case_name": "test",
                "case_log_id": 2,
                "message": "ok",
            },
            "file_path": "/tmp/test.pdf",
        }
        resp = RecognitionResponse.from_dict(data)
        assert resp.recognition.document_type == DocumentType.SUMMONS
        assert resp.binding is not None
        assert resp.file_path == "/tmp/test.pdf"

    def test_from_dict_no_binding(self) -> None:
        data = {
            "recognition": {"document_type": "other"},
            "file_path": "",
        }
        resp = RecognitionResponse.from_dict(data)
        assert resp.binding is None


# ---------------------------------------------------------------------------
# CaseBindingService
# ---------------------------------------------------------------------------


class TestCaseBindingServiceInit:
    def test_default_init(self) -> None:
        svc = CaseBindingService()
        assert svc._case_service is None

    def test_injected_service(self) -> None:
        mock_cs = MagicMock()
        svc = CaseBindingService(case_service=mock_cs)
        assert svc._case_service is mock_cs

    def test_case_service_property_lazy(self) -> None:
        svc = CaseBindingService()
        with patch("apps.core.interfaces.ServiceLocator") as mock_loc:
            mock_cs = MagicMock()
            mock_loc.get_case_service.return_value = mock_cs
            cs = svc.case_service
            assert cs is mock_cs
            assert svc._case_service is mock_cs


class TestCaseBindingServiceFindByNumber:
    def test_empty_number_returns_none(self) -> None:
        svc = CaseBindingService()
        assert svc.find_case_by_number("") is None
        assert svc.find_case_by_number("   ") is None
        assert svc.find_case_by_number("") is None

    def test_valid_number_calls_service(self) -> None:
        mock_cs = MagicMock()
        mock_case = MagicMock()
        mock_case.id = 1
        mock_cs.search_cases_by_case_number_internal.return_value = [mock_case]
        svc = CaseBindingService(case_service=mock_cs)
        result = svc.find_case_by_number("2024京01民初1号")
        assert result == 1

    def test_no_match_returns_none(self) -> None:
        mock_cs = MagicMock()
        mock_cs.search_cases_by_case_number_internal.return_value = []
        svc = CaseBindingService(case_service=mock_cs)
        result = svc.find_case_by_number("2024京01民初1号")
        assert result is None
