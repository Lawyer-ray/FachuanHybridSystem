"""document_delivery 相关模块单元测试。"""

from __future__ import annotations

import tempfile
import zipfile
from datetime import datetime, timezone as tz, UTC
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest

from apps.automation.services.document_delivery.data_classes import (
    DocumentDeliveryRecord,
    DocumentProcessResult,
    DocumentQueryResult,
)


class TestDocumentDeliveryRecord:

    def test_creation(self):
        record = DocumentDeliveryRecord(
            case_number="(2024)粤01民初100号",
            send_time=datetime(2024, 1, 15, tzinfo=UTC),
            element_index=0,
            document_name="判决书",
            court_name="广州市中级人民法院",
            delivery_event_id="evt_123",
        )
        assert record.case_number == "(2024)粤01民初100号"
        assert record.document_name == "判决书"
        assert record.delivery_event_id == "evt_123"


class TestDocumentProcessResult:

    def test_default_values(self):
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

    def test_success_result(self):
        result = DocumentProcessResult(
            success=True,
            case_id=1,
            case_log_id=10,
            renamed_path="/tmp/renamed.pdf",
            notification_sent=True,
            error_message=None,
        )
        assert result.success is True
        assert result.case_id == 1


class TestDocumentQueryResult:

    def test_defaults(self):
        result = DocumentQueryResult(
            total_found=0,
            processed_count=0,
            skipped_count=0,
            failed_count=0,
            case_log_ids=[],
            errors=[],
        )
        assert result.total_found == 0
        assert result.errors == []

    def test_with_data(self):
        result = DocumentQueryResult(
            total_found=10,
            processed_count=8,
            skipped_count=1,
            failed_count=1,
            case_log_ids=[1, 2, 3],
            errors=["some error"],
        )
        assert result.total_found == 10
        assert len(result.case_log_ids) == 3


class TestDocumentProcessorExtractZip:

    def test_non_zip_returns_none(self):
        from apps.automation.services.document_delivery.delivery.document_processor import DocumentProcessor
        proc = DocumentProcessor()
        assert proc.extract_zip_if_needed("/tmp/test.pdf") is None

    def test_zip_extracts_files(self):
        from apps.automation.services.document_delivery.delivery.document_processor import DocumentProcessor
        proc = DocumentProcessor()
        with tempfile.NamedTemporaryFile(suffix=".zip", delete=False) as f:
            zip_path = f.name
        with zipfile.ZipFile(zip_path, "w") as zf:
            zf.writestr("test1.pdf", b"content1")
            zf.writestr("test2.pdf", b"content2")
        result = proc.extract_zip_if_needed(zip_path)
        assert result is not None
        assert len(result) == 2
        # cleanup
        Path(zip_path).unlink(missing_ok=True)
        for f in result:
            Path(f).unlink(missing_ok=True)

    def test_invalid_zip_returns_none(self):
        from apps.automation.services.document_delivery.delivery.document_processor import DocumentProcessor
        proc = DocumentProcessor()
        with tempfile.NamedTemporaryFile(suffix=".zip", delete=False) as f:
            f.write(b"not a zip")
            zip_path = f.name
        assert proc.extract_zip_if_needed(zip_path) is None
        Path(zip_path).unlink(missing_ok=True)


class TestDocumentDeliveryProcessorExtractZip:

    def test_non_zip_returns_none(self):
        from apps.automation.services.document_delivery.processor.document_delivery_processor import DocumentDeliveryProcessor
        proc = DocumentDeliveryProcessor()
        assert proc.extract_zip_if_needed("/tmp/test.pdf") is None

    def test_zip_extracts_files(self):
        from apps.automation.services.document_delivery.processor.document_delivery_processor import DocumentDeliveryProcessor
        proc = DocumentDeliveryProcessor()
        with tempfile.NamedTemporaryFile(suffix=".zip", delete=False) as f:
            zip_path = f.name
        with zipfile.ZipFile(zip_path, "w") as zf:
            zf.writestr("a.pdf", b"data")
        result = proc.extract_zip_if_needed(zip_path)
        assert result is not None
        assert len(result) >= 1
        Path(zip_path).unlink(missing_ok=True)

    def test_sync_case_number_skips_existing(self):
        from apps.automation.services.document_delivery.processor.document_delivery_processor import DocumentDeliveryProcessor
        proc = DocumentDeliveryProcessor()
        num = SimpleNamespace(number="(2024)粤01民初100号")
        cn_service = MagicMock()
        cn_service.list_numbers_internal.return_value = [num]
        proc._case_number_service = cn_service
        result = proc.sync_case_number_to_case(1, "(2024)粤01民初100号")
        assert result is True
        cn_service.create_number_internal.assert_not_called()

    def test_send_notification_returns_false_when_no_case(self):
        from apps.automation.services.document_delivery.processor.document_delivery_processor import DocumentDeliveryProcessor
        proc = DocumentDeliveryProcessor()
        sms = SimpleNamespace(id=1, case=None, notification_results=None)
        assert proc.send_notification(sms, []) is False


class TestDocumentDeliveryServiceShouldProcess:

    def test_should_process_returns_false_when_old(self):
        from apps.automation.services.document_delivery.document_delivery_service import DocumentDeliveryService
        svc = DocumentDeliveryService()
        record = DocumentDeliveryRecord(
            case_number="test",
            send_time=datetime(2020, 1, 1, tzinfo=UTC),
            element_index=0,
            document_name="test",
            court_name="test",
            delivery_event_id="test",
        )
        cutoff = datetime(2024, 1, 1, tzinfo=UTC)
        assert svc._should_process(record, cutoff, 1) is False

    def test_should_process_returns_false_when_none_time(self):
        from apps.automation.services.document_delivery.document_delivery_service import DocumentDeliveryService
        svc = DocumentDeliveryService()
        record = DocumentDeliveryRecord(
            case_number="test",
            send_time=None,
            element_index=0,
            document_name="test",
            court_name="test",
            delivery_event_id="test",
        )
        cutoff = datetime(2024, 1, 1, tzinfo=UTC)
        assert svc._should_process(record, cutoff, 1) is False
