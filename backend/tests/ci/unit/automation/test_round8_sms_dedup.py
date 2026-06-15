"""Tests for CourtSMSDedupService helper methods."""

from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from unittest.mock import MagicMock, patch

import pytest

from apps.automation.services.sms.court_sms_dedup_service import (
    CourtSMSDedupIdentity,
    CourtSMSDedupResult,
    CourtSMSDedupService,
)
from apps.automation.services.document_delivery.data_classes import DocumentDeliveryRecord


# ---------------------------------------------------------------------------
# Dataclasses
# ---------------------------------------------------------------------------


class TestDataclasses:
    def test_dedup_identity(self):
        identity = CourtSMSDedupIdentity(
            event_id="evt_123",
            event_key="key_456",
            canonical_payload='{"key": "val"}',
            uses_fallback=False,
        )
        assert identity.event_id == "evt_123"
        assert identity.uses_fallback is False

    def test_dedup_result(self):
        mock_sms = MagicMock()
        identity = CourtSMSDedupIdentity(event_id=None, event_key=None, canonical_payload=None)
        result = CourtSMSDedupResult(sms=mock_sms, created=True, identity=identity)
        assert result.created is True


# ---------------------------------------------------------------------------
# CourtSMSDedupService
# ---------------------------------------------------------------------------


class TestNormalizeText:
    def test_normal(self):
        svc = CourtSMSDedupService()
        assert svc._normalize_text("hello  world") == "hello world"

    def test_empty(self):
        svc = CourtSMSDedupService()
        assert svc._normalize_text("") == ""

    def test_none(self):
        svc = CourtSMSDedupService()
        assert svc._normalize_text(None) == ""

    def test_whitespace_only(self):
        svc = CourtSMSDedupService()
        assert svc._normalize_text("   ") == ""


class TestNormalizeSendTime:
    def test_naive_datetime(self):
        svc = CourtSMSDedupService()
        naive = datetime(2025, 1, 15, 10, 30, 0)
        result = svc._normalize_send_time(naive)
        assert "2025-01-15" in result

    def test_aware_datetime(self):
        svc = CourtSMSDedupService()
        aware = datetime(2025, 1, 15, 10, 30, 0, tzinfo=timezone.utc)
        result = svc._normalize_send_time(aware)
        assert "2025-01-15" in result


class TestHashPayload:
    def test_basic(self):
        svc = CourtSMSDedupService()
        result = svc._hash_payload("test")
        expected = hashlib.sha256("test".encode("utf-8")).hexdigest()
        assert result == expected

    def test_unicode(self):
        svc = CourtSMSDedupService()
        result = svc._hash_payload("中文测试")
        assert len(result) == 64  # SHA-256 hex digest


class TestBuildDocumentDeliveryIdentity:
    def test_with_event_id(self):
        svc = CourtSMSDedupService()
        record = DocumentDeliveryRecord(
            case_number="2025-粤01民初1号",
            send_time=datetime(2025, 1, 15, tzinfo=timezone.utc),
            element_index=0,
            delivery_event_id="evt_123",
        )
        identity = svc.build_document_delivery_identity(record)
        assert identity.event_id == "evt_123"
        assert identity.event_key is not None
        assert identity.uses_fallback is False

    def test_without_event_id(self):
        svc = CourtSMSDedupService()
        record = DocumentDeliveryRecord(
            case_number="2025-粤01民初1号",
            send_time=datetime(2025, 1, 15, tzinfo=timezone.utc),
            element_index=0,
            delivery_event_id="",
        )
        identity = svc.build_document_delivery_identity(record)
        assert identity.event_id is None or identity.event_id == ""
        assert identity.event_key is not None
        assert identity.uses_fallback is True

    def test_no_event_id_no_case_number(self):
        svc = CourtSMSDedupService()
        record = DocumentDeliveryRecord(
            case_number="",
            send_time=None,
            element_index=0,
            delivery_event_id="",
        )
        identity = svc.build_document_delivery_identity(record)
        assert identity.event_key is None


class TestBuildExistingSmsResult:
    def test_basic(self):
        svc = CourtSMSDedupService()
        sms = MagicMock()
        sms.notification_results = {}
        sms.feishu_sent_at = None
        result = svc.build_existing_sms_result(sms, "/path/to/file.pdf")
        assert result["success"] is True
        assert result["deduplicated"] is True
        assert result["renamed_path"] == "/path/to/file.pdf"

    def test_notification_sent(self):
        svc = CourtSMSDedupService()
        sms = MagicMock()
        sms.notification_results = {"feishu": {"success": True}}
        sms.feishu_sent_at = None
        result = svc.build_existing_sms_result(sms, "/path.pdf")
        assert result["notification_sent"] is True

    def test_feishu_sent_at_fallback(self):
        svc = CourtSMSDedupService()
        sms = MagicMock()
        sms.notification_results = {}
        sms.feishu_sent_at = datetime.now()
        result = svc.build_existing_sms_result(sms, "/path.pdf")
        assert result["notification_sent"] is True


class TestHasModelField:
    def test_existing_field(self):
        svc = CourtSMSDedupService()
        assert svc._has_model_field("content") is True

    def test_missing_field(self):
        svc = CourtSMSDedupService()
        assert svc._has_model_field("nonexistent_field_xyz") is False
