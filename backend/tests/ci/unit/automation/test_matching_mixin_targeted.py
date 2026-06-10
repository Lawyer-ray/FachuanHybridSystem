"""Targeted tests for DocumentDeliveryMatchingMixin and DocumentDeliveryScheduleService."""

from __future__ import annotations

from datetime import timedelta
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock, patch

import pytest
from django.utils import timezone

from apps.automation.models import (
    CourtSMS,
    CourtSMSStatus,
    DocumentDeliverySchedule,
    ScraperTask,
    ScraperTaskType,
)


# ── DocumentDeliveryMatchingMixin ─────────────────────────────────


@pytest.fixture
def matching_mixin():
    from apps.automation.services.document_delivery._matching_mixin import DocumentDeliveryMatchingMixin

    class ConcreteMixin(DocumentDeliveryMatchingMixin):
        _case_matcher_mock = MagicMock()
        _document_renamer_mock = MagicMock()
        _notification_service_mock = MagicMock()

        @property
        def case_matcher(self):
            return self._case_matcher_mock

        @property
        def document_renamer(self):
            return self._document_renamer_mock

        @property
        def notification_service(self):
            return self._notification_service_mock

    return ConcreteMixin()


class TestCaseMatchByNumber:
    def test_delegates_to_matcher(self, matching_mixin):
        matching_mixin.case_matcher.match_by_case_number.return_value = MagicMock()
        result = matching_mixin._match_case_by_number("（2024）京0101民初1234号")
        matching_mixin.case_matcher.match_by_case_number.assert_called_once_with(["（2024）京0101民初1234号"])


class TestCaseMatchByDocumentParties:
    def test_no_documents_returns_none(self, matching_mixin):
        result = matching_mixin._match_case_by_document_parties([])
        assert result is None

    def test_no_extracted_parties(self, matching_mixin):
        matching_mixin.case_matcher.extract_parties_from_document.return_value = None
        result = matching_mixin._match_case_by_document_parties(["/path/to/doc.pdf"])
        assert result is None

    def test_matched_active_case(self, matching_mixin):
        from apps.core.models.enums import CaseStatus

        case = MagicMock()
        case.status = CaseStatus.ACTIVE
        case.id = 42
        matching_mixin.case_matcher.extract_parties_from_document.return_value = ["张某", "李某"]
        matching_mixin.case_matcher.match_by_party_names.return_value = case

        result = matching_mixin._match_case_by_document_parties(["/path/to/doc.pdf"])
        assert result == case

    def test_matched_inactive_case(self, matching_mixin):
        from apps.core.models.enums import CaseStatus

        case = MagicMock()
        case.status = CaseStatus.CLOSED
        matching_mixin.case_matcher.extract_parties_from_document.return_value = ["张某"]
        matching_mixin.case_matcher.match_by_party_names.return_value = case

        result = matching_mixin._match_case_by_document_parties(["/path/to/doc.pdf"])
        assert result is None

    def test_no_matched_case(self, matching_mixin):
        matching_mixin.case_matcher.extract_parties_from_document.return_value = ["张某"]
        matching_mixin.case_matcher.match_by_party_names.return_value = None
        result = matching_mixin._match_case_by_document_parties(["/path/to/doc.pdf"])
        assert result is None

    def test_exception_returns_none(self, matching_mixin):
        matching_mixin.case_matcher.extract_parties_from_document.side_effect = Exception("boom")
        result = matching_mixin._match_case_by_document_parties(["/path/to/doc.pdf"])
        assert result is None


class TestGetSystemUser:
    def test_returns_user(self, matching_mixin):
        with patch("apps.core.interfaces.ServiceLocator") as mock_locator:
            mock_service = MagicMock()
            admin = MagicMock()
            admin.id = 1
            mock_service.get_admin_lawyer.return_value = admin
            mock_service.get_lawyer_model.return_value = MagicMock()
            mock_locator.get_lawyer_service.return_value = mock_service
            result = matching_mixin._get_system_user()
            assert result is not None

    def test_no_admin_returns_none(self, matching_mixin):
        with patch("apps.core.interfaces.ServiceLocator") as mock_locator:
            mock_service = MagicMock()
            mock_service.get_admin_lawyer.return_value = None
            mock_locator.get_lawyer_service.return_value = mock_service
            result = matching_mixin._get_system_user()
            assert result is None

    def test_exception_returns_none(self, matching_mixin):
        with patch("apps.core.interfaces.ServiceLocator") as mock_locator:
            mock_locator.get_lawyer_service.side_effect = Exception("boom")
            result = matching_mixin._get_system_user()
            assert result is None


