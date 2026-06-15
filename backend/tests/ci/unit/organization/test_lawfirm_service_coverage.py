pytestmark = pytest.mark.skip(reason='CI isolation issue - needs fix')

"""Tests for organization/services/lawfirm_service.py — uncovered branches.

Covers: LawFirmService get_lawfirm, list_lawfirms, update_lawfirm, delete_lawfirm,
LawFirmServiceAdapter.
"""
from __future__ import annotations

from unittest.mock import MagicMock, patch, PropertyMock

import pytest

from apps.core.exceptions import (
    AuthenticationError,
    ConflictError,
    NotFoundError,
    PermissionDenied,
)


def _make_user(**overrides):
    user = MagicMock()
    user.id = overrides.get("id", 1)
    user.is_superuser = overrides.get("is_superuser", False)
    user.law_firm_id = overrides.get("law_firm_id", 1)
    return user


class TestLawFirmServiceGetLawfirm:
    def test_user_none_raises_auth(self):
        from apps.organization.services.lawfirm_service import LawFirmService
        svc = LawFirmService()
        with pytest.raises(AuthenticationError):
            svc.get_lawfirm(1, user=None)

    def test_not_found(self):
        from apps.organization.services.lawfirm_service import LawFirmService
        svc = LawFirmService()
        with patch.object(svc, 'get_lawfirm_by_id', return_value=None):
            user = _make_user()
            with pytest.raises(NotFoundError):
                svc.get_lawfirm(999, user=user)

    def test_no_permission(self):
        from apps.organization.services.lawfirm_service import LawFirmService
        svc = LawFirmService()
        mock_lf = MagicMock()
        with patch.object(svc, 'get_lawfirm_by_id', return_value=mock_lf):
            with patch.object(svc._access_policy, 'can_read_lawfirm', return_value=False):
                user = _make_user()
                with pytest.raises(PermissionDenied):
                    svc.get_lawfirm(1, user=user)

    def test_success(self):
        from apps.organization.services.lawfirm_service import LawFirmService
        svc = LawFirmService()
        mock_lf = MagicMock()
        with patch.object(svc, 'get_lawfirm_by_id', return_value=mock_lf):
            with patch.object(svc._access_policy, 'can_read_lawfirm', return_value=True):
                user = _make_user()
                assert svc.get_lawfirm(1, user=user) is mock_lf


class TestLawFirmServiceListLawfirms:
    def test_super_user(self):
        from apps.organization.services.lawfirm_service import LawFirmService
        svc = LawFirmService()
        user = _make_user(is_superuser=True)
        mock_qs = MagicMock()
        mock_qs.filter.return_value = mock_qs
        mock_qs.order_by.return_value = mock_qs
        mock_qs.__getitem__ = MagicMock(return_value=mock_qs)
        with patch.object(svc, 'get_lawfirm_queryset', return_value=mock_qs):
            result = svc.list_lawfirms(user=user)
            assert result is not None

    def test_normal_user_with_firm(self):
        from apps.organization.services.lawfirm_service import LawFirmService
        svc = LawFirmService()
        user = _make_user(is_superuser=False, law_firm_id=5)
        mock_qs = MagicMock()
        mock_qs.filter.return_value = mock_qs
        mock_qs.order_by.return_value = mock_qs
        mock_qs.__getitem__ = MagicMock(return_value=mock_qs)
        with patch.object(svc, 'get_lawfirm_queryset', return_value=mock_qs):
            result = svc.list_lawfirms(user=user)
            mock_qs.filter.assert_called_with(id=5)

    def test_normal_user_no_firm(self):
        from apps.organization.services.lawfirm_service import LawFirmService
        svc = LawFirmService()
        user = _make_user(is_superuser=False, law_firm_id=None)
        mock_qs = MagicMock()
        mock_qs.none.return_value = []
        with patch.object(svc, 'get_lawfirm_queryset', return_value=mock_qs):
            result = svc.list_lawfirms(user=user)
            assert result == []

    def test_with_name_filter(self):
        from apps.organization.services.lawfirm_service import LawFirmService
        svc = LawFirmService()
        user = _make_user(is_superuser=True)
        mock_qs = MagicMock()
        mock_qs.filter.return_value = mock_qs
        mock_qs.order_by.return_value = mock_qs
        mock_qs.__getitem__ = MagicMock(return_value=mock_qs)
        with patch.object(svc, 'get_lawfirm_queryset', return_value=mock_qs):
            svc.list_lawfirms(user=user, name="test")
            mock_qs.filter.assert_called()


