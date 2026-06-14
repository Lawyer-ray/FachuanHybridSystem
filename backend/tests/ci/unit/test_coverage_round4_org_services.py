"""Coverage round 4: lawyer_import_service + organization_service_adapter."""
from __future__ import annotations

from unittest.mock import MagicMock, patch, PropertyMock

import pytest


# ============================================================
# lawyer_import_service.py
# ============================================================

class TestLawyerImportService:
    def _make_service(self):
        from apps.organization.services.lawyer_import_service import LawyerImportService
        return LawyerImportService()

    @patch("apps.organization.services.lawyer_import_service.Lawyer")
    def test_import_existing_lawyer_updates(self, MockLawyer):
        svc = self._make_service()
        existing = MagicMock()
        existing.real_name = ""
        existing.phone = None
        existing.license_no = ""
        existing.id_card = ""
        existing.license_pdf = ""
        existing.law_firm = None
        existing.lawyer_teams = MagicMock()
        existing.lawyer_teams.values_list.return_value = []
        existing.biz_teams = MagicMock()
        existing.biz_teams.values_list.return_value = []
        existing.credentials = MagicMock()
        existing.credentials.values_list.return_value = []
        MockLawyer.objects.filter.return_value.first.return_value = existing

        with patch("apps.organization.services.lawyer_import_service.LawFirm") as MockFirm:
            with patch("apps.organization.services.lawyer_import_service.Team"):
                MockFirm.objects.get_or_create.return_value = (MagicMock(), True)
                data = [{
                    "username": "lawyer1",
                    "real_name": "张三",
                    "phone": "13800000000",
                    "license_no": "L123",
                    "id_card": "110101",
                    "law_firm": "测试律所",
                }]
                success, skipped, errors = svc.import_from_json(data, actor="admin")
        assert success == 1
        assert skipped == 0
        assert errors == []
        existing.save.assert_called()

    @patch("apps.organization.services.lawyer_import_service.Lawyer")
    def test_import_new_lawyer(self, MockLawyer):
        svc = self._make_service()
        MockLawyer.objects.filter.return_value.first.return_value = None
        new_lawyer = MagicMock()
        MockLawyer.objects.create_user.return_value = new_lawyer

        with patch("apps.organization.services.lawyer_import_service.LawFirm") as MockFirm:
            with patch("apps.organization.services.lawyer_import_service.Team"):
                MockFirm.objects.get_or_create.return_value = (MagicMock(), True)
                data = [{
                    "username": "new_lawyer",
                    "real_name": "李四",
                    "password": "pass123",
                    "is_admin": True,
                    "is_active": True,
                }]
                success, skipped, errors = svc.import_from_json(data, actor="admin")
        assert success == 1
        MockLawyer.objects.create_user.assert_called_once()

    @patch("apps.organization.services.lawyer_import_service.Lawyer")
    def test_import_with_exception(self, MockLawyer):
        svc = self._make_service()
        MockLawyer.objects.filter.return_value.first.side_effect = RuntimeError("db error")
        data = [{"username": "bad_user"}]
        success, skipped, errors = svc.import_from_json(data, actor="admin")
        assert success == 0
        assert len(errors) == 1
        assert "db error" in errors[0]


class TestLawyerImportMerge:
    def _make_service(self):
        from apps.organization.services.lawyer_import_service import LawyerImportService
        return LawyerImportService()

    def test_merge_lawyer_teams_no_teams(self):
        svc = self._make_service()
        existing = MagicMock()
        svc._merge_lawyer_teams(existing=existing, item={})
        # Should return early without errors

    def test_merge_biz_teams_no_teams(self):
        svc = self._make_service()
        existing = MagicMock()
        svc._merge_biz_teams(existing=existing, item={})
        # Should return early

    @patch("apps.organization.services.lawyer_import_service.Team")
    @patch("apps.organization.services.lawyer_import_service.LawFirm")
    def test_merge_lawyer_teams_adds_new(self, MockFirm, MockTeam):
        svc = self._make_service()
        existing = MagicMock()
        existing.law_firm = MagicMock()
        existing.lawyer_teams.values_list.return_value = []
        MockFirm.objects.get_or_create.return_value = (MagicMock(), True)
        MockTeam.objects.get_or_create.return_value = (MagicMock(), True)
        svc._merge_lawyer_teams(existing=existing, item={"lawyer_teams": ["团队A"]})
        MockTeam.objects.get_or_create.assert_called()

    @patch("apps.organization.services.lawyer_import_service.Team")
    def test_merge_biz_teams_adds_new(self, MockTeam):
        svc = self._make_service()
        existing = MagicMock()
        existing.law_firm = MagicMock()
        existing.biz_teams.values_list.return_value = []
        MockTeam.objects.get_or_create.return_value = (MagicMock(), True)
        svc._merge_biz_teams(existing=existing, item={"biz_teams": ["业务组A"]})
        MockTeam.objects.get_or_create.assert_called()


