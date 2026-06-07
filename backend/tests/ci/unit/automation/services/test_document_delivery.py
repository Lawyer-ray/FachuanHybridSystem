"""Tests for document delivery services."""

from datetime import datetime
from unittest.mock import MagicMock, patch

import pytest


# ============================================================
# api_delivery_service.py - create_delivery_record
# ============================================================

class TestCreateDeliveryRecord:
    def _make_service(self):
        from apps.automation.services.document_delivery.delivery.api_delivery_service import ApiDeliveryService
        svc = ApiDeliveryService.__new__(ApiDeliveryService)
        svc.api_client = MagicMock()
        return svc

    def test_with_none_fssj_uses_now(self):
        svc = self._make_service()
        record = MagicMock()
        record.parse_fssj.return_value = None
        record.ah = "test_case"
        record.wsmc = "test_doc"
        record.fymc = "test_court"
        with patch("django.utils.timezone.now", return_value=datetime(2025, 6, 1)):
            result = svc.create_delivery_record(record)
            assert result.case_number == "test_case"
            assert result.document_name == "test_doc"
            assert result.court_name == "test_court"


# ============================================================
# playwright_delivery_service.py - _parse_send_time
# ============================================================

class TestPlaywrightParseSendTime:
    def _make_service(self):
        from apps.automation.services.document_delivery.delivery.playwright_delivery_service import (
            PlaywrightDeliveryService,
        )
        return PlaywrightDeliveryService()

    def test_parse_valid_time(self):
        svc = self._make_service()
        with patch("django.utils.timezone.make_aware", return_value=datetime(2025, 6, 1, 10, 30, 0)):
            result = svc._parse_send_time("2025-06-01 10:30:00", 0)
            assert result is not None

    def test_parse_empty_returns_none(self):
        svc = self._make_service()
        assert svc._parse_send_time("", 0) is None

    def test_parse_label_text_returns_none(self):
        svc = self._make_service()
        assert svc._parse_send_time("发送时间", 0) is None

    def test_parse_invalid_format_returns_none(self):
        svc = self._make_service()
        assert svc._parse_send_time("invalid", 0) is None

    def test_parse_no_seconds_returns_none(self):
        svc = self._make_service()
        assert svc._parse_send_time("2025-06-01 10:30", 0) is None


# ============================================================
# playwright_delivery_service.py - _extract_single_entry
# ============================================================

class TestExtractSingleEntry:
    def _make_service(self):
        from apps.automation.services.document_delivery.delivery.playwright_delivery_service import (
            PlaywrightDeliveryService,
        )
        return PlaywrightDeliveryService()

    def test_complete_entry(self):
        svc = self._make_service()
        case_el = MagicMock()
        case_el.inner_text.return_value = "(2025)粤01民初123号"
        time_el = MagicMock()
        time_el.inner_text.return_value = "2025-06-01 10:30:00"
        with patch("django.utils.timezone.make_aware", return_value=datetime(2025, 6, 1, 10, 30, 0)):
            result = svc._extract_single_entry(0, [case_el], [time_el])
            assert result is not None
            assert result.case_number == "(2025)粤01民初123号"

    def test_header_text_skipped(self):
        svc = self._make_service()
        case_el = MagicMock()
        case_el.inner_text.return_value = "案号"
        time_el = MagicMock()
        time_el.inner_text.return_value = "发送时间"
        result = svc._extract_single_entry(0, [case_el], [time_el])
        assert result is None


# ============================================================
# document_delivery_processor.py - extract_zip_if_needed
# ============================================================

class TestExtractZipIfNeeded:
    def _make_processor(self):
        from apps.automation.services.document_delivery.processor.document_delivery_processor import (
            DocumentDeliveryProcessor,
        )
        return DocumentDeliveryProcessor.__new__(DocumentDeliveryProcessor)

    def test_non_zip_returns_none(self):
        proc = self._make_processor()
        assert proc.extract_zip_if_needed("/tmp/test.pdf") is None

    def test_non_zip_doc_returns_none(self):
        proc = self._make_processor()
        assert proc.extract_zip_if_needed("/tmp/test.docx") is None
