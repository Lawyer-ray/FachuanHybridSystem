"""Tests for automation.services.document_delivery.delivery.api_delivery_service — Round 4 deeper coverage.

Covers: download_document flow, download_document with no details, download_document
with missing wjlj, download_document all failures, should_process_document with
aware datetime, create_delivery_record to_dict/from_dict.
"""

from __future__ import annotations

from datetime import datetime
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest

from django.utils import timezone

from apps.automation.services.document_delivery.delivery.api_delivery_service import ApiDeliveryService
from apps.automation.services.document_delivery.data_classes import (
    DocumentDeliveryRecord,
    DocumentRecord,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_record(
    *,
    ah: str = "(2025)粤01民初100号",
    fssj: str = "2025-06-01 10:00:00",
    wsmc: str = "判决书",
    fymc: str = "广州市天河区人民法院",
    sdbh: str = "SD001",
) -> MagicMock:
    record = MagicMock(spec=DocumentRecord)
    record.ah = ah
    record.fssj = fssj
    record.wsmc = wsmc
    record.fymc = fymc
    record.sdbh = sdbh
    record.parse_fssj.return_value = datetime.strptime(fssj, "%Y-%m-%d %H:%M:%S")
    return record


def _make_service(api_client: MagicMock | None = None) -> ApiDeliveryService:
    return ApiDeliveryService(api_client=api_client or MagicMock())


# ---------------------------------------------------------------------------
# download_document — success flow
# ---------------------------------------------------------------------------


class TestDownloadDocument:
    def test_success_downloads_files(self):
        svc = _make_service()

        detail1 = MagicMock()
        detail1.wjlj = "https://example.com/doc1.pdf"
        detail1.c_wsmc = "判决书"
        detail1.c_wjgs = "pdf"

        svc.api_client.fetch_document_details.return_value = [detail1]
        svc.api_client.download_document.return_value = True

        record = _make_record()
        with patch("apps.automation.services.document_delivery.delivery.api_delivery_service.tempfile") as mock_tf:
            mock_tf.mkdtemp.return_value = "/tmp/test_dir"
            with patch("apps.automation.services.document_delivery.delivery.api_delivery_service.Path") as mock_path_cls:
                mock_path = MagicMock()
                mock_path.__truediv__ = MagicMock(return_value="/tmp/test_dir/判决书.pdf")
                mock_path_cls.return_value = mock_path
                result = svc.download_document(record, "tok")

        assert result is not None
        files, temp_dir = result
        assert len(files) == 1
        assert temp_dir == "/tmp/test_dir"

    def test_no_details_returns_none(self):
        svc = _make_service()
        svc.api_client.fetch_document_details.return_value = []

        record = _make_record()
        result = svc.download_document(record, "tok")
        assert result is None

    def test_missing_wjlj_skips_file(self):
        svc = _make_service()

        detail = MagicMock()
        detail.wjlj = ""  # missing download link
        detail.c_wsmc = "判决书"
        detail.c_wjgs = "pdf"

        svc.api_client.fetch_document_details.return_value = [detail]

        record = _make_record()
        with patch("apps.automation.services.document_delivery.delivery.api_delivery_service.tempfile") as mock_tf:
            mock_tf.mkdtemp.return_value = "/tmp/test_dir"
            result = svc.download_document(record, "tok")

        assert result is None  # all files failed

    def test_download_failure_returns_none(self):
        svc = _make_service()

        detail = MagicMock()
        detail.wjlj = "https://example.com/doc.pdf"
        detail.c_wsmc = "判决书"
        detail.c_wjgs = "pdf"

        svc.api_client.fetch_document_details.return_value = [detail]
        svc.api_client.download_document.return_value = False

        record = _make_record()
        with patch("apps.automation.services.document_delivery.delivery.api_delivery_service.tempfile") as mock_tf:
            mock_tf.mkdtemp.return_value = "/tmp/test_dir"
            with patch("apps.automation.services.document_delivery.delivery.api_delivery_service.Path") as mock_path_cls:
                mock_path = MagicMock()
                mock_path.__truediv__ = MagicMock(return_value="/tmp/test_dir/判决书.pdf")
                mock_path_cls.return_value = mock_path
                result = svc.download_document(record, "tok")

        assert result is None

    def test_api_exception_returns_none(self):
        svc = _make_service()
        svc.api_client.fetch_document_details.side_effect = RuntimeError("API error")

        record = _make_record()
        result = svc.download_document(record, "tok")
        assert result is None

    def test_mixed_success_and_failure(self):
        svc = _make_service()

        detail1 = MagicMock()
        detail1.wjlj = "https://example.com/doc1.pdf"
        detail1.c_wsmc = "判决书1"
        detail1.c_wjgs = "pdf"

        detail2 = MagicMock()
        detail2.wjlj = "https://example.com/doc2.pdf"
        detail2.c_wsmc = "判决书2"
        detail2.c_wjgs = "pdf"

        svc.api_client.fetch_document_details.return_value = [detail1, detail2]
        svc.api_client.download_document.side_effect = [True, False]

        record = _make_record()
        with patch("apps.automation.services.document_delivery.delivery.api_delivery_service.tempfile") as mock_tf:
            mock_tf.mkdtemp.return_value = "/tmp/test_dir"
            with patch("apps.automation.services.document_delivery.delivery.api_delivery_service.Path") as mock_path_cls:
                mock_path = MagicMock()
                mock_path.__truediv__ = MagicMock(return_value="/tmp/test_dir/file.pdf")
                mock_path_cls.return_value = mock_path
                result = svc.download_document(record, "tok")

        assert result is not None
        files, _ = result
        assert len(files) == 1


# ---------------------------------------------------------------------------
# should_process_document — aware datetime
# ---------------------------------------------------------------------------


class TestShouldProcessDocumentAware:
    def test_aware_cutoff_with_naive_send_time(self):
        record = _make_record(fssj="2099-01-01 00:00:00")
        cutoff = timezone.now()
        svc = _make_service()
        with patch.object(svc, "_check_not_processed", return_value=True):
            result = svc.should_process_document(record, cutoff, 1)
        assert result is True


# ---------------------------------------------------------------------------
# create_delivery_record — to_dict round trip
# ---------------------------------------------------------------------------


class TestDeliveryRecordRoundTrip:
    def test_to_dict_and_from_dict(self):
        record = DocumentDeliveryRecord(
            case_number="(2025)粤01民初100号",
            send_time=datetime(2025, 6, 1, 10, 0, 0),
            element_index=0,
            document_name="判决书",
            court_name="天河法院",
        )
        d = record.to_dict()
        assert d["case_number"] == "(2025)粤01民初100号"
        assert d["element_index"] == 0
        assert d["document_name"] == "判决书"

        restored = DocumentDeliveryRecord.from_dict(d)
        assert restored.case_number == record.case_number
        assert restored.document_name == record.document_name

    def test_from_dict_with_none_send_time(self):
        d = {
            "case_number": "CN001",
            "send_time": None,
            "element_index": 0,
        }
        restored = DocumentDeliveryRecord.from_dict(d)
        assert restored.send_time is None

    def test_from_dict_with_string_send_time(self):
        d = {
            "case_number": "CN001",
            "send_time": "2025-06-01T10:00:00",
            "element_index": 0,
        }
        restored = DocumentDeliveryRecord.from_dict(d)
        assert restored.send_time is not None
        assert restored.send_time.year == 2025


# ---------------------------------------------------------------------------
# query_documents — exact total = page_size
# ---------------------------------------------------------------------------


class TestQueryDocumentsEdge:
    def test_exact_page_size(self):
        records = [_make_record() for _ in range(20)]
        svc = _make_service()
        svc.api_client.fetch_document_list.return_value = SimpleNamespace(total=20, documents=records)
        result = svc.query_documents(token="tok", cutoff_time=datetime.now(), credential_id=1)
        assert result.total_pages == 1


# ---------------------------------------------------------------------------
# DocumentRecord data class
# ---------------------------------------------------------------------------


class TestDocumentRecordDataClass:
    def test_parse_fssj_valid(self):
        dr = DocumentRecord(
            ah="CN001", sdbh="SD001", ajzybh="AJ001",
            fssj="2025-06-01 10:00:00", fymc="法院",
        )
        result = dr.parse_fssj()
        assert result is not None
        assert result.year == 2025

    def test_parse_fssj_empty(self):
        dr = DocumentRecord(
            ah="CN001", sdbh="SD001", ajzybh="AJ001",
            fssj="", fymc="法院",
        )
        assert dr.parse_fssj() is None

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
        }
        dr = DocumentRecord.from_api_response(data)
        assert dr.ah == "CN001"
        assert dr.sdbh == "SD001"

    def test_to_dict(self):
        dr = DocumentRecord(
            ah="CN001", sdbh="SD001", ajzybh="AJ001",
            fssj="2025-06-01 10:00:00", fymc="法院",
        )
        d = dr.to_dict()
        assert d["ah"] == "CN001"
        assert d["fymc"] == "法院"