# ============================================================
# organization_service_adapter.py
# ============================================================

class TestOrganizationServiceAdapter:
    def _make_adapter(self):
        from apps.organization.services.organization_service_adapter import OrganizationServiceAdapter
        adapter = OrganizationServiceAdapter.__new__(OrganizationServiceAdapter)
        adapter._account_credential_service = MagicMock()
        adapter._lawfirm_service = None
        adapter._team_service = None
        adapter._lawyer_service = None
        return adapter

    def test_get_law_firm_found(self):
        adapter = self._make_adapter()
        mock_lawfirm = MagicMock()
        mock_lawfirm.id = 1
        mock_lawfirm.name = "Test Firm"
        adapter._lawfirm_service = MagicMock()
        adapter._lawfirm_service.get_lawfirm_by_id.return_value = mock_lawfirm
        with patch("apps.organization.services.organization_service_adapter.LawFirmDTO") as MockDTO:
            MockDTO.from_model.return_value = MagicMock()
            result = adapter.get_law_firm(1)
        assert result is not None

    def test_get_law_firm_not_found(self):
        adapter = self._make_adapter()
        adapter._lawfirm_service = MagicMock()
        adapter._lawfirm_service.get_lawfirm_by_id.return_value = None
        assert adapter.get_law_firm(999) is None

    def test_get_team_found(self):
        adapter = self._make_adapter()
        adapter._team_service = MagicMock()
        adapter._team_service.get_team.return_value = MagicMock()
        with patch("apps.organization.services.organization_service_adapter.TeamDTO") as MockDTO:
            MockDTO.from_model.return_value = MagicMock()
            result = adapter.get_team(1)
        assert result is not None

    def test_get_team_not_found(self):
        adapter = self._make_adapter()
        adapter._team_service = MagicMock()
        from apps.core.exceptions import NotFoundError
        adapter._team_service.get_team.side_effect = NotFoundError("not found")
        assert adapter.get_team(999) is None

    def test_get_lawyers_in_organization(self):
        adapter = self._make_adapter()
        adapter._lawyer_service = MagicMock()
        adapter._lawyer_service.list_lawyers.return_value = []
        with patch("apps.organization.services.organization_service_adapter._assembler") as mock_asm:
            result = adapter.get_lawyers_in_organization(1)
        assert result == []
        adapter._lawyer_service.list_lawyers.assert_called_once()

    def test_get_all_credentials(self):
        adapter = self._make_adapter()
        adapter._account_credential_service.list_all_credentials.return_value = []
        with patch("apps.organization.services.organization_service_adapter.AccountCredentialDTO") as MockDTO:
            result = adapter.get_all_credentials()
        assert result == []

    def test_get_credential(self):
        adapter = self._make_adapter()
        adapter._account_credential_service.get_credential_by_id.return_value = MagicMock()
        with patch("apps.organization.services.organization_service_adapter.AccountCredentialDTO") as MockDTO:
            MockDTO.from_model.return_value = MagicMock()
            result = adapter.get_credential(1)
        assert result is not None

    def test_get_credentials_by_site(self):
        adapter = self._make_adapter()
        adapter._account_credential_service.get_credentials_by_site.return_value = []
        with patch("apps.organization.services.organization_service_adapter.AccountCredentialDTO"):
            result = adapter.get_credentials_by_site("test_site")
        assert result == []

    def test_get_credential_by_account(self):
        adapter = self._make_adapter()
        adapter._account_credential_service.get_credential_by_account.return_value = MagicMock()
        with patch("apps.organization.services.organization_service_adapter.AccountCredentialDTO") as MockDTO:
            MockDTO.from_model.return_value = MagicMock()
            result = adapter.get_credential_by_account("user1", "site1")
        assert result is not None

    def test_update_login_success_delegates(self):
        adapter = self._make_adapter()
        adapter.update_login_success(5)
        adapter._account_credential_service.update_login_success.assert_called_once_with(5)

    def test_update_login_failure_delegates(self):
        adapter = self._make_adapter()
        adapter.update_login_failure(5)
        adapter._account_credential_service.update_login_failure.assert_called_once_with(5)

    def test_get_lawyer_by_id_found(self):
        adapter = self._make_adapter()
        adapter._lawyer_service = MagicMock()
        adapter._lawyer_service.get_lawyer_by_id.return_value = MagicMock()
        with patch("apps.organization.services.organization_service_adapter._assembler") as mock_asm:
            mock_asm.to_dto.return_value = MagicMock()
            result = adapter.get_lawyer_by_id(1)
        assert result is not None

    def test_get_lawyer_by_id_not_found(self):
        adapter = self._make_adapter()
        adapter._lawyer_service = MagicMock()
        adapter._lawyer_service.get_lawyer_by_id.return_value = None
        assert adapter.get_lawyer_by_id(999) is None

    def test_get_default_lawyer_id_admin_first(self):
        adapter = self._make_adapter()
        adapter._lawyer_service = MagicMock()
        admin = MagicMock()
        admin.id = 42
        qs = MagicMock()
        qs.filter.return_value.order_by.return_value.first.return_value = admin
        adapter._lawyer_service.get_lawyer_queryset.return_value = qs
        assert adapter.get_default_lawyer_id() == 42

    def test_get_default_lawyer_id_fallback(self):
        adapter = self._make_adapter()
        adapter._lawyer_service = MagicMock()
        fallback = MagicMock()
        fallback.id = 7
        qs = MagicMock()
        qs.filter.return_value.order_by.return_value.first.return_value = None
        qs.order_by.return_value.first.return_value = fallback
        adapter._lawyer_service.get_lawyer_queryset.return_value = qs
        assert adapter.get_default_lawyer_id() == 7

    def test_get_default_lawyer_id_none(self):
        adapter = self._make_adapter()
        adapter._lawyer_service = MagicMock()
        qs = MagicMock()
        qs.filter.return_value.order_by.return_value.first.return_value = None
        qs.order_by.return_value.first.return_value = None
        adapter._lawyer_service.get_lawyer_queryset.return_value = qs
        assert adapter.get_default_lawyer_id() is None

    def test_has_credential_for_lawyer_true(self):
        adapter = self._make_adapter()
        cred = MagicMock()
        cred.lawyer_id = 1
        adapter._account_credential_service.get_credentials_by_site.return_value = [cred]
        assert adapter.has_credential_for_lawyer(1, "site") is True

    def test_has_credential_for_lawyer_false(self):
        adapter = self._make_adapter()
        adapter._account_credential_service.get_credentials_by_site.return_value = []
        assert adapter.has_credential_for_lawyer(1, "site") is False

    def test_get_credential_for_lawyer_found(self):
        adapter = self._make_adapter()
        cred = MagicMock()
        cred.lawyer_id = 1
        adapter._account_credential_service.get_credentials_by_site.return_value = [cred]
        mock_dto = MagicMock()
        mock_dto.lawyer_id = 1
        with patch("apps.organization.services.organization_service_adapter.AccountCredentialDTO") as MockDTO:
            MockDTO.from_model.return_value = mock_dto
            result = adapter.get_credential_for_lawyer(1, "site")
        assert result is mock_dto

    def test_get_credential_for_lawyer_not_found(self):
        adapter = self._make_adapter()
        adapter._account_credential_service.get_credentials_by_site.return_value = []
        assert adapter.get_credential_for_lawyer(99, "site") is None

    def test_list_sites_for_lawyer(self):
        adapter = self._make_adapter()
        adapter._account_credential_service.list_sites_for_lawyer.return_value = ["s1", "s2"]
        assert adapter.list_sites_for_lawyer(1) == ["s1", "s2"]

    def test_internal_delegates(self):
        adapter = self._make_adapter()
        adapter._account_credential_service.list_all_credentials.return_value = []
        adapter._account_credential_service.get_credential_by_id.return_value = MagicMock()
        adapter._account_credential_service.get_credentials_by_site.return_value = []
        adapter._account_credential_service.get_credential_by_account.return_value = MagicMock()
        adapter._account_credential_service.list_sites_for_lawyer.return_value = []
        adapter._lawyer_service = MagicMock()
        adapter._lawyer_service.get_lawyer_by_id.return_value = None
        adapter._lawyer_service.get_lawyer_queryset.return_value.filter.return_value.order_by.return_value.first.return_value = None
        with patch("apps.organization.services.organization_service_adapter.AccountCredentialDTO") as MockDTO:
            MockDTO.from_model.return_value = MagicMock()
            adapter.get_all_credentials_internal()
            adapter.get_credential_internal(1)
            adapter.get_credentials_by_site_internal("s1")
            adapter.get_credential_by_account_internal("a", "s1")
            adapter.update_login_success_internal(1)
            adapter.update_login_failure_internal(1)
            adapter.get_lawyer_by_id_internal(1)
            adapter.get_default_lawyer_id_internal()


    def test_lazy_property_init(self):
        from apps.organization.services.organization_service_adapter import OrganizationServiceAdapter
        adapter = OrganizationServiceAdapter()
        assert adapter._lawfirm_service is None
        assert adapter._team_service is None
        assert adapter._lawyer_service is None
