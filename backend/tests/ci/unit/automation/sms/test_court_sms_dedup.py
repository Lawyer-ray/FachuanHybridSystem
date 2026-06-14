"""Tests for apps.automation.services.sms.court_sms_dedup_service."""
from __future__ import annotations

import hashlib
import json
from datetime import datetime
from unittest.mock import MagicMock, patch

import pytest

from apps.automation.services.document_delivery.data_classes import DocumentDeliveryRecord
from apps.automation.services.sms.court_sms_dedup_service import (
    CourtSMSDedupIdentity,
    CourtSMSDedupResult,
    CourtSMSDedupService,
)


class TestCourtSMSDedupIdentity:
    def test_frozen(self) -> None:
        identity = CourtSMSDedupIdentity(event_id="e1", event_key="k1", canonical_payload="p")
        assert identity.event_id == "e1"
        with pytest.raises(AttributeError):
            identity.event_id = "e2"  # type: ignore[misc]

    def test_default_uses_fallback(self) -> None:
        identity = CourtSMSDedupIdentity(event_id=None, event_key=None, canonical_payload=None)
        assert identity.uses_fallback is False


class TestCourtSMSDedupServiceIdentity:
    def setup_method(self) -> None:
        self.svc = CourtSMSDedupService()

    def test_build_identity_with_event_id(self) -> None:
        record = DocumentDeliveryRecord(
            case_number="C123",
            send_time=datetime(2025, 1, 1),
            element_index=0,
            delivery_event_id="evt-001",
        )
        identity = self.svc.build_document_delivery_identity(record)
        assert identity.event_id == "evt-001"
        assert identity.event_key is not None
        assert identity.uses_fallback is False

    def test_build_identity_fallback_no_event_id(self) -> None:
        record = DocumentDeliveryRecord(
            case_number="C123",
            send_time=datetime(2025, 1, 1),
            element_index=0,
            delivery_event_id="",
        )
        identity = self.svc.build_document_delivery_identity(record)
        assert identity.event_id is None
        assert identity.event_key is not None
        assert identity.uses_fallback is True

    def test_build_identity_no_fallback_data(self) -> None:
        record = DocumentDeliveryRecord(
            case_number="",
            send_time=None,
            element_index=0,
            delivery_event_id="",
        )
        identity = self.svc.build_document_delivery_identity(record)
        assert identity.event_id is None
        assert identity.event_key is None

    def test_normalize_text(self) -> None:
        assert self.svc._normalize_text("  hello   world  ") == "hello world"
        assert self.svc._normalize_text(None) == ""
        assert self.svc._normalize_text("") == ""

    def test_hash_payload_consistent(self) -> None:
        payload = '{"key":"value"}'
        h1 = self.svc._hash_payload(payload)
        h2 = self.svc._hash_payload(payload)
        assert h1 == h2
        assert h1 == hashlib.sha256(payload.encode("utf-8")).hexdigest()

    def test_normalize_send_time(self) -> None:
        from django.utils import timezone

        dt = datetime(2025, 6, 15, 10, 30, 0)
        result = self.svc._normalize_send_time(dt)
        assert "2025" in result
        assert "10:30" in result


class TestCourtSMSDedupServiceSkipCheck:
    def setup_method(self) -> None:
        self.svc = CourtSMSDedupService()

    @patch.object(CourtSMSDedupService, "_find_existing_by_event_key")
    def test_should_skip_returns_true_when_exists(self, mock_find: MagicMock) -> None:
        mock_find.return_value = MagicMock()
        record = DocumentDeliveryRecord(
            case_number="C1",
            send_time=datetime(2025, 1, 1),
            element_index=0,
            delivery_event_id="evt-1",
        )
        should_skip, sms = self.svc.should_skip_document_delivery(record)
        assert should_skip is True
        assert sms is not None

    @patch.object(CourtSMSDedupService, "_find_existing_by_event_key")
    def test_should_skip_returns_false_when_not_exists(self, mock_find: MagicMock) -> None:
        mock_find.return_value = None
        record = DocumentDeliveryRecord(
            case_number="C1",
            send_time=datetime(2025, 1, 1),
            element_index=0,
            delivery_event_id="evt-1",
        )
        should_skip, sms = self.svc.should_skip_document_delivery(record)
        assert should_skip is False
        assert sms is None


class TestBuildExistingSmsResult:
    def test_with_notification(self) -> None:
        svc = CourtSMSDedupService()
        sms = MagicMock()
        sms.notification_results = {"feishu": {"success": True}}
        sms.feishu_sent_at = None
        result = svc.build_existing_sms_result(sms, "/path/file.pdf")
        assert result["success"] is True
        assert result["deduplicated"] is True
        assert result["notification_sent"] is True

    def test_with_feishu_sent_at(self) -> None:
        svc = CourtSMSDedupService()
        sms = MagicMock()
        sms.notification_results = {}
        sms.feishu_sent_at = datetime.now()
        result = svc.build_existing_sms_result(sms, "/path/file.pdf")
        assert result["notification_sent"] is True

    def test_no_notification(self) -> None:
        svc = CourtSMSDedupService()
        sms = MagicMock()
        sms.notification_results = {}
        sms.feishu_sent_at = None
        result = svc.build_existing_sms_result(sms, "/path/file.pdf")
        assert result["notification_sent"] is False
