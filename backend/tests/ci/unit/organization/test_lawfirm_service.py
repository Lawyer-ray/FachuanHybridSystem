"""organization/services/lawfirm_service.py 单元测试。"""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest

from apps.core.exceptions import (
    AuthenticationError,
    ConflictError,
    NotFoundError,
    PermissionDenied,
)
from apps.organization.dtos import LawFirmCreateDTO, LawFirmUpdateDTO
from apps.organization.services.lawfirm_service import LawFirmService, LawFirmServiceAdapter


def _user(**kwargs: object) -> SimpleNamespace:
    defaults: dict[str, object] = {"id": 1, "is_authenticated": True, "is_superuser": False, "is_admin": False, "law_firm_id": 1}
    defaults.update(kwargs)
    return SimpleNamespace(**defaults)


def _lawfirm(**kwargs: object) -> SimpleNamespace:
    defaults: dict[str, object] = {"id": 1, "name": "TestFirm", "address": "", "phone": "", "social_credit_code": ""}
    defaults.update(kwargs)
    return SimpleNamespace(**defaults)


# ── get_lawfirm ─────────────────────────────────────────────────────────


class TestGetLawfirm:
    def test_none_user_raises_auth(self) -> None:
        with pytest.raises(AuthenticationError):
            LawFirmService().get_lawfirm(1, None)

    def test_not_found(self) -> None:
        svc = LawFirmService()
        with patch.object(svc, "get_lawfirm_by_id", return_value=None):
            with pytest.raises(NotFoundError):
                svc.get_lawfirm(99, _user())

    def test_permission_denied(self) -> None:
        svc = LawFirmService()
        firm = _lawfirm()
        with patch.object(svc, "get_lawfirm_by_id", return_value=firm):
            with patch.object(svc._access_policy, "can_read_lawfirm", return_value=False):
                with pytest.raises(PermissionDenied):
                    svc.get_lawfirm(1, _user())

    def test_success(self) -> None:
        svc = LawFirmService()
        firm = _lawfirm()
        with patch.object(svc, "get_lawfirm_by_id", return_value=firm):
            with patch.object(svc._access_policy, "can_read_lawfirm", return_value=True):
                assert svc.get_lawfirm(1, _user()) is firm


# ── list_lawfirms ───────────────────────────────────────────────────────


class TestListLawfirms:
    def test_none_user(self) -> None:
        svc = LawFirmService()
        qs = MagicMock()
        qs.none.return_value = qs
        qs.__getitem__ = MagicMock(return_value=qs)
        user = SimpleNamespace(id=1, is_authenticated=True, is_superuser=False, law_firm_id=None)
        with patch.object(svc, "get_lawfirm_queryset", return_value=qs):
            svc.list_lawfirms(user=user)
            qs.none.assert_called_once()

    def test_non_superuser_with_firm(self) -> None:
        svc = LawFirmService()
        qs = MagicMock()
        user = _user(is_superuser=False, law_firm_id=1)
        with patch.object(svc, "get_lawfirm_queryset", return_value=qs):
            svc.list_lawfirms(user=user)
            qs.filter.assert_any_call(id=1)

    def test_non_superuser_no_firm(self) -> None:
        svc = LawFirmService()
        qs = MagicMock()
        user = _user(is_superuser=False, law_firm_id=None)
        with patch.object(svc, "get_lawfirm_queryset", return_value=qs):
            result = svc.list_lawfirms(user=user)
            qs.none.assert_called_once()

    def test_with_name_filter(self) -> None:
        svc = LawFirmService()
        qs = MagicMock()
        with patch.object(svc, "get_lawfirm_queryset", return_value=qs):
            svc.list_lawfirms(name="Test")
            qs.filter.assert_any_call(name__icontains="Test")


# ── get_lawfirm_by_id ──────────────────────────────────────────────────


