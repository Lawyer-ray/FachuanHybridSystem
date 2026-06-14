"""organization/services/lawyer/mutation.py 单元测试。"""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest

from apps.core.exceptions import ConflictError, PermissionDenied, ValidationException
from apps.organization.dtos import LawyerUpdateDTO
from apps.organization.services.lawyer.mutation import LawyerMutationService


def _mock_access_policy(**overrides: object) -> MagicMock:
    policy = MagicMock()
    policy.can_create.return_value = overrides.get("can_create", True)
    policy.can_update_lawyer.return_value = overrides.get("can_update", True)
    policy.can_delete_lawyer.return_value = overrides.get("can_delete", True)
    return policy


def _make_lawyer(**kwargs: object) -> MagicMock:
    lawyer = MagicMock()
    lawyer.pk = kwargs.get("pk", 1)
    lawyer.id = kwargs.get("id", 1)
    lawyer.law_firm_id = kwargs.get("law_firm_id", 1)
    lawyer.law_firm = MagicMock()
    lawyer.phone = kwargs.get("phone", "13800000000")
    lawyer.real_name = kwargs.get("real_name", "Test")
    lawyer.is_admin = kwargs.get("is_admin", False)
    lawyer.license_no = kwargs.get("license_no", "")
    lawyer.id_card = kwargs.get("id_card", "")
    lawyer.created_cases = MagicMock()
    lawyer.created_cases.exists.return_value = False
    lawyer.lawyer_teams = MagicMock()
    lawyer.lawyer_teams.values_list.return_value = []
    lawyer.biz_teams = MagicMock()
    lawyer.set_password = MagicMock()
    lawyer.save = MagicMock()
    lawyer.delete = MagicMock()
    return lawyer


# ── update_lawyer ──────────────────────────────────────────────────────


class TestUpdateLawyerPermissionDenied:
    def test_raises(self, db: object) -> None:
        access_policy = _mock_access_policy(can_update=False)
        svc = LawyerMutationService(access_policy=access_policy)
        with pytest.raises(PermissionDenied):
            svc.update_lawyer(_make_lawyer(), LawyerUpdateDTO(), _make_lawyer(id=99))


class TestUpdateLawyerFields:
    def test_updates_fields(self, db: object) -> None:
        access_policy = _mock_access_policy()
        upload_service = MagicMock()
        svc = LawyerMutationService(access_policy=access_policy, upload_service=upload_service)
        lawyer = _make_lawyer()
        data = LawyerUpdateDTO(real_name="New Name", phone="13900000000")
        result = svc.update_lawyer(lawyer, data, _make_lawyer(id=99))
        assert result.real_name == "New Name"
        assert result.phone == "13900000000"

    def test_no_changes_no_save(self, db: object) -> None:
        access_policy = _mock_access_policy()
        upload_service = MagicMock()
        svc = LawyerMutationService(access_policy=access_policy, upload_service=upload_service)
        lawyer = _make_lawyer()
        data = LawyerUpdateDTO()
        svc.update_lawyer(lawyer, data, _make_lawyer(id=99))
        lawyer.save.assert_not_called()

    def test_password_change(self, db: object) -> None:
        access_policy = _mock_access_policy()
        upload_service = MagicMock()
        svc = LawyerMutationService(access_policy=access_policy, upload_service=upload_service)
        lawyer = _make_lawyer()
        data = LawyerUpdateDTO(password="newpass123")
        svc.update_lawyer(lawyer, data, _make_lawyer(id=99))
        lawyer.set_password.assert_called_once_with("newpass123")

    def test_license_pdf_attached(self, db: object) -> None:
        access_policy = _mock_access_policy()
        upload_service = MagicMock()
        svc = LawyerMutationService(access_policy=access_policy, upload_service=upload_service)
        lawyer = _make_lawyer()
        fake_pdf = MagicMock()
        svc.update_lawyer(lawyer, LawyerUpdateDTO(), _make_lawyer(id=99), license_pdf=fake_pdf)
        upload_service.attach_license_pdf.assert_called_once_with(lawyer, fake_pdf)


# ── delete_lawyer ──────────────────────────────────────────────────────


class TestDeleteLawyerPermissionDenied:
    def test_raises(self, db: object) -> None:
        access_policy = _mock_access_policy(can_delete=False)
        svc = LawyerMutationService(access_policy=access_policy)
        with pytest.raises(PermissionDenied):
            svc.delete_lawyer(_make_lawyer(), _make_lawyer(id=99))


class TestDeleteLawyerConflict:
    def test_has_cases(self, db: object) -> None:
        access_policy = _mock_access_policy()
        svc = LawyerMutationService(access_policy=access_policy)
        lawyer = _make_lawyer()
        lawyer.created_cases.exists.return_value = True
        with pytest.raises(ConflictError):
            svc.delete_lawyer(lawyer, _make_lawyer(id=99))


class TestDeleteLawyerSuccess:
    def test_deletes(self, db: object) -> None:
        access_policy = _mock_access_policy()
        svc = LawyerMutationService(access_policy=access_policy)
        lawyer = _make_lawyer()
        with patch("apps.organization.services.lawyer.mutation.invalidate_users_access_context"):
            svc.delete_lawyer(lawyer, _make_lawyer(id=99))
            lawyer.delete.assert_called_once()


# ── _apply_field_updates ───────────────────────────────────────────────


class TestApplyFieldUpdates:
    def test_law_firm_change(self) -> None:
        access_policy = _mock_access_policy()
        upload_service = MagicMock()
        svc = LawyerMutationService(access_policy=access_policy, upload_service=upload_service)
        lawyer = _make_lawyer()
        new_firm = MagicMock()
        with patch("apps.organization.services.lawyer.mutation.LawFirm") as MockFirm:
            MockFirm.objects.filter.return_value.first.return_value = new_firm
            data = LawyerUpdateDTO(law_firm_id=2)
            changed = svc._apply_field_updates(lawyer, data)
            assert "law_firm_id" in changed
            assert lawyer.law_firm == new_firm

    def test_law_firm_not_found(self) -> None:
        access_policy = _mock_access_policy()
        upload_service = MagicMock()
        svc = LawyerMutationService(access_policy=access_policy, upload_service=upload_service)
        lawyer = _make_lawyer()
        with patch("apps.organization.services.lawyer.mutation.LawFirm") as MockFirm:
            MockFirm.objects.filter.return_value.first.return_value = None
            data = LawyerUpdateDTO(law_firm_id=999)
            with pytest.raises(ValidationException):
                svc._apply_field_updates(lawyer, data)

    def test_is_admin_change(self) -> None:
        access_policy = _mock_access_policy()
        upload_service = MagicMock()
        svc = LawyerMutationService(access_policy=access_policy, upload_service=upload_service)
        lawyer = _make_lawyer()
        data = LawyerUpdateDTO(is_admin=True)
        changed = svc._apply_field_updates(lawyer, data)
        assert "is_admin" in changed
        assert lawyer.is_admin is True
