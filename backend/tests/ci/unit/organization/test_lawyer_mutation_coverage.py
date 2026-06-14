"""补充覆盖测试: organization/services/lawyer/mutation.py (40 missing)

覆盖: _apply_field_updates 所有字段分支, delete_lawyer 权限/冲突/正常,
update_lawyer 权限拒绝。
"""
from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest

from apps.core.exceptions import ConflictError, PermissionDenied, ValidationException
from apps.organization.dtos import LawyerUpdateDTO
from apps.organization.services.lawyer.mutation import LawyerMutationService


def _make_lawyer(
    *,
    pk: int = 1,
    real_name: str = "Test",
    phone: str = "13800000000",
    license_no: str = "L001",
    id_card: str = "110101199001011234",
    is_admin: bool = False,
) -> SimpleNamespace:
    return SimpleNamespace(
        pk=pk,
        real_name=real_name,
        phone=phone,
        license_no=license_no,
        id_card=id_card,
        is_admin=is_admin,
        law_firm=None,
        lawyer_teams=MagicMock(),
        biz_teams=MagicMock(),
        created_cases=MagicMock(),
        set_password=MagicMock(),
        save=MagicMock(),
        delete=MagicMock(),
    )


def _make_svc() -> LawyerMutationService:
    access_policy = MagicMock()
    upload_service = MagicMock()
    return LawyerMutationService(access_policy=access_policy, upload_service=upload_service)


# ── _apply_field_updates ──────────────────────────────────────────


class TestApplyFieldUpdates:
    def test_update_real_name(self) -> None:
        svc = _make_svc()
        lawyer = _make_lawyer()
        data = LawyerUpdateDTO(real_name="New Name")
        fields = svc._apply_field_updates(lawyer, data)
        assert lawyer.real_name == "New Name"
        assert "real_name" in fields

    def test_update_phone(self) -> None:
        svc = _make_svc()
        lawyer = _make_lawyer()
        data = LawyerUpdateDTO(phone="13900000000")
        fields = svc._apply_field_updates(lawyer, data)
        assert lawyer.phone == "13900000000"
        assert "phone" in fields

    def test_update_license_no(self) -> None:
        svc = _make_svc()
        lawyer = _make_lawyer()
        data = LawyerUpdateDTO(license_no="L999")
        fields = svc._apply_field_updates(lawyer, data)
        assert lawyer.license_no == "L999"
        assert "license_no" in fields

    def test_update_id_card(self) -> None:
        svc = _make_svc()
        lawyer = _make_lawyer()
        data = LawyerUpdateDTO(id_card="310101199001011234")
        fields = svc._apply_field_updates(lawyer, data)
        assert lawyer.id_card == "310101199001011234"
        assert "id_card" in fields

    def test_update_is_admin(self) -> None:
        svc = _make_svc()
        lawyer = _make_lawyer()
        data = LawyerUpdateDTO(is_admin=True)
        fields = svc._apply_field_updates(lawyer, data)
        assert lawyer.is_admin is True
        assert "is_admin" in fields

    def test_update_password(self) -> None:
        svc = _make_svc()
        lawyer = _make_lawyer()
        data = LawyerUpdateDTO(password="newpass123")
        fields = svc._apply_field_updates(lawyer, data)
        lawyer.set_password.assert_called_once_with("newpass123")
        assert "password" in fields

    def test_update_law_firm(self) -> None:
        svc = _make_svc()
        lawyer = _make_lawyer()
        mock_firm = MagicMock()
        data = LawyerUpdateDTO(law_firm_id=42)

        with patch("apps.organization.services.lawyer.mutation.LawFirm") as MockFirm:
            MockFirm.objects.filter.return_value.first.return_value = mock_firm
            fields = svc._apply_field_updates(lawyer, data)
            assert lawyer.law_firm is mock_firm
            assert "law_firm_id" in fields

    def test_update_law_firm_not_found(self) -> None:
        svc = _make_svc()
        lawyer = _make_lawyer()
        data = LawyerUpdateDTO(law_firm_id=999)

        with patch("apps.organization.services.lawyer.mutation.LawFirm") as MockFirm:
            MockFirm.objects.filter.return_value.first.return_value = None
            with pytest.raises(ValidationException, match="律所不存在"):
                svc._apply_field_updates(lawyer, data)

    def test_no_updates_returns_empty(self) -> None:
        svc = _make_svc()
        lawyer = _make_lawyer()
        data = LawyerUpdateDTO()
        fields = svc._apply_field_updates(lawyer, data)
        assert fields == []


