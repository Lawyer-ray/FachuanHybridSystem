"""Tests for apps.automation.services.document_delivery.query_service DocumentRecord."""

from __future__ import annotations

from apps.automation.services.document_delivery.data_classes import DocumentRecord, DocumentQueryResult


class TestDocumentRecordFromApiResponse:
    def test_from_api_response(self) -> None:
        data = {
            "ah": "（2025）粤0604民初123号",
            "sdbh": "SD001",
            "ajzybh": "AJ001",
            "fssj": "2025-06-10 10:00:00",
            "fymc": "佛山法院",
            "ahdm": "AH001",
            "wsmc": "判决书",
        }
        rec = DocumentRecord.from_api_response(data)
        assert rec.ah == "（2025）粤0604民初123号"
        assert rec.sdbh == "SD001"
        assert rec.wsmc == "判决书"

    def test_from_api_response_missing_fields(self) -> None:
        data: dict = {}
        rec = DocumentRecord.from_api_response(data)
        assert rec.ah == ""
        assert rec.fssj == ""

    def test_parse_fssj_iso_format(self) -> None:
        rec = DocumentRecord(
            ah="", sdbh="", ajzybh="",
            fssj="2025-06-10T10:00:00", fymc="",
        )
        dt = rec.parse_fssj()
        assert dt is not None
        assert dt.year == 2025


class TestDocumentQueryResult:
    def test_defaults(self) -> None:
        r = DocumentQueryResult(
            total_found=10, processed_count=5, skipped_count=3, failed_count=2,
            case_log_ids=["1", "2"], errors=[],
        )
        assert r.total_found == 10
        assert r.processed_count == 5
        assert r.skipped_count == 3
        assert r.failed_count == 2
        assert r.case_log_ids == ["1", "2"]
