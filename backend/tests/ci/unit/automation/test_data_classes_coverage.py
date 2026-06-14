"""Tests for automation.services.document_delivery.data_classes — coverage boost.

Covers: DocumentRecord parse_fssj/from_api_response/to_dict, DocumentDetail
from_api_response/to_dict, DocumentListResponse from_api_response/to_dict,
DocumentDeliveryRecord to_dict/from_dict, DocumentQueryResult,
DocumentProcessResult.
"""

from __future__ import annotations

from datetime import datetime

import pytest

from apps.automation.services.document_delivery.data_classes import (
    DocumentDeliveryRecord,
    DocumentDetail,
    DocumentListResponse,
    DocumentProcessResult,
    DocumentQueryResult,
    DocumentRecord,
)


# ---------------------------------------------------------------------------
# DocumentRecord
# ---------------------------------------------------------------------------


class TestDocumentRecord:
    def test_parse_fssj_valid(self):
        dr = DocumentRecord(
            ah="CN001", sdbh="SD001", ajzybh="AJ001",
            fssj="2025-06-01 10:00:00", fymc="法院",
        )
        result = dr.parse_fssj()
        assert result is not None
        assert result.year == 2025
        assert result.month == 6

    def test_parse_fssj_empty(self):
        dr = DocumentRecord(
            ah="CN001", sdbh="SD001", ajzybh="AJ001",
            fssj="", fymc="法院",
        )
        assert dr.parse_fssj() is None

    def test_parse_fssj_none(self):
        dr = DocumentRecord(
            ah="CN001", sdbh="SD001", ajzybh="AJ001",
            fssj="", fymc="法院",
        )
        assert dr.parse_fssj() is None

    def test_parse_fssj_iso_format(self):
        dr = DocumentRecord(
            ah="CN001", sdbh="SD001", ajzybh="AJ001",
            fssj="2025-06-01T10:00:00", fymc="法院",
        )
        result = dr.parse_fssj()
        assert result is not None
        assert result.year == 2025

    def test_parse_fssj_invalid(self):
        dr = DocumentRecord(
            ah="CN001", sdbh="SD001", ajzybh="AJ001",
            fssj="not-a-date", fymc="法院",
        )
        assert dr.parse_fssj() is None

    def test_from_api_response(self):
        data = {
            "ah": "CN001", "sdbh": "SD001", "ajzybh": "AJ001",
            "fssj": "2025-06-01 10:00:00", "fymc": "法院",
            "ahdm": "AH001", "fybh": "FY001",
            "ssdrxm": "张三", "ssdrsjhm": "13800138000", "ssdrzjhm": "110101",
            "wsmc": "判决书", "sdzt": "1", "qdzt": "1", "qdbh": "QD001",
            "fqr": "FQ001", "cjsj": "2025-06-01", "zhxgsj": "2025-06-02",
        }
        dr = DocumentRecord.from_api_response(data)
        assert dr.ah == "CN001"
        assert dr.sdbh == "SD001"
        assert dr.wsmc == "判决书"
        assert dr.ahdm == "AH001"

    def test_from_api_response_defaults(self):
        data = {}
        dr = DocumentRecord.from_api_response(data)
        assert dr.ah == ""
        assert dr.sdbh == ""

    def test_to_dict(self):
        dr = DocumentRecord(
            ah="CN001", sdbh="SD001", ajzybh="AJ001",
            fssj="2025-06-01 10:00:00", fymc="法院",
            wsmc="判决书",
        )
        d = dr.to_dict()
        assert d["ah"] == "CN001"
        assert d["wsmc"] == "判决书"
        assert len(d) == 17  # all fields


# ---------------------------------------------------------------------------
# DocumentDetail
# ---------------------------------------------------------------------------


class TestDocumentDetail:
    def test_from_api_response(self):
        data = {
            "c_sdbh": "SD001", "c_wsmc": "判决书", "c_wjgs": "pdf",
            "wjlj": "https://example.com/doc.pdf",
            "c_stbh": "ST001", "c_wsbh": "WS001", "c_fybh": "FY001",
            "c_fymc": "法院", "dt_cjsj": "2025-06-01",
        }
        dd = DocumentDetail.from_api_response(data)
        assert dd.c_sdbh == "SD001"
        assert dd.wjlj == "https://example.com/doc.pdf"

    def test_from_api_response_defaults(self):
        data = {}
        dd = DocumentDetail.from_api_response(data)
        assert dd.c_sdbh == ""
        assert dd.wjlj == ""

    def test_to_dict(self):
        dd = DocumentDetail(
            c_sdbh="SD001", c_wsmc="判决书", c_wjgs="pdf",
            wjlj="https://example.com/doc.pdf",
        )
        d = dd.to_dict()
        assert d["c_sdbh"] == "SD001"
        assert d["wjlj"] == "https://example.com/doc.pdf"


