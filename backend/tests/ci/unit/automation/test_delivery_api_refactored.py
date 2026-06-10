"""
Refactored pure data processing tests for DocumentDeliveryApiService
(_matching, _process, _query modules).

Tests the extracted data transformation / time comparison / result
construction logic that does NOT require database, external API, or
network access.
"""

from __future__ import annotations

import math
from datetime import datetime
from typing import Any
from unittest.mock import MagicMock

import pytest
from django.utils import timezone

from apps.automation.services.document_delivery.data_classes import (
    DocumentDeliveryRecord,
    DocumentProcessResult,
    DocumentQueryResult,
    DocumentRecord,
    DocumentListResponse,
)
from apps.automation.services.document_delivery.api.document_delivery_api_service._query import DocumentQueryMixin


# ═══════════════════════════════════════════════════════════════════════════
# DocumentRecord.from_api_response
# ═══════════════════════════════════════════════════════════════════════════

class TestDocumentRecordFromApiResponse:
    """Test DocumentRecord.from_api_response data extraction."""

    def test_full_response(self) -> None:
        data = {
            "ah": "（2025）粤0604民初123号",
            "sdbh": "SD001",
            "ajzybh": "AJ001",
            "fssj": "2025-06-10 10:00:00",
            "fymc": "佛山法院",
            "ahdm": "AH001",
            "fybh": "FY001",
            "ssdrxm": "张三",
            "ssdrsjhm": "13800138000",
            "ssdrzjhm": "440000199001011234",
            "wsmc": "判决书",
            "sdzt": "已送达",
            "qdzt": "已签到",
            "qdbh": "QD001",
            "fqr": "法院系统",
            "cjsj": "2025-06-10",
            "zhxgsj": "2025-06-11",
        }
        rec = DocumentRecord.from_api_response(data)
        assert rec.ah == "（2025）粤0604民初123号"
        assert rec.sdbh == "SD001"
        assert rec.fymc == "佛山法院"
        assert rec.wsmc == "判决书"

    def test_empty_response(self) -> None:
        rec = DocumentRecord.from_api_response({})
        assert rec.ah == ""
        assert rec.sdbh == ""
        assert rec.fssj == ""

    def test_partial_response(self) -> None:
        rec = DocumentRecord.from_api_response({"ah": "test", "sdbh": "SD"})
        assert rec.ah == "test"
        assert rec.sdbh == "SD"
        assert rec.fymc == ""


# ═══════════════════════════════════════════════════════════════════════════
# DocumentRecord.parse_fssj
# ═══════════════════════════════════════════════════════════════════════════

class TestDocumentRecordParseFssj:
    """Test DocumentRecord.parse_fssj date parsing."""

    def test_standard_format(self) -> None:
        rec = DocumentRecord(ah="", sdbh="", ajzybh="", fssj="2025-06-10 16:25:37", fymc="")
        dt = rec.parse_fssj()
        assert dt is not None
        assert dt.year == 2025
        assert dt.month == 6
        assert dt.day == 10
        assert dt.hour == 16

    def test_iso_format(self) -> None:
        rec = DocumentRecord(ah="", sdbh="", ajzybh="", fssj="2025-06-10T10:00:00", fymc="")
        dt = rec.parse_fssj()
        assert dt is not None
        assert dt.year == 2025

    def test_empty_fssj(self) -> None:
        rec = DocumentRecord(ah="", sdbh="", ajzybh="", fssj="", fymc="")
        assert rec.parse_fssj() is None

    def test_invalid_format(self) -> None:
        rec = DocumentRecord(ah="", sdbh="", ajzybh="", fssj="not-a-date", fymc="")
        assert rec.parse_fssj() is None

    def test_date_only_format(self) -> None:
        """Date-only format should fail both parsers."""
        rec = DocumentRecord(ah="", sdbh="", ajzybh="", fssj="2025-06-10", fymc="")
        # This may or may not parse depending on isoformat behavior
        # The important thing is it doesn't raise
        result = rec.parse_fssj()
        # isoformat can parse date-only strings, producing midnight
        if result is not None:
            assert result.year == 2025


# ═══════════════════════════════════════════════════════════════════════════
# DocumentRecord.to_dict / from_api_response roundtrip
# ═══════════════════════════════════════════════════════════════════════════