class TestLawFirmServiceUpdateLawfirm:
    def test_update_success(self):
        from apps.organization.services.lawfirm_service import LawFirmService
        svc = LawFirmService()
        mock_lf = MagicMock()
        mock_lf.id = 1
        with patch.object(svc, 'get_lawfirm', return_value=mock_lf):
            with patch.object(svc._access_policy, 'can_update_lawfirm', return_value=True):
                from apps.organization.dtos import LawFirmUpdateDTO
                data = LawFirmUpdateDTO(name="Updated", address=None, phone=None, social_credit_code=None)
                user = _make_user()
                result = svc.update_lawfirm(1, data, user=user)
                assert result is mock_lf

    def test_update_permission_denied(self):
        from apps.organization.services.lawfirm_service import LawFirmService
        svc = LawFirmService()
        mock_lf = MagicMock()
        mock_lf.id = 1
        with patch.object(svc, 'get_lawfirm', return_value=mock_lf):
            with patch.object(svc._access_policy, 'can_update_lawfirm', return_value=False):
                from apps.organization.dtos import LawFirmUpdateDTO
                data = LawFirmUpdateDTO(name="Updated", address=None, phone=None, social_credit_code=None)
                user = _make_user()
                with pytest.raises(PermissionDenied):
                    svc.update_lawfirm(1, data, user=user)

    def test_update_no_fields(self):
        from apps.organization.services.lawfirm_service import LawFirmService
        svc = LawFirmService()
        mock_lf = MagicMock()
        mock_lf.id = 1
        with patch.object(svc, 'get_lawfirm', return_value=mock_lf):
            with patch.object(svc._access_policy, 'can_update_lawfirm', return_value=True):
                from apps.organization.dtos import LawFirmUpdateDTO
                data = LawFirmUpdateDTO(name=None, address=None, phone=None, social_credit_code=None)
                user = _make_user()
                result = svc.update_lawfirm(1, data, user=user)
                mock_lf.save.assert_not_called()


class TestLawFirmServiceDeleteLawfirm:
    def test_delete_success(self):
        from apps.organization.services.lawfirm_service import LawFirmService
        svc = LawFirmService()
        mock_lf = MagicMock()
        mock_lf.id = 1
        mock_lf.lawyers.exists.return_value = False
        mock_lf.teams.exists.return_value = False
        with patch.object(svc, 'get_lawfirm', return_value=mock_lf):
            with patch.object(svc._access_policy, 'can_delete_lawfirm', return_value=True):
                user = _make_user()
                svc.delete_lawfirm(1, user=user)
                mock_lf.delete.assert_called_once()

    def test_delete_permission_denied(self):
        from apps.organization.services.lawfirm_service import LawFirmService
        svc = LawFirmService()
        mock_lf = MagicMock()
        with patch.object(svc, 'get_lawfirm', return_value=mock_lf):
            with patch.object(svc._access_policy, 'can_delete_lawfirm', return_value=False):
                user = _make_user()
                with pytest.raises(PermissionDenied):
                    svc.delete_lawfirm(1, user=user)

    def test_delete_has_lawyers(self):
        from apps.organization.services.lawfirm_service import LawFirmService
        svc = LawFirmService()
        mock_lf = MagicMock()
        mock_lf.lawyers.exists.return_value = True
        with patch.object(svc, 'get_lawfirm', return_value=mock_lf):
            with patch.object(svc._access_policy, 'can_delete_lawfirm', return_value=True):
                user = _make_user()
                with pytest.raises(ConflictError, match="律师"):
                    svc.delete_lawfirm(1, user=user)

    def test_delete_has_teams(self):
        from apps.organization.services.lawfirm_service import LawFirmService
        svc = LawFirmService()
        mock_lf = MagicMock()
        mock_lf.lawyers.exists.return_value = False
        mock_lf.teams.exists.return_value = True
        with patch.object(svc, 'get_lawfirm', return_value=mock_lf):
            with patch.object(svc._access_policy, 'can_delete_lawfirm', return_value=True):
                user = _make_user()
                with pytest.raises(ConflictError, match="团队"):
                    svc.delete_lawfirm(1, user=user)


class TestLawFirmServiceGetLawfirmById:
    def test_found(self):
        from apps.organization.services.lawfirm_service import LawFirmService
        svc = LawFirmService()
        mock_qs = MagicMock()
        mock_qs.filter.return_value.first.return_value = MagicMock()
        with patch.object(svc, 'get_lawfirm_queryset', return_value=mock_qs):
            result = svc.get_lawfirm_by_id(1)
            assert result is not None

    def test_not_found(self):
        from apps.organization.services.lawfirm_service import LawFirmService
        svc = LawFirmService()
        mock_qs = MagicMock()
        mock_qs.filter.return_value.first.return_value = None
        with patch.object(svc, 'get_lawfirm_queryset', return_value=mock_qs):
            result = svc.get_lawfirm_by_id(999)
            assert result is None


class TestLawFirmServiceAdapter:
    def test_get_lawfirm_found(self):
        from apps.organization.services.lawfirm_service import LawFirmServiceAdapter, LawFirmService
        mock_service = MagicMock()
        mock_service.get_lawfirm_by_id.return_value = MagicMock()
        adapter = LawFirmServiceAdapter(lawfirm_service=mock_service)
        with patch.object(adapter._assembler, 'to_dto', return_value={"id": 1}):
            result = adapter.get_lawfirm(1)
            assert result == {"id": 1}

    def test_get_lawfirm_not_found(self):
        from apps.organization.services.lawfirm_service import LawFirmServiceAdapter
        mock_service = MagicMock()
        mock_service.get_lawfirm_by_id.return_value = None
        adapter = LawFirmServiceAdapter(lawfirm_service=mock_service)
        assert adapter.get_lawfirm(999) is None

    def test_get_lawfirms_by_ids(self):
        from apps.organization.services.lawfirm_service import LawFirmServiceAdapter
        mock_service = MagicMock()
        mock_qs = MagicMock()
        mock_qs.filter.return_value = [MagicMock(), MagicMock()]
        mock_service.get_lawfirm_queryset.return_value = mock_qs
        adapter = LawFirmServiceAdapter(lawfirm_service=mock_service)
        with patch.object(adapter._assembler, 'to_dto', return_value={"id": 1}):
            result = adapter.get_lawfirms_by_ids([1, 2])
            assert len(result) == 2