# ---------------------------------------------------------------------------
# DocumentListResponse
# ---------------------------------------------------------------------------


class TestDocumentListResponse:
    def test_from_api_response(self):
        data = {
            "data": {
                "total": 2,
                "data": [
                    {"ah": "CN001", "sdbh": "SD001", "ajzybh": "AJ001", "fssj": "", "fymc": "F1"},
                    {"ah": "CN002", "sdbh": "SD002", "ajzybh": "AJ002", "fssj": "", "fymc": "F2"},
                ],
            }
        }
        resp = DocumentListResponse.from_api_response(data)
        assert resp.total == 2
        assert len(resp.documents) == 2

    def test_from_api_response_empty(self):
        data = {}
        resp = DocumentListResponse.from_api_response(data)
        assert resp.total == 0
        assert resp.documents == []

    def test_to_dict(self):
        resp = DocumentListResponse(
            total=1,
            documents=[DocumentRecord(ah="CN001", sdbh="SD001", ajzybh="AJ001", fssj="", fymc="F")],
        )
        d = resp.to_dict()
        assert d["total"] == 1
        assert len(d["documents"]) == 1


# ---------------------------------------------------------------------------
# DocumentDeliveryRecord
# ---------------------------------------------------------------------------


class TestDocumentDeliveryRecord:
    def test_to_dict_with_time(self):
        rec = DocumentDeliveryRecord(
            case_number="CN001", send_time=datetime(2025, 6, 1, 10, 0, 0),
            element_index=0, document_name="判决书", court_name="法院",
        )
        d = rec.to_dict()
        assert d["case_number"] == "CN001"
        assert d["send_time"] is not None
        assert d["element_index"] == 0

    def test_to_dict_none_time(self):
        rec = DocumentDeliveryRecord(
            case_number="CN001", send_time=None, element_index=0,
        )
        d = rec.to_dict()
        assert d["send_time"] is None

    def test_from_dict_with_string_time(self):
        d = {
            "case_number": "CN001",
            "send_time": "2025-06-01T10:00:00",
            "element_index": 0,
        }
        rec = DocumentDeliveryRecord.from_dict(d)
        assert rec.send_time is not None
        assert rec.send_time.year == 2025

    def test_from_dict_with_none_time(self):
        d = {"case_number": "CN001", "send_time": None, "element_index": 0}
        rec = DocumentDeliveryRecord.from_dict(d)
        assert rec.send_time is None

    def test_from_dict_with_datetime_time(self):
        d = {
            "case_number": "CN001",
            "send_time": datetime(2025, 6, 1),
            "element_index": 0,
        }
        rec = DocumentDeliveryRecord.from_dict(d)
        assert rec.send_time.year == 2025

    def test_from_dict_with_optional_fields(self):
        d = {
            "case_number": "CN001",
            "send_time": None,
            "element_index": 0,
            "document_name": "判决书",
            "court_name": "法院",
            "delivery_event_id": "EVT001",
        }
        rec = DocumentDeliveryRecord.from_dict(d)
        assert rec.document_name == "判决书"
        assert rec.court_name == "法院"
        assert rec.delivery_event_id == "EVT001"


# ---------------------------------------------------------------------------
# DocumentQueryResult
# ---------------------------------------------------------------------------


class TestDocumentQueryResult:
    def test_creation(self):
        r = DocumentQueryResult(
            total_found=10, processed_count=5, skipped_count=3,
            failed_count=2, case_log_ids=[1, 2], errors=["err1"],
        )
        assert r.total_found == 10
        assert r.processed_count == 5
        assert r.skipped_count == 3
        assert r.failed_count == 2


# ---------------------------------------------------------------------------
# DocumentProcessResult
# ---------------------------------------------------------------------------


class TestDocumentProcessResult:
    def test_creation(self):
        r = DocumentProcessResult(
            success=True, case_id=1, case_log_id=2,
            renamed_path="/tmp/doc.pdf", notification_sent=True,
            error_message=None,
        )
        assert r.success is True
        assert r.case_id == 1
        assert r.notification_sent is True
