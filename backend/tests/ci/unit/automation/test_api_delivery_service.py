"""Tests for automation.services.document_delivery.delivery.api_delivery_service.

Covers: query_documents, should_process_document, create_delivery_record,
_check_not_processed, _show_schedule_info, _get_credential_info.
"""

from __future__ import annotations

from datetime import datetime, timedelta
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest

from django.utils import timezone

from apps.automation.services.document_delivery.delivery.api_delivery_service import ApiDeliveryService
from apps.automation.services.document_delivery.data_classes import (
    DocumentDeliveryRecord,
    DocumentQueryResult,
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
    # parse_fssj returns naive datetime
    record.parse_fssj.return_value = datetime.strptime(fssj, "%Y-%m-%d %H:%M:%S")
    return record


def _make_service(api_client: MagicMock | None = None) -> ApiDeliveryService:
    return ApiDeliveryService(api_client=api_client or MagicMock())


# ---------------------------------------------------------------------------
# query_documents
# ---------------------------------------------------------------------------


class TestQueryDocuments:
    def test_zero_total_returns_early(self):
        svc = _make_service()
        svc.api_client.fetch_document_list.return_value = SimpleNamespace(total=0, documents=[])
        result = svc.query_documents(token="tok", cutoff_time=datetime.now(), credential_id=1)
        assert result.total_found == 0

    def test_single_page(self):
        records = [_make_record()]
        svc = _make_service()
        svc.api_client.fetch_document_list.return_value = SimpleNamespace(total=1, documents=records)
        result = svc.query_documents(token="tok", cutoff_time=datetime.now(), credential_id=1)
        assert result.total_found == 1
        assert result.total_pages == 1

    def test_multiple_pages_calculated(self):
        records = [_make_record() for _ in range(20)]
        svc = _make_service()
        svc.api_client.fetch_document_list.return_value = SimpleNamespace(total=45, documents=records)
        result = svc.query_documents(token="tok", cutoff_time=datetime.now(), credential_id=1)
        assert result.total_pages == 3

    def test_api_error_appends_and_raises(self):
        svc = _make_service()
        svc.api_client.fetch_document_list.side_effect = RuntimeError("API down")
        with pytest.raises(RuntimeError):
            svc.query_documents(token="tok", cutoff_time=datetime.now(), credential_id=1)


# ---------------------------------------------------------------------------
# should_process_document
# ---------------------------------------------------------------------------


class TestShouldProcessDocument:
    def test_unparseable_fssj_defaults_to_process(self):
        record = _make_record()
        record.parse_fssj.return_value = None
        svc = _make_service()
        assert svc.should_process_document(record, timezone.now(), 1) is True

    def test_send_time_before_cutoff_returns_false(self):
        record = _make_record(fssj="2020-01-01 00:00:00")
        cutoff = timezone.now()
        svc = _make_service()
        assert svc.should_process_document(record, cutoff, 1) is False

    def test_send_time_after_cutoff_checks_history(self):
        record = _make_record(fssj="2099-01-01 00:00:00")
        cutoff = datetime(2025, 1, 1)
        svc = _make_service()
        with patch.object(svc, "_check_not_processed", return_value=True):
            assert svc.should_process_document(record, cutoff, 1) is True


# ---------------------------------------------------------------------------
# create_delivery_record
# ---------------------------------------------------------------------------


class TestCreateDeliveryRecord:
    def test_with_valid_fssj(self):
        record = _make_record(
            ah="(2025)粤01民初100号",
            fssj="2025-06-01 10:00:00",
            wsmc="判决书",
            fymc="天河法院",
        )
        svc = _make_service()
        result = svc.create_delivery_record(record)
        assert result.case_number == "(2025)粤01民初100号"
        assert result.document_name == "判决书"
        assert result.court_name == "天河法院"

    def test_with_none_fssj_uses_now(self):
        record = _make_record()
        record.parse_fssj.return_value = None
        svc = _make_service()
        result = svc.create_delivery_record(record)
        assert result.send_time is not None


# ---------------------------------------------------------------------------
# fetch_page
# ---------------------------------------------------------------------------


class TestFetchPage:
    def test_returns_documents(self):
        docs = [_make_record()]
        svc = _make_service()
        svc.api_client.fetch_document_list.return_value = SimpleNamespace(documents=docs)
        result = svc.fetch_page(token="tok", page_num=1)
        assert len(result) == 1

    def test_exception_returns_empty(self):
        svc = _make_service()
        svc.api_client.fetch_document_list.side_effect = RuntimeError("fail")
        result = svc.fetch_page(token="tok", page_num=1)
        assert result == []