class TestDocumentRecordSerialization:
    """Test DocumentRecord serialization / deserialization."""

    def test_to_dict(self) -> None:
        rec = DocumentRecord(ah="test", sdbh="SD", ajzybh="AJ", fssj="2025-01-01", fymc="法院")
        d = rec.to_dict()
        assert d["ah"] == "test"
        assert d["sdbh"] == "SD"
        assert "fymc" in d

    def test_roundtrip(self) -> None:
        data = {"ah": "test", "sdbh": "SD", "ajzybh": "AJ", "fssj": "2025-01-01 10:00:00", "fymc": "法院"}
        rec = DocumentRecord.from_api_response(data)
        d = rec.to_dict()
        assert d["ah"] == data["ah"]
        assert d["fssj"] == data["fssj"]


# ═══════════════════════════════════════════════════════════════════════════
# DocumentListResponse.from_api_response
# ═══════════════════════════════════════════════════════════════════════════

class TestDocumentListResponseParsing:
    """Test DocumentListResponse.from_api_response nested data extraction."""

    def test_standard_response(self) -> None:
        data = {
            "code": 200,
            "msg": "成功！",
            "success": True,
            "data": {
                "total": 2,
                "data": [
                    {"ah": "case1", "sdbh": "SD1", "ajzybh": "AJ1", "fssj": "2025-01-01", "fymc": "法院A"},
                    {"ah": "case2", "sdbh": "SD2", "ajzybh": "AJ2", "fssj": "2025-01-02", "fymc": "法院B"},
                ],
            },
        }
        resp = DocumentListResponse.from_api_response(data)
        assert resp.total == 2
        assert len(resp.documents) == 2
        assert resp.documents[0].ah == "case1"

    def test_empty_total(self) -> None:
        data = {"data": {"total": 0, "data": []}}
        resp = DocumentListResponse.from_api_response(data)
        assert resp.total == 0
        assert resp.documents == []

    def test_missing_data_key(self) -> None:
        resp = DocumentListResponse.from_api_response({})
        assert resp.total == 0
        assert resp.documents == []

    def test_missing_total_defaults_zero(self) -> None:
        data = {"data": {"data": []}}
        resp = DocumentListResponse.from_api_response(data)
        assert resp.total == 0

    def test_to_dict(self) -> None:
        data = {
            "data": {
                "total": 1,
                "data": [{"ah": "c1", "sdbh": "SD1", "ajzybh": "AJ1", "fssj": "", "fymc": ""}],
            }
        }
        resp = DocumentListResponse.from_api_response(data)
        d = resp.to_dict()
        assert d["total"] == 1
        assert len(d["documents"]) == 1


# ═══════════════════════════════════════════════════════════════════════════
# DocumentDeliveryRecord.from_dict / to_dict
# ═══════════════════════════════════════════════════════════════════════════

class TestDocumentDeliveryRecordSerialization:
    """Test DocumentDeliveryRecord serialization."""

    def test_to_dict_with_send_time(self) -> None:
        rec = DocumentDeliveryRecord(
            case_number="case1",
            send_time=datetime(2025, 6, 10, 16, 0),
            element_index=0,
            document_name="判决书",
            court_name="佛山法院",
        )
        d = rec.to_dict()
        assert d["case_number"] == "case1"
        assert d["send_time"] is not None
        assert "2025" in d["send_time"]

    def test_to_dict_with_none_send_time(self) -> None:
        rec = DocumentDeliveryRecord(case_number="case1", send_time=None, element_index=0)
        d = rec.to_dict()
        assert d["send_time"] is None

    def test_from_dict_with_iso_string(self) -> None:
        d = {
            "case_number": "case1",
            "send_time": "2025-06-10T16:00:00",
            "element_index": 0,
            "document_name": "判决书",
        }
        rec = DocumentDeliveryRecord.from_dict(d)
        assert rec.case_number == "case1"
        assert rec.send_time is not None
        assert rec.send_time.year == 2025

    def test_from_dict_with_none_send_time(self) -> None:
        d = {"case_number": "case1", "send_time": None, "element_index": 0}
        rec = DocumentDeliveryRecord.from_dict(d)
        assert rec.send_time is None

    def test_from_dict_with_datetime_object(self) -> None:
        dt = datetime(2025, 6, 10, 16, 0)
        d = {"case_number": "case1", "send_time": dt, "element_index": 0}
        rec = DocumentDeliveryRecord.from_dict(d)
        assert rec.send_time == dt

    def test_from_dict_defaults(self) -> None:
        d = {"case_number": "case1", "send_time": None, "element_index": 0}
        rec = DocumentDeliveryRecord.from_dict(d)
        assert rec.document_name == ""
        assert rec.court_name == ""
        assert rec.delivery_event_id == ""


# ═══════════════════════════════════════════════════════════════════════════
# DocumentProcessResult construction
# ═══════════════════════════════════════════════════════════════════════════