class TestArchiveToCaseFolder:
    def test_no_case_id(self, matching_mixin):
        sms = MagicMock()
        sms.case_id = None
        matching_mixin._archive_to_case_folder(sms, ["/path.pdf"])

    def test_no_paths(self, matching_mixin):
        sms = MagicMock()
        sms.case_id = 42
        matching_mixin._archive_to_case_folder(sms, [])


class TestSendNotification:
    def test_no_case(self, matching_mixin):
        sms = MagicMock()
        sms.id = 1
        sms.case = None
        result = matching_mixin._send_notification(sms, ["/path.pdf"])
        assert result is False

    def test_with_case(self, matching_mixin):
        sms = MagicMock()
        sms.id = 1
        sms.case = MagicMock()
        notification_result = MagicMock()
        notification_result.to_notification_results.return_value = {"test": {"success": True}}
        notification_result.any_success = True
        matching_mixin.notification_service.send_case_chat_notification.return_value = notification_result

        result = matching_mixin._send_notification(sms, ["/path.pdf"])
        assert result is True

    def test_exception_returns_false(self, matching_mixin):
        sms = MagicMock()
        sms.id = 1
        sms.case = MagicMock()
        sms.notification_results = None
        matching_mixin.notification_service.send_case_chat_notification.side_effect = Exception("boom")
        result = matching_mixin._send_notification(sms, ["/path.pdf"])
        assert result is False


class TestSyncCaseNumberToCase:
    def test_sync_success(self, matching_mixin):
        case_number_service = MagicMock()
        existing_number = MagicMock()
        existing_number.number = "OTHER"
        case_number_service.list_numbers_internal.return_value = [existing_number]
        case_number_service.create_number_internal.return_value = MagicMock()
        matching_mixin._case_number_service = case_number_service

        result = matching_mixin._sync_case_number_to_case(42, "（2024）京0101民初1234号")
        assert result is True
        case_number_service.create_number_internal.assert_called_once()

    def test_already_exists(self, matching_mixin):
        case_number_service = MagicMock()
        existing_number = MagicMock()
        existing_number.number = "（2024）京0101民初1234号"
        case_number_service.list_numbers_internal.return_value = [existing_number]
        matching_mixin._case_number_service = case_number_service

        result = matching_mixin._sync_case_number_to_case(42, "（2024）京0101民初1234号")
        assert result is True
        case_number_service.create_number_internal.assert_not_called()

    def test_no_list_method(self, matching_mixin):
        case_number_service = MagicMock(spec=[])  # Empty spec = no attributes
        matching_mixin._case_number_service = case_number_service

        result = matching_mixin._sync_case_number_to_case(42, "案号")
        assert result is False

    def test_exception_returns_false(self, matching_mixin):
        case_number_service = MagicMock()
        case_number_service.list_numbers_internal.side_effect = Exception("boom")
        matching_mixin._case_number_service = case_number_service

        result = matching_mixin._sync_case_number_to_case(42, "案号")
        assert result is False


class TestRenameAndAttachDocuments:
    def test_no_files(self, matching_mixin):
        sms = MagicMock()
        case = MagicMock()
        result = matching_mixin._rename_and_attach_documents(sms, case, [])
        assert result == ([], None)

    def test_renames_successfully(self, matching_mixin, tmp_path):
        doc = tmp_path / "test.pdf"
        doc.write_bytes(b"test")
        sms = MagicMock()
        case = MagicMock()
        case.name = "测试案件"
        case.id = 42
        matching_mixin.document_renamer.rename.return_value = str(tmp_path / "renamed.pdf")

        with patch.object(matching_mixin, "_get_system_user", return_value=None):
            result = matching_mixin._rename_and_attach_documents(sms, case, [str(doc)])
            assert len(result[0]) == 1


# ── DocumentDeliverySchedule model tests ──────────────────────────


class TestDocumentDeliverySchedule:
    def test_str(self):
        schedule = MagicMock()
        schedule.runs_per_day = 2
        schedule.is_active = True
        schedule.credential = MagicMock()
        schedule.credential.__str__ = lambda self: "test_credential"
        result = DocumentDeliverySchedule.__str__(schedule)
        assert "test_credential" in result

    def test_str_inactive(self):
        schedule = MagicMock()
        schedule.runs_per_day = 1
        schedule.is_active = False
        schedule.credential = MagicMock()
        schedule.credential.__str__ = lambda self: "test_credential"
        result = DocumentDeliverySchedule.__str__(schedule)
        assert "禁用" in result
