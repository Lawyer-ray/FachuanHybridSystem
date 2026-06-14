"""organization/services/credential/account_credential_service.py 单元测试。"""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest

from apps.core.exceptions import NotFoundError, PermissionDenied
from apps.organization.dtos import AccountCredentialUpdateDTO
from apps.organization.services.credential.account_credential_service import AccountCredentialService


def _mock_user(**kwargs: object) -> SimpleNamespace:
    defaults: dict[str, object] = {"id": 1, "is_authenticated": True, "is_superuser": False, "law_firm_id": 1}
    defaults.update(kwargs)
    return SimpleNamespace(**defaults)


def _mock_credential(**kwargs: object) -> MagicMock:
    cred = MagicMock()
    cred.id = kwargs.get("id", 1)
    cred.lawyer_id = kwargs.get("lawyer_id", 1)
    cred.site_name = kwargs.get("site_name", "test_site")
    cred.url = kwargs.get("url", "")
    cred.account = kwargs.get("account", "user123")
    cred.password = kwargs.get("password", "pass")
    cred.save = MagicMock()
    cred.delete = MagicMock()
    return cred


# ── list_credentials ────────────────────────────────────────────────────


class TestListCredentials:
    def test_superuser_sees_all(self) -> None:
        svc = AccountCredentialService()
        user = _mock_user(is_superuser=True)
        with patch.object(svc, "_get_base_queryset") as mock_qs:
            mock_qs.return_value = MagicMock()
            result = svc.list_credentials(user=user)
            # Superuser branch: no filter applied

    def test_non_superuser_filters_by_firm(self) -> None:
        svc = AccountCredentialService()
        user = _mock_user(law_firm_id=1)
        qs = MagicMock()
        with patch.object(svc, "_get_base_queryset", return_value=qs):
            svc.list_credentials(user=user)
            qs.filter.assert_any_call(lawyer__law_firm_id=1)

    def test_no_user_no_firm(self) -> None:
        svc = AccountCredentialService()
        qs = MagicMock()
        with patch.object(svc, "_get_base_queryset", return_value=qs):
            result = svc.list_credentials(user=None)
            qs.none.assert_called_once()

    def test_with_lawyer_name(self) -> None:
        svc = AccountCredentialService()
        user = _mock_user(is_superuser=True)
        qs = MagicMock()
        with patch.object(svc, "_get_base_queryset", return_value=qs):
            svc.list_credentials(lawyer_name="John", user=user)
            qs.filter.assert_called()


# ── get_credential ──────────────────────────────────────────────────────


class TestGetCredential:
    def test_not_found(self) -> None:
        svc = AccountCredentialService()
        with patch.object(svc, "get_credential_by_id", side_effect=NotFoundError()):
            with pytest.raises(NotFoundError):
                svc.get_credential(99)

    def test_permission_denied(self) -> None:
        svc = AccountCredentialService()
        cred = _mock_credential()
        with patch.object(svc, "get_credential_by_id", return_value=cred):
            with patch.object(svc._access_policy, "can_read_lawyer", return_value=False):
                with pytest.raises(PermissionDenied):
                    svc.get_credential(1, _mock_user())

    def test_success(self) -> None:
        svc = AccountCredentialService()
        cred = _mock_credential()
        with patch.object(svc, "get_credential_by_id", return_value=cred):
            with patch.object(svc._access_policy, "can_read_lawyer", return_value=True):
                assert svc.get_credential(1, _mock_user()) is cred


# ── get_credential_by_id ────────────────────────────────────────────────


class TestGetCredentialById:
    def test_not_found(self) -> None:
        svc = AccountCredentialService()
        qs = MagicMock()
        qs.filter.return_value.first.return_value = None
        with patch.object(svc, "_get_base_queryset", return_value=qs):
            with pytest.raises(NotFoundError):
                svc.get_credential_by_id(99)

    def test_found(self) -> None:
        svc = AccountCredentialService()
        cred = _mock_credential()
        qs = MagicMock()
        qs.filter.return_value.first.return_value = cred
        with patch.object(svc, "_get_base_queryset", return_value=qs):
            assert svc.get_credential_by_id(1) is cred