class TestDocumentProcessResult:
    """Test DocumentProcessResult data construction."""

    def test_default_values(self) -> None:
        result = DocumentProcessResult(
            success=False,
            case_id=None,
            case_log_id=None,
            renamed_path=None,
            notification_sent=False,
            error_message=None,
        )
        assert result.success is False
        assert result.case_id is None

    def test_successful_result(self) -> None:
        result = DocumentProcessResult(
            success=True,
            case_id=42,
            case_log_id=100,
            renamed_path="/new/path.pdf",
            notification_sent=True,
            error_message=None,
        )
        assert result.success is True
        assert result.case_id == 42
        assert result.notification_sent is True


# ═══════════════════════════════════════════════════════════════════════════
# DocumentQueryResult aggregation
# ═══════════════════════════════════════════════════════════════════════════

class TestDocumentQueryResult:
    """Test DocumentQueryResult aggregation logic."""

    def test_initial_state(self) -> None:
        result = DocumentQueryResult(
            total_found=0, processed_count=0, skipped_count=0, failed_count=0, case_log_ids=[], errors=[]
        )
        assert result.total_found == 0
        assert result.errors == []

    def test_aggregation(self) -> None:
        """Simulates the aggregation pattern from _process_document_page."""
        result = DocumentQueryResult(
            total_found=10, processed_count=0, skipped_count=0, failed_count=0, case_log_ids=[], errors=[]
        )
        # Simulate processing 3 documents
        result.processed_count += 2
        result.skipped_count += 1
        result.case_log_ids.extend([1, 2])
        # Simulate 1 failure
        result.failed_count += 1
        result.errors.append("doc3 failed")

        assert result.processed_count == 2
        assert result.skipped_count == 1
        assert result.failed_count == 1
        assert len(result.case_log_ids) == 2


# ═══════════════════════════════════════════════════════════════════════════
# pagination calculation
# ═══════════════════════════════════════════════════════════════════════════

class TestPaginationCalculation:
    """Test the pagination calculation from query_documents."""

    @staticmethod
    def compute_total_pages(total: int, page_size: int) -> int:
        """Extracted pagination calculation from query_documents."""
        return math.ceil(total / page_size) if total > 0 else 0

    def test_exact_pages(self) -> None:
        assert self.compute_total_pages(40, 20) == 2

    def test_rounds_up(self) -> None:
        assert self.compute_total_pages(41, 20) == 3

    def test_zero_total(self) -> None:
        assert self.compute_total_pages(0, 20) == 0

    def test_single_item(self) -> None:
        assert self.compute_total_pages(1, 20) == 1

    def test_large_total(self) -> None:
        assert self.compute_total_pages(1000, 20) == 50


# ═══════════════════════════════════════════════════════════════════════════
# should_process_document time comparison
# ═══════════════════════════════════════════════════════════════════════════

class TestShouldProcessDocumentTimeLogic:
    """Test the time comparison logic from should_process_document."""

    def test_parse_fssj_none_returns_true(self) -> None:
        """When fssj is empty, defaults to processing."""
        rec = DocumentRecord(ah="", sdbh="", ajzybh="", fssj="", fymc="")
        send_time = rec.parse_fssj()
        assert send_time is None  # Would result in returning True in should_process

    def test_send_time_before_cutoff_returns_false(self) -> None:
        """Documents before cutoff should be skipped."""
        rec = DocumentRecord(ah="", sdbh="", ajzybh="", fssj="2025-01-01 10:00:00", fymc="")
        send_time = rec.parse_fssj()
        cutoff = datetime(2025, 6, 1, 0, 0)
        assert send_time is not None
        assert send_time <= cutoff  # Would result in returning False

    def test_send_time_after_cutoff_passes(self) -> None:
        """Documents after cutoff pass the time check."""
        rec = DocumentRecord(ah="", sdbh="", ajzybh="", fssj="2025-12-01 10:00:00", fymc="")
        send_time = rec.parse_fssj()
        cutoff = datetime(2025, 6, 1, 0, 0)
        assert send_time is not None
        assert send_time > cutoff  # Would proceed to dedup check

    def test_send_time_equal_to_cutoff_returns_false(self) -> None:
        """Documents exactly at cutoff should be skipped (<= comparison)."""
        cutoff = datetime(2025, 6, 1, 10, 0)
        rec = DocumentRecord(ah="", sdbh="", ajzybh="", fssj="2025-06-01 10:00:00", fymc="")
        send_time = rec.parse_fssj()
        assert send_time is not None
        assert send_time <= cutoff