# ── update_lawyer ─────────────────────────────────────────────────


class TestUpdateLawyer:
    @pytest.mark.django_db
    def test_permission_denied(self) -> None:
        svc = _make_svc()
        svc.access_policy.can_update_lawyer.return_value = False
        lawyer = _make_lawyer()
        user = _make_lawyer(pk=2)
        data = LawyerUpdateDTO(real_name="New")

        with pytest.raises(PermissionDenied):
            svc.update_lawyer(lawyer, data, user)

    @pytest.mark.django_db
    def test_success_updates_fields(self) -> None:
        svc = _make_svc()
        svc.access_policy.can_update_lawyer.return_value = True
        lawyer = _make_lawyer()
        user = _make_lawyer(pk=2)
        data = LawyerUpdateDTO(real_name="Updated")

        result = svc.update_lawyer(lawyer, data, user)
        assert result.real_name == "Updated"
        lawyer.save.assert_called()

    @pytest.mark.django_db
    def test_with_license_pdf(self) -> None:
        svc = _make_svc()
        svc.access_policy.can_update_lawyer.return_value = True
        lawyer = _make_lawyer()
        user = _make_lawyer(pk=2)
        data = LawyerUpdateDTO(real_name="Updated")
        mock_file = MagicMock()

        result = svc.update_lawyer(lawyer, data, user, license_pdf=mock_file)
        svc.upload_service.attach_license_pdf.assert_called_with(lawyer, mock_file)
        lawyer.save.assert_called()

    @pytest.mark.django_db
    def test_with_avatar(self) -> None:
        svc = _make_svc()
        svc.access_policy.can_update_lawyer.return_value = True
        lawyer = _make_lawyer()
        user = _make_lawyer(pk=2)
        data = LawyerUpdateDTO()
        mock_avatar = MagicMock()

        result = svc.update_lawyer(lawyer, data, user, avatar=mock_avatar)
        svc.upload_service.attach_avatar.assert_called_with(lawyer, mock_avatar)


# ── delete_lawyer ─────────────────────────────────────────────────


class TestDeleteLawyer:
    @pytest.mark.django_db
    def test_permission_denied(self) -> None:
        svc = _make_svc()
        svc.access_policy.can_delete_lawyer.return_value = False
        lawyer = _make_lawyer()
        user = _make_lawyer(pk=2)

        with pytest.raises(PermissionDenied):
            svc.delete_lawyer(lawyer, user)

    @pytest.mark.django_db
    def test_has_created_cases_raises(self) -> None:
        svc = _make_svc()
        svc.access_policy.can_delete_lawyer.return_value = True
        lawyer = _make_lawyer()
        lawyer.created_cases.exists.return_value = True
        user = _make_lawyer(pk=2)

        with pytest.raises(ConflictError, match="无法删除"):
            svc.delete_lawyer(lawyer, user)

    @patch("apps.organization.services.lawyer.mutation.invalidate_users_access_context")
    def test删除成功(self, mock_invalidate: MagicMock) -> None:
        svc = _make_svc()
        svc.access_policy.can_delete_lawyer.return_value = True
        lawyer = _make_lawyer()
        lawyer.created_cases.exists.return_value = False
        lawyer.lawyer_teams.values_list.return_value = [1, 2]
        user = _make_lawyer(pk=2)

        with patch("apps.organization.services.lawyer.mutation.Lawyer") as MockLawyer:
            MockLawyer.objects.filter.return_value.values_list.return_value = [2, 3]
            svc.delete_lawyer(lawyer, user)
            lawyer.delete.assert_called_once()
            mock_invalidate.assert_called_once()
