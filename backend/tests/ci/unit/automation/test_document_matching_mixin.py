"""Tests for automation.services.document_delivery.api.document_delivery_api_service._matching.

Covers: _match_case_by_number, _match_case_by_document_parties,
_sync_case_number_to_case, _send_notification, _get_system_user.
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest


# ---------------------------------------------------------------------------
# _match_case_by_number
# ---------------------------------------------------------------------------


class TestMatchCaseByNumber:
    def test_delegates_to_case_matcher(self):
        from apps.automation.services.document_delivery.api.document_delivery_api_service._matching import (
            DocumentMatchingMixin,
        )

        mock_matcher = MagicMock()
        mock_matcher.match_by_case_number.return_value = "case_obj"

        class Dummy(DocumentMatchingMixin):
            @property
            def case_matcher(self):
                return mock_matcher

            @property
            def document_renamer(self):
                return MagicMock()

            @property
            def notification_service(self):
                return MagicMock()

        dummy = Dummy()
        result = dummy._match_case_by_number("CN001")
        assert result == "case_obj"
        mock_matcher.match_by_case_number.assert_called_once_with(["CN001"])


# ---------------------------------------------------------------------------
# _match_case_by_document_parties
# ---------------------------------------------------------------------------


class TestMatchCaseByDocumentParties:
    def _make_dummy(self, *, extract_result=None, match_result=None):
        from apps.automation.services.document_delivery.api.document_delivery_api_service._matching import (
            DocumentMatchingMixin,
        )

        class Dummy(DocumentMatchingMixin):
            @property
            def case_matcher(self):
                return MagicMock(
                    extract_parties_from_document=MagicMock(return_value=extract_result),
                    match_by_party_names=MagicMock(return_value=match_result),
                )

            @property
            def document_renamer(self):
                return MagicMock()

            @property
            def notification_service(self):
                return MagicMock()

        return Dummy()

    def test_no_extracted_parties_returns_none(self):
        dummy = self._make_dummy(extract_result=None)
        result = dummy._match_case_by_document_parties(["/path/doc.pdf"])
        assert result is None

    def test_active_case_returned(self):
        from apps.core.models.enums import CaseStatus

        matched = MagicMock()
        matched.status = CaseStatus.ACTIVE
        matched.id = 1
        dummy = self._make_dummy(extract_result=["张三"], match_result=matched)
        result = self._make_dummy(extract_result=["张三"], match_result=matched)
        # Re-create with proper match
        dummy2 = self._make_dummy(extract_result=["张三"], match_result=matched)
        result = dummy2._match_case_by_document_parties(["/path/doc.pdf"])
        assert result == matched

    def test_inactive_case_continues(self):
        from apps.core.models.enums import CaseStatus

        inactive = MagicMock()
        inactive.status = CaseStatus.CLOSED
        dummy = self._make_dummy(extract_result=["张三"], match_result=inactive)
        result = dummy._match_case_by_document_parties(["/path/doc.pdf"])
        assert result is None

    def test_exception_returns_none(self):
        from apps.automation.services.document_delivery.api.document_delivery_api_service._matching import (
            DocumentMatchingMixin,
        )

        class Dummy(DocumentMatchingMixin):
            @property
            def case_matcher(self):
                m = MagicMock()
                m.extract_parties_from_document.side_effect = RuntimeError("fail")
                return m

            @property
            def document_renamer(self):
                return MagicMock()

            @property
            def notification_service(self):
                return MagicMock()

        result = Dummy()._match_case_by_document_parties(["/path/doc.pdf"])
        assert result is None


# ---------------------------------------------------------------------------
# _sync_case_number_to_case
# ---------------------------------------------------------------------------


class TestSyncCaseNumberToCase:
    def _make_dummy(self):
        from apps.automation.services.document_delivery.api.document_delivery_api_service._matching import (
            DocumentMatchingMixin,
        )

        class Dummy(DocumentMatchingMixin):
            @property
            def case_matcher(self):
                return MagicMock()

            @property
            def document_renamer(self):
                return MagicMock()

            @property
            def notification_service(self):
                return MagicMock()

        return Dummy()

    def test_already_exists_returns_true(self):
        dummy = self._make_dummy()
        existing = MagicMock()
        existing.number = "CN001"
        with patch(
            "apps.core.dependencies.business_case.build_case_number_service"
        ) as mock_build:
            svc = MagicMock()
            svc.list_numbers_internal.return_value = [existing]
            mock_build.return_value = svc
            assert dummy._sync_case_number_to_case(1, "CN001") is True

    def test_creates_new_number(self):
        dummy = self._make_dummy()
        with patch(
            "apps.core.dependencies.business_case.build_case_number_service"
        ) as mock_build:
            svc = MagicMock()
            svc.list_numbers_internal.return_value = []
            mock_build.return_value = svc
            assert dummy._sync_case_number_to_case(1, "CN002") is True
            svc.create_number_internal.assert_called_once()

    def test_no_list_method_returns_false(self):
        dummy = self._make_dummy()
        with patch(
            "apps.core.dependencies.business_case.build_case_number_service"
        ) as mock_build:
            svc = MagicMock(spec=[])  # no methods
            mock_build.return_value = svc
            assert dummy._sync_case_number_to_case(1, "CN003") is False

    def test_exception_returns_false(self):
        dummy = self._make_dummy()
        with patch(
            "apps.core.dependencies.business_case.build_case_number_service"
        ) as mock_build:
            mock_build.side_effect = RuntimeError("fail")
            assert dummy._sync_case_number_to_case(1, "CN004") is False


# ---------------------------------------------------------------------------
# _send_notification
# ---------------------------------------------------------------------------


class TestSendNotification:
    def _make_dummy(self, notification_result=None):
        from apps.automation.services.document_delivery.api.document_delivery_api_service._matching import (
            DocumentMatchingMixin,
        )

        class Dummy(DocumentMatchingMixin):
            @property
            def case_matcher(self):
                return MagicMock()

            @property
            def document_renamer(self):
                return MagicMock()

            @property
            def notification_service(self):
                result = MagicMock()
                result.to_notification_results.return_value = {"wechat": {"success": True}}
                result.any_success = True
                return MagicMock(send_case_chat_notification=MagicMock(return_value=result))

        return Dummy()

    def test_no_case_returns_false(self):
        dummy = self._make_dummy()
        sms = MagicMock()
        sms.case = None
        sms.id = 1
        assert dummy._send_notification(sms, ["/path/doc.pdf"]) is False

    def test_success(self):
        dummy = self._make_dummy()
        sms = MagicMock()
        sms.case = MagicMock()
        result = dummy._send_notification(sms, ["/path/doc.pdf"])
        assert result is True

    def test_exception_returns_false(self):
        from apps.automation.services.document_delivery.api.document_delivery_api_service._matching import (
            DocumentMatchingMixin,
        )

        class Dummy(DocumentMatchingMixin):
            @property
            def case_matcher(self):
                return MagicMock()

            @property
            def document_renamer(self):
                return MagicMock()

            @property
            def notification_service(self):
                svc = MagicMock()
                svc.send_case_chat_notification.side_effect = RuntimeError("fail")
                return svc

        dummy = Dummy()
        sms = MagicMock()
        sms.case = MagicMock()
        sms.notification_results = {}
        assert dummy._send_notification(sms, ["/path/doc.pdf"]) is False


# ---------------------------------------------------------------------------
# _get_system_user
# ---------------------------------------------------------------------------


class TestGetSystemUser:
    def _make_dummy(self):
        from apps.automation.services.document_delivery.api.document_delivery_api_service._matching import (
            DocumentMatchingMixin,
        )

        class Dummy(DocumentMatchingMixin):
            @property
            def case_matcher(self):
                return MagicMock()

            @property
            def document_renamer(self):
                return MagicMock()

            @property
            def notification_service(self):
                return MagicMock()

        return Dummy()

    def test_success(self):
        dummy = self._make_dummy()
        with patch("apps.core.interfaces.ServiceLocator") as MockLoc:
            lawyer_svc = MagicMock()
            admin = MagicMock()
            admin.id = 1
            lawyer_svc.get_admin_lawyer.return_value = admin
            lawyer_svc.get_lawyer_model.return_value = "user_model"
            MockLoc.get_lawyer_service.return_value = lawyer_svc
            result = dummy._get_system_user()
            assert result == "user_model"

    def test_no_admin_returns_none(self):
        dummy = self._make_dummy()
        with patch("apps.core.interfaces.ServiceLocator") as MockLoc:
            lawyer_svc = MagicMock()
            lawyer_svc.get_admin_lawyer.return_value = None
            MockLoc.get_lawyer_service.return_value = lawyer_svc
            assert dummy._get_system_user() is None

    def test_exception_returns_none(self):
        dummy = self._make_dummy()
        with patch("apps.core.interfaces.ServiceLocator") as MockLoc:
            MockLoc.get_lawyer_service.side_effect = RuntimeError("fail")
            assert dummy._get_system_user() is None
