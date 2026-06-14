"""Tests for automation/schemas/court_sms.py (missing: 15 lines).

Covers: _to_media_url branches, from_model for CourtSMSDetailOut and CourtSMSListOut,
field_validators, and Config metadata.
"""
from __future__ import annotations

from datetime import datetime
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest


class TestCourtSMSSubmitIn:
    def test_validate_content_strips_whitespace(self) -> None:
        from apps.automation.schemas.court_sms import CourtSMSSubmitIn
        result = CourtSMSSubmitIn(content="  hello  ")
        assert result.content == "hello"

    def test_validate_content_empty_raises(self) -> None:
        from apps.automation.schemas.court_sms import CourtSMSSubmitIn
        with pytest.raises(Exception):
            CourtSMSSubmitIn(content="")

    def test_validate_content_whitespace_only_raises(self) -> None:
        from apps.automation.schemas.court_sms import CourtSMSSubmitIn
        with pytest.raises(Exception):
            CourtSMSSubmitIn(content="   ")


class TestCourtSMSDetailOutToMediaUrl:
    def test_empty_path(self) -> None:
        from apps.automation.schemas.court_sms import CourtSMSDetailOut
        assert CourtSMSDetailOut._to_media_url("") is None
        assert CourtSMSDetailOut._to_media_url(None) is None  # type: ignore[arg-type]

    @patch("apps.automation.schemas.court_sms.settings")
    def test_absolute_path_inside_media(self, mock_settings: MagicMock) -> None:
        from apps.automation.schemas.court_sms import CourtSMSDetailOut
        mock_settings.MEDIA_ROOT = "/tmp/media"
        mock_settings.MEDIA_URL = "/media/"
        result = CourtSMSDetailOut._to_media_url("/tmp/media/docs/file.pdf")
        assert result is not None
        assert "media" in result

    @patch("apps.automation.schemas.court_sms.settings")
    def test_relative_path(self, mock_settings: MagicMock) -> None:
        from apps.automation.schemas.court_sms import CourtSMSDetailOut
        mock_settings.MEDIA_ROOT = "/tmp/media"
        mock_settings.MEDIA_URL = "/media/"
        result = CourtSMSDetailOut._to_media_url("docs/file.pdf")
        assert result is not None

    @patch("apps.automation.schemas.court_sms.settings")
    def test_path_outside_media_returns_none(self, mock_settings: MagicMock) -> None:
        from apps.automation.schemas.court_sms import CourtSMSDetailOut
        mock_settings.MEDIA_ROOT = "/tmp/media"
        mock_settings.MEDIA_URL = "/media/"
        result = CourtSMSDetailOut._to_media_url("/other/path/file.pdf")
        assert result is None


class TestCourtSMSDetailOutFromModel:
    def test_from_model_basic(self) -> None:
        from apps.automation.schemas.court_sms import CourtSMSDetailOut
        obj = SimpleNamespace(
            id=1,
            content="test content",
            received_at=datetime.now(),
            sms_type="document",
            download_links=[],
            case_numbers=[],
            party_names=[],
            status="completed",
            error_message=None,
            retry_count=0,
            case=None,
            feishu_sent_at=None,
            notification_results=None,
            feishu_error=None,
            created_at=datetime.now(),
            updated_at=datetime.now(),
        )
        with patch("apps.automation.schemas.court_sms.CourtSMSDocumentReferenceService") as MockSvc:
            MockSvc.return_value.collect.return_value = []
            result = CourtSMSDetailOut.from_model(obj)
            assert result.id == 1
            assert result.case is None

    def test_from_model_with_case(self) -> None:
        from apps.automation.schemas.court_sms import CourtSMSDetailOut
        obj = SimpleNamespace(
            id=2,
            content="test",
            received_at=datetime.now(),
            sms_type=None,
            download_links=[],
            case_numbers=[],
            party_names=[],
            status="pending",
            error_message=None,
            retry_count=1,
            case=SimpleNamespace(id=10, name="Test Case"),
            feishu_sent_at=datetime.now(),
            notification_results=None,
            feishu_error=None,
            created_at=datetime.now(),
            updated_at=datetime.now(),
        )
        with patch("apps.automation.schemas.court_sms.CourtSMSDocumentReferenceService") as MockSvc:
            MockSvc.return_value.collect.return_value = []
            result = CourtSMSDetailOut.from_model(obj)
            assert result.case is not None
            assert result.case["id"] == 10


class TestCourtSMSListOutFromModel:
    def test_short_content(self) -> None:
        from apps.automation.schemas.court_sms import CourtSMSListOut
        obj = SimpleNamespace(
            id=1,
            content="short",
            received_at=datetime.now(),
            sms_type=None,
            status="completed",
            case=None,
            feishu_sent_at=None,
            notification_results=None,
            created_at=datetime.now(),
        )
        with patch("apps.automation.schemas.court_sms.CourtSMSDocumentReferenceService") as MockSvc:
            MockSvc.return_value.has_any_references.return_value = False
            result = CourtSMSListOut.from_model(obj)
            assert result.content == "short"

    def test_long_content_truncated(self) -> None:
        from apps.automation.schemas.court_sms import CourtSMSListOut
        obj = SimpleNamespace(
            id=1,
            content="x" * 150,
            received_at=datetime.now(),
            sms_type=None,
            status="completed",
            case=SimpleNamespace(id=1, name="Case"),
            feishu_sent_at=datetime.now(),
            notification_results=None,
            created_at=datetime.now(),
        )
        with patch("apps.automation.schemas.court_sms.CourtSMSDocumentReferenceService") as MockSvc:
            MockSvc.return_value.has_any_references.return_value = True
            result = CourtSMSListOut.from_model(obj)
            assert len(result.content) < 150
            assert result.has_documents is True

    def test_feishu_sent_from_notification_results(self) -> None:
        from apps.automation.schemas.court_sms import CourtSMSListOut
        obj = SimpleNamespace(
            id=1,
            content="test",
            received_at=datetime.now(),
            sms_type=None,
            status="completed",
            case=None,
            feishu_sent_at=None,
            notification_results={"feishu": {"success": True}},
            created_at=datetime.now(),
        )
        with patch("apps.automation.schemas.court_sms.CourtSMSDocumentReferenceService") as MockSvc:
            MockSvc.return_value.has_any_references.return_value = False
            result = CourtSMSListOut.from_model(obj)
            assert result.feishu_sent is True
