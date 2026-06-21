"""Tests for apps.automation.services.sms.court_sms_dedup_service."""
from __future__ import annotations

import hashlib
import json
from datetime import datetime
from unittest.mock import MagicMock, patch

import pytest

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
