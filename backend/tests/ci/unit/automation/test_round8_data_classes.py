"""Tests for DocumentRecord data class (from_api_response, parse_fssj, to_dict)."""

from __future__ import annotations

from datetime import datetime

import pytest

from apps.automation.services.document_delivery.data_classes import (
    DocumentRecord,
    DocumentDetail,
    DocumentListResponse,
    DocumentDeliveryRecord,
)


class TestDocumentRecord:
    def test_from_api_response(self):
        data = {
            "ah": "（2025）粤0604民初41257号",
            "sdbh": "sd_001",
            "ajzybh": "aj_001",
            "fssj": "2025-12-10 16:25:37",
            "fymc": "佛山市禅城区人民法院",
        }
        record = DocumentRecord.from_api_response(data)
        assert record.ah == "（2025）粤0604民初41257号"
        assert record.sdbh == "sd_001"
        assert record.fymc == "佛山市禅城区人民法院"

    def test_parse_fssj_valid(self):
        record = DocumentRecord(ah="", sdbh="", ajzybh="", fssj="2025-01-15 10:30:00", fymc="")
        result = record.parse_fssj()
        assert result is not None
        assert result.year == 2025
        assert result.month == 1

    def test_parse_fssj_iso(self):
        record = DocumentRecord(ah="", sdbh="", ajzybh="", fssj="2025-01-15T10:30:00", fymc="")
        result = record.parse_fssj()
        assert result is not None

    def test_parse_fssj_empty(self):
        record = DocumentRecord(ah="", sdbh="", ajzybh="", fssj="", fymc="")
        assert record.parse_fssj() is None

    def test_parse_fssj_invalid(self):
        record = DocumentRecord(ah="", sdbh="", ajzybh="", fssj="not-a-date", fymc="")
        assert record.parse_fssj() is None

    def test_to_dict(self):
        record = DocumentRecord(ah="test", sdbh="sd", ajzybh="aj", fssj="2025-01-01", fymc="court")
        d = record.to_dict()
        assert d["ah"] == "test"
        assert d["fymc"] == "court"


class TestDocumentDetail:
    def test_from_api_response(self):
        data = {
            "c_sdbh": "sd_001",
            "c_wsmc": "判决书",
            "c_wjgs": "pdf",
            "wjlj": "https://example.com/file.pdf",
        }
        detail = DocumentDetail.from_api_response(data)
        assert detail.c_sdbh == "sd_001"
        assert detail.wjlj == "https://example.com/file.pdf"

    def test_to_dict(self):
        detail = DocumentDetail(c_sdbh="sd", c_wsmc="判决书", c_wjgs="pdf", wjlj="url")
        d = detail.to_dict()
        assert d["c_sdbh"] == "sd"
        assert d["wjlj"] == "url"


class TestDocumentListResponse:
    def test_from_api_response(self):
        data = {
            "data": {
                "total": 2,
                "data": [
                    {"ah": "case1", "sdbh": "sd1", "ajzybh": "aj1", "fssj": "2025-01-01", "fymc": "court"},
                    {"ah": "case2", "sdbh": "sd2", "ajzybh": "aj2", "fssj": "2025-01-02", "fymc": "court2"},
                ],
            }
        }
        resp = DocumentListResponse.from_api_response(data)
        assert resp.total == 2
        assert len(resp.documents) == 2

    def test_from_api_response_empty(self):
        data = {"data": {"total": 0, "data": []}}
        resp = DocumentListResponse.from_api_response(data)
        assert resp.total == 0
        assert len(resp.documents) == 0

    def test_to_dict(self):
        resp = DocumentListResponse(total=1, documents=[
            DocumentRecord(ah="case1", sdbh="sd1", ajzybh="aj1", fssj="2025-01-01", fymc="court"),
        ])
        d = resp.to_dict()
        assert d["total"] == 1
        assert len(d["documents"]) == 1


class TestDocumentDeliveryRecord:
    def test_basic(self):
        record = DocumentDeliveryRecord(
            case_number="2025-粤01民初1号",
            send_time=datetime(2025, 1, 15, 10, 0, 0),
            element_index=0,
            document_name="判决书",
            court_name="广州市法院",
            delivery_event_id="evt_123",
        )
        assert record.case_number == "2025-粤01民初1号"
        assert record.delivery_event_id == "evt_123"

    def test_to_dict(self):
        record = DocumentDeliveryRecord(
            case_number="2025-粤01民初1号",
            send_time=datetime(2025, 1, 15, 10, 0, 0),
            element_index=0,
        )
        d = record.to_dict()
        assert d["case_number"] == "2025-粤01民初1号"
        assert d["send_time"] is not None

    def test_to_dict_no_send_time(self):
        record = DocumentDeliveryRecord(
            case_number="test",
            send_time=None,
            element_index=0,
        )
        d = record.to_dict()
        assert d["send_time"] is None
