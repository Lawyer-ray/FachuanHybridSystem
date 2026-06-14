"""Tests for apps.automation.schemas.document_delivery."""

from __future__ import annotations

from datetime import datetime, timezone
from unittest.mock import patch

import pytest

from apps.automation.schemas.document_delivery import (
    DocumentDeliveryRecord,
    DocumentProcessResult,
    DocumentQueryResult,
)


class TestDocumentDeliveryRecord:
    def test_to_dict(self):
        dt = datetime(2024, 6, 15, 10, 30, 0)
        record = DocumentDeliveryRecord(
            case_number="case-1",
            send_time=dt,
            element_index=3,
            document_name="doc.pdf",
            court_name="court",
        )
        d = record.to_dict()
        assert d["case_number"] == "case-1"
        assert d["send_time"] == dt.isoformat()
        assert d["element_index"] == 3
        assert d["document_name"] == "doc.pdf"

    def test_to_dict_none_send_time(self):
        record = DocumentDeliveryRecord(
            case_number="c", send_time=None, element_index=0  # type: ignore[arg-type]
        )
        d = record.to_dict()
        assert d["send_time"] is None

    def test_from_dict_string_time(self):
        data = {
            "case_number": "c1",
            "send_time": "2024-06-15T10:00:00Z",
            "element_index": 1,
        }
        record = DocumentDeliveryRecord.from_dict(data)
        assert record.case_number == "c1"
        assert record.element_index == 1

    def test_from_dict_datetime_time(self):
        dt = datetime(2024, 1, 1, tzinfo=timezone.utc)
        data = {"case_number": "c1", "send_time": dt, "element_index": 0}
        record = DocumentDeliveryRecord.from_dict(data)
        assert record.send_time == dt

    def test_from_dict_none_time(self):
        data = {"case_number": "c1", "send_time": None, "element_index": 0}
        record = DocumentDeliveryRecord.from_dict(data)
        # When send_time is None, timezone.now() is called as fallback
        assert record.send_time is not None

    def test_from_dict_non_string_document_name(self):
        data = {
            "case_number": "c1",
            "send_time": "2024-01-01T00:00:00",
            "element_index": 0,
            "document_name": 123,
            "court_name": None,
        }
        record = DocumentDeliveryRecord.from_dict(data)
        assert record.document_name == "123"
        assert record.court_name == ""

    def test_from_dict_non_int_element(self):
        data = {
            "case_number": "c1",
            "send_time": "2024-01-01T00:00:00",
            "element_index": "5",
        }
        record = DocumentDeliveryRecord.from_dict(data)
        assert record.element_index == 5

    def test_from_dict_non_str_case_number(self):
        data = {
            "case_number": 12345,
            "send_time": "2024-01-01T00:00:00",
            "element_index": 0,
        }
        record = DocumentDeliveryRecord.from_dict(data)
        assert record.case_number == "12345"


class TestDocumentQueryResult:
    def test_dataclass(self):
        result = DocumentQueryResult(
            total_found=10,
            processed_count=8,
            skipped_count=1,
            failed_count=1,
            case_log_ids=[1, 2, 3],
            errors=["err1"],
        )
        assert result.total_found == 10
        assert len(result.case_log_ids) == 3


class TestDocumentProcessResult:
    def test_dataclass(self):
        result = DocumentProcessResult(
            success=True,
            case_id=1,
            case_log_id=2,
            renamed_path="/path/to/file",
            notification_sent=True,
            error_message=None,
        )
        assert result.success is True
        assert result.error_message is None
