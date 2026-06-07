"""Coverage tests for contacts.services.contact_service."""

from unittest.mock import MagicMock, patch

import pytest

from apps.contacts.services.contact_service import CaseContactService
from apps.core.exceptions import NotFoundError


class TestCaseContactService:
    def _make(self):
        return CaseContactService()

    def _set_does_not_exist(self, MockModel):
        """Set DoesNotExist on a MagicMock to a real exception class."""
        MockModel.DoesNotExist = type("DoesNotExist", (Exception,), {})

    @patch("apps.contacts.services.contact_service.CaseContact")
    @patch.object(CaseContactService, "ensure_admin")
    def test_list_contacts(self, mock_admin, MockModel):
        svc = self._make()
        mock_qs = MagicMock()
        mock_qs.order_by.return_value = mock_qs
        MockModel.objects.select_related.return_value = mock_qs
        result = svc.list_contacts(case_id=1)
        assert result is not None

    @patch("apps.contacts.services.contact_service.CaseContact")
    @patch.object(CaseContactService, "ensure_admin")
    def test_get_contact_found(self, mock_admin, MockModel):
        svc = self._make()
        mock_obj = MagicMock()
        MockModel.objects.select_related.return_value.get.return_value = mock_obj
        result = svc.get_contact(1)
        assert result is mock_obj

    @patch("apps.contacts.services.contact_service.CaseContact")
    @patch.object(CaseContactService, "ensure_admin")
    def test_get_contact_not_found(self, mock_admin, MockModel):
        svc = self._make()
        self._set_does_not_exist(MockModel)
        MockModel.objects.select_related.return_value.get.side_effect = MockModel.DoesNotExist
        with pytest.raises(NotFoundError):
            svc.get_contact(999)

    @patch("apps.contacts.services.contact_service.CaseContact")
    @patch.object(CaseContactService, "ensure_admin")
    def test_create_contact(self, mock_admin, MockModel):
        svc = self._make()
        mock_obj = MagicMock()
        mock_obj.id = 1
        MockModel.objects.create.return_value = mock_obj
        result = svc.create_contact(1, {"name": "test"})
        assert result.id == 1

    @patch("apps.contacts.services.contact_service.CaseContact")
    @patch.object(CaseContactService, "ensure_admin")
    def test_update_contact_not_found(self, mock_admin, MockModel):
        svc = self._make()
        self._set_does_not_exist(MockModel)
        MockModel.objects.get.side_effect = MockModel.DoesNotExist
        with pytest.raises(NotFoundError):
            svc.update_contact(999, {"name": "new"})

    @patch("apps.contacts.services.contact_service.CaseContact")
    @patch.object(CaseContactService, "ensure_admin")
    def test_delete_contact_not_found(self, mock_admin, MockModel):
        svc = self._make()
        self._set_does_not_exist(MockModel)
        MockModel.objects.get.side_effect = MockModel.DoesNotExist
        with pytest.raises(NotFoundError):
            svc.delete_contact(999)