# ── update_credential ──────────────────────────────────────────────────


class TestUpdateCredential:
    def test_updates_fields(self, db: object) -> None:
        svc = AccountCredentialService()
        cred = _mock_credential()
        with patch.object(svc, "get_credential", return_value=cred):
            data = AccountCredentialUpdateDTO(site_name="new_site", account="new_acc")
            result = svc.update_credential(1, data, _mock_user())
            assert result.site_name == "new_site"
            assert result.account == "new_acc"
            cred.save.assert_called_once()

    def test_no_changes(self, db: object) -> None:
        svc = AccountCredentialService()
        cred = _mock_credential()
        with patch.object(svc, "get_credential", return_value=cred):
            data = AccountCredentialUpdateDTO()
            svc.update_credential(1, data, _mock_user())
            cred.save.assert_not_called()


# ── delete_credential ──────────────────────────────────────────────────


class TestDeleteCredential:
    def test_success(self, db: object) -> None:
        svc = AccountCredentialService()
        cred = _mock_credential()
        with patch.object(svc, "get_credential", return_value=cred):
            svc.delete_credential(1, _mock_user())
            cred.delete.assert_called_once()


# ── get_credentials_by_site ─────────────────────────────────────────────


class TestGetCredentialsBySite:
    def test_uses_site_url_mapping(self) -> None:
        svc = AccountCredentialService()
        qs = MagicMock()
        with patch.object(svc, "_get_base_queryset", return_value=qs):
            svc.get_credentials_by_site("court_zxfw")
            # filter is called, chain continues
            assert qs.filter.called


# ── get_credential_by_account ───────────────────────────────────────────


class TestGetCredentialByAccount:
    def test_not_found(self) -> None:
        svc = AccountCredentialService()
        qs = MagicMock()
        qs.filter.return_value.first.return_value = None
        with patch.object(svc, "_get_base_queryset", return_value=qs):
            with pytest.raises(NotFoundError):
                svc.get_credential_by_account("user", "site")

    def test_found(self) -> None:
        svc = AccountCredentialService()
        cred = _mock_credential()
        qs = MagicMock()
        qs.filter.return_value.first.return_value = cred
        with patch.object(svc, "_get_base_queryset", return_value=qs):
            assert svc.get_credential_by_account("user", "site") is cred


# ── list_sites_for_lawyer ──────────────────────────────────────────────


class TestListSitesForLawyer:
    def test_returns_distinct(self) -> None:
        svc = AccountCredentialService()
        expected = ["site1", "site2"]
        mock_distinct = MagicMock()
        mock_distinct.__iter__ = MagicMock(return_value=iter(expected))
        mock_distinct.__len__ = MagicMock(return_value=len(expected))
        qs = MagicMock()
        qs.filter.return_value.values_list.return_value.distinct.return_value = mock_distinct
        with patch.object(svc, "_get_base_queryset", return_value=qs):
            result = svc.list_sites_for_lawyer(1)
            assert result == expected
            qs.filter.assert_called_once_with(lawyer_id=1)


# ── filter_by_ids_and_site ─────────────────────────────────────────────


class TestFilterByIdsAndSite:
    def test_filters(self) -> None:
        svc = AccountCredentialService()
        qs = MagicMock()
        with patch.object(svc, "_get_base_queryset", return_value=qs):
            svc.filter_by_ids_and_site([1, 2], "site")
            qs.filter.assert_called_once_with(id__in=[1, 2], site_name="site")


# ── SITE_URL_MAPPING ──────────────────────────────────────────────────


class TestSiteUrlMapping:
    def test_has_court_zxfw(self) -> None:
        assert "court_zxfw" in AccountCredentialService.SITE_URL_MAPPING
