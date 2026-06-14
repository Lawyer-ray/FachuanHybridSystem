"""Tests for apps.automation.services.document_delivery.data_classes."""
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


class TestDocumentRecord:
    def test_from_api_response(self) -> None:
        data = {"ah": "案号1", "sdbh": "s1", "ajzybh": "aj1", "fssj": "2025-06-15 10:00:00", "fymc": "法院"}
        rec = DocumentRecord.from_api_response(data)
        assert rec.ah == "案号1"
        assert rec.sdbh == "s1"

    def test_parse_fssj_valid(self) -> None:
        rec = DocumentRecord(ah="", sdbh="", ajzybh="", fssj="2025-06-15 10:00:00", fymc="")
        dt = rec.parse_fssj()
        assert dt is not None
        assert dt.year == 2025
        assert dt.hour == 10

    def test_parse_fssj_iso_format(self) -> None:
        rec = DocumentRecord(ah="", sdbh="", ajzybh="", fssj="2025-06-15T10:00:00", fymc="")
        dt = rec.parse_fssj()
        assert dt is not None

    def test_parse_fssj_empty(self) -> None:
        rec = DocumentRecord(ah="", sdbh="", ajzybh="", fssj="", fymc="")
        assert rec.parse_fssj() is None

    def test_parse_fssj_invalid(self) -> None:
        rec = DocumentRecord(ah="", sdbh="", ajzybh="", fssj="not-a-date", fymc="")
        assert rec.parse_fssj() is None

    def test_to_dict(self) -> None:
        rec = DocumentRecord(ah="a", sdbh="b", ajzybh="c", fssj="d", fymc="e")
        d = rec.to_dict()
        assert d["ah"] == "a"
        assert d["fymc"] == "e"


class TestDocumentDetail:
    def test_from_api_response(self) -> None:
        data = {"c_sdbh": "s1", "c_wsmc": "w1", "c_wjgs": "pdf", "wjlj": "http://url"}
        detail = DocumentDetail.from_api_response(data)
        assert detail.c_sdbh == "s1"
        assert detail.wjlj == "http://url"

    def test_to_dict(self) -> None:
        detail = DocumentDetail(c_sdbh="s", c_wsmc="w", c_wjgs="pdf", wjlj="url")
        d = detail.to_dict()
        assert d["c_sdbh"] == "s"


class TestDocumentListResponse:
    def test_from_api_response(self) -> None:
        data = {
            "data": {
                "total": 5,
                "data": [
                    {"ah": "a1", "sdbh": "s1", "ajzybh": "", "fssj": "", "fymc": ""},
                    {"ah": "a2", "sdbh": "s2", "ajzybh": "", "fssj": "", "fymc": ""},
                ],
            }
        }
        resp = DocumentListResponse.from_api_response(data)
        assert resp.total == 5
        assert len(resp.documents) == 2

    def test_from_api_response_empty(self) -> None:
        resp = DocumentListResponse.from_api_response({})
        assert resp.total == 0
        assert resp.documents == []


class TestDocumentDeliveryRecord:
    def test_to_dict(self) -> None:
        record = DocumentDeliveryRecord(
            case_number="C1",
            send_time=datetime(2025, 6, 15, 10, 0),
            element_index=0,
        )
        d = record.to_dict()
        assert d["case_number"] == "C1"
        assert d["send_time"] == "2025-06-15T10:00:00"

    def test_to_dict_no_send_time(self) -> None:
        record = DocumentDeliveryRecord(case_number="C1", send_time=None, element_index=0)
        d = record.to_dict()
        assert d["send_time"] is None

    def test_from_dict(self) -> None:
        data = {
            "case_number": "C1",
            "send_time": "2025-06-15T10:00:00",
            "element_index": 0,
        }
        rec = DocumentDeliveryRecord.from_dict(data)
        assert rec.case_number == "C1"
        assert rec.send_time is not None

    def test_from_dict_no_send_time(self) -> None:
        data = {"case_number": "C1", "element_index": 0}
        rec = DocumentDeliveryRecord.from_dict(data)
        assert rec.send_time is None

    def test_from_dict_with_datetime(self) -> None:
        dt = datetime(2025, 1, 1)
        data = {"case_number": "C1", "send_time": dt, "element_index": 0}
        rec = DocumentDeliveryRecord.from_dict(data)
        assert rec.send_time is dt


class TestDataclassesDefaults:
    def test_query_result(self) -> None:
        r = DocumentQueryResult(total_found=1, processed_count=1, skipped_count=0, failed_count=0, case_log_ids=[], errors=[])
        assert r.total_found == 1

    def test_process_result(self) -> None:
        r = DocumentProcessResult(success=True, case_id=1, case_log_id=2, renamed_path="/x", notification_sent=True, error_message=None)
        assert r.success is True