class TestGetLawfirmById:
    def test_not_found(self) -> None:
        svc = LawFirmService()
        qs = MagicMock()
        qs.filter.return_value.first.return_value = None
        with patch.object(svc, "get_lawfirm_queryset", return_value=qs):
            assert svc.get_lawfirm_by_id(99) is None

    def test_found(self) -> None:
        svc = LawFirmService()
        firm = _lawfirm()
        qs = MagicMock()
        qs.filter.return_value.first.return_value = firm
        with patch.object(svc, "get_lawfirm_queryset", return_value=qs):
            assert svc.get_lawfirm_by_id(1) is firm


# ── update_lawfirm ─────────────────────────────────────────────────────


class TestUpdateLawfirm:
    def test_permission_denied(self, db: object) -> None:
        svc = LawFirmService()
        firm = _lawfirm()
        with patch.object(svc, "get_lawfirm", return_value=firm):
            with patch.object(svc._access_policy, "can_update_lawfirm", return_value=False):
                with pytest.raises(PermissionDenied):
                    svc.update_lawfirm(1, LawFirmUpdateDTO(), _user())

    def test_update_fields(self, db: object) -> None:
        svc = LawFirmService()
        firm = MagicMock()
        firm.name = "TestFirm"
        firm.address = ""
        firm.phone = ""
        firm.social_credit_code = ""
        firm.save = MagicMock()
        with patch.object(svc, "get_lawfirm", return_value=firm):
            with patch.object(svc._access_policy, "can_update_lawfirm", return_value=True):
                data = LawFirmUpdateDTO(name="New Name")
                result = svc.update_lawfirm(1, data, _user())
                assert result.name == "New Name"
                firm.save.assert_called_once()


# ── delete_lawfirm ─────────────────────────────────────────────────────


class TestDeleteLawfirm:
    def test_permission_denied(self, db: object) -> None:
        svc = LawFirmService()
        firm = _lawfirm()
        with patch.object(svc, "get_lawfirm", return_value=firm):
            with patch.object(svc._access_policy, "can_delete_lawfirm", return_value=False):
                with pytest.raises(PermissionDenied):
                    svc.delete_lawfirm(1, _user())

    def test_has_lawyers(self, db: object) -> None:
        svc = LawFirmService()
        firm = _lawfirm()
        firm.lawyers = MagicMock()
        firm.lawyers.exists.return_value = True
        with patch.object(svc, "get_lawfirm", return_value=firm):
            with patch.object(svc._access_policy, "can_delete_lawfirm", return_value=True):
                with pytest.raises(ConflictError):
                    svc.delete_lawfirm(1, _user())

    def test_has_teams(self, db: object) -> None:
        svc = LawFirmService()
        firm = _lawfirm()
        firm.lawyers = MagicMock()
        firm.lawyers.exists.return_value = False
        firm.teams = MagicMock()
        firm.teams.exists.return_value = True
        with patch.object(svc, "get_lawfirm", return_value=firm):
            with patch.object(svc._access_policy, "can_delete_lawfirm", return_value=True):
                with pytest.raises(ConflictError):
                    svc.delete_lawfirm(1, _user())

    def test_success(self, db: object) -> None:
        svc = LawFirmService()
        firm = MagicMock()
        firm.lawyers.exists.return_value = False
        firm.teams.exists.return_value = False
        with patch.object(svc, "get_lawfirm", return_value=firm):
            with patch.object(svc._access_policy, "can_delete_lawfirm", return_value=True):
                svc.delete_lawfirm(1, _user())
                firm.delete.assert_called_once()


# ── LawFirmServiceAdapter ─────────────────────────────────────────────


class TestLawFirmServiceAdapter:
    def test_get_lawfirm_none(self) -> None:
        svc = LawFirmService()
        adapter = LawFirmServiceAdapter(lawfirm_service=svc)
        with patch.object(svc, "get_lawfirm_by_id", return_value=None):
            assert adapter.get_lawfirm(1) is None

    def test_get_lawfirm_found(self) -> None:
        svc = LawFirmService()
        adapter = LawFirmServiceAdapter(lawfirm_service=svc)
        firm = MagicMock()
        firm.pk = 1
        firm.name = "F"
        firm.address = ""
        firm.phone = ""
        firm.social_credit_code = ""
        with patch.object(svc, "get_lawfirm_by_id", return_value=firm):
            result = adapter.get_lawfirm(1)
            assert result is not None
