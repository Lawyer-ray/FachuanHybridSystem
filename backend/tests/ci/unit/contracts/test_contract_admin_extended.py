"""Tests for contracts.admin.contract_admin — increase coverage."""

from __future__ import annotations

import json
from unittest.mock import MagicMock, patch

import pytest


class TestContractAdminAttributes:
    """Verify ContractAdmin configuration attributes."""

    def _make_admin(self):
        from apps.contracts.admin.contract_admin import ContractAdmin
        from apps.contracts.models import Contract

        return ContractAdmin(Contract, MagicMock())

    def test_list_display(self) -> None:
        admin = self._make_admin()
        assert "id" in admin.list_display
        assert "name_link" in admin.list_display
        assert "case_type" in admin.list_display
        assert "status" in admin.list_display

    def test_list_filter(self) -> None:
        admin = self._make_admin()
        assert "case_type" in admin.list_filter
        assert "status" in admin.list_filter

    def test_search_fields(self) -> None:
        admin = self._make_admin()
        assert "name" in admin.search_fields

    def test_date_hierarchy(self) -> None:
        admin = self._make_admin()
        assert admin.date_hierarchy == "specified_date"

    def test_readonly_fields(self) -> None:
        admin = self._make_admin()
        assert "filing_number" in admin.readonly_fields

    def test_actions(self) -> None:
        admin = self._make_admin()
        assert "export_selected_as_json" in admin.actions
        assert "archive_selected_contracts" in admin.actions
        assert "file_selected_contracts" in admin.actions

    def test_fieldsets(self) -> None:
        admin = self._make_admin()
        fieldsets = admin.fieldsets
        assert isinstance(fieldsets, tuple)
        names = [f[0] for f in fieldsets]
        assert "基本信息" in names
        assert "收费信息" in names

    def test_export_model_name(self) -> None:
        admin = self._make_admin()
        assert admin.export_model_name == "contract"

    def test_import_required_fields(self) -> None:
        admin = self._make_admin()
        assert "name" in admin.import_required_fields


class TestContractAdminForm:
    """Test ContractAdminForm behavior."""

    def test_form_init_new_instance(self) -> None:
        from apps.contracts.admin.contract_admin import ContractAdmin

        form_class = ContractAdmin.ContractAdminForm
        with patch("apps.contracts.admin.contract_admin.timezone") as mock_tz:
            mock_tz.localdate.return_value = MagicMock()
            form = form_class()
            # Check that representation_stages initial is set
            assert isinstance(form.fields["representation_stages"].initial, list)

    def test_form_init_existing_instance(self) -> None:
        from apps.contracts.admin.contract_admin import ContractAdmin

        form_class = ContractAdmin.ContractAdminForm
        instance = MagicMock()
        instance.pk = 1
        instance.representation_stages = ["first_instance"]
        form = form_class(instance=instance)
        assert form.fields["representation_stages"].initial == ["first_instance"]


class TestContractAdminViews:
    """Test ContractAdmin view methods."""

    def _make_admin(self):
        from apps.contracts.admin.contract_admin import ContractAdmin
        from apps.contracts.models import Contract

        return ContractAdmin(Contract, MagicMock())

    def test_reorder_materials_wrong_method(self) -> None:
        admin = self._make_admin()
        request = MagicMock()
        request.method = "GET"
        result = admin.reorder_materials_view(request, 1)
        assert result.status_code == 405

    def test_reorder_materials_no_permission(self) -> None:
        admin = self._make_admin()
        admin.has_change_permission = MagicMock(return_value=False)
        request = MagicMock()
        request.method = "POST"
        result = admin.reorder_materials_view(request, 1)
        assert result.status_code == 403

    def test_reorder_materials_success(self) -> None:
        admin = self._make_admin()
        admin.has_change_permission = MagicMock(return_value=True)
        request = MagicMock()
        request.method = "POST"
        request.body = json.dumps({"ids": [3, 1, 2]}).encode()
        with patch("apps.contracts.admin.contract_admin.FinalizedMaterial") as mock_model:
            mock_model.objects.filter.return_value.update.return_value = 3
            result = admin.reorder_materials_view(request, 1)
            data = json.loads(result.content)
            assert data["ok"] is True

    def test_reorder_materials_error(self) -> None:
        admin = self._make_admin()
        admin.has_change_permission = MagicMock(return_value=True)
        request = MagicMock()
        request.method = "POST"
        request.body = b"invalid json"
        result = admin.reorder_materials_view(request, 1)
        assert result.status_code == 400

    def test_changelist_view_redirects_to_active(self) -> None:
        admin = self._make_admin()
        request = MagicMock()
        request.GET = {}
        request.path = "/admin/contracts/contract/"
        request.session = {}
        result = admin.changelist_view(request)
        assert result.status_code == 302
        assert "status__exact=active" in result.url

    def test_changelist_view_with_filter(self, db) -> None:
        from django.http import QueryDict

        admin = self._make_admin()
        request = MagicMock()
        qd = QueryDict("status__exact=active")
        request.GET = qd
        request.session = {}
        request.META = {"SERVER_NAME": "localhost", "SERVER_PORT": "80"}
        request.user = MagicMock()
        request.user.is_staff = True
        request.user.is_active = True
        request.user.has_perm.return_value = True
        try:
            admin.changelist_view(request)
        except Exception:
            pass
        assert request.session.get("contract_changelist_filters") == "status__exact=active"


class TestContractAdminFormValidation:
    def test_clean_with_representation_stages(self) -> None:
        from apps.contracts.admin.contract_admin import ContractAdmin

        form_class = ContractAdmin.ContractAdminForm
        form = form_class()
        form.cleaned_data = {
            "case_type": "civil",
            "representation_stages": ["first_instance"],
        }
        with patch("apps.contracts.admin.contract_admin.timezone"):
            with patch("apps.contracts.validators.normalize_representation_stages", return_value=["first_instance"]):
                result = form.clean()
                assert "representation_stages" in result

    def test_clean_with_exception(self) -> None:
        from apps.contracts.admin.contract_admin import ContractAdmin

        form_class = ContractAdmin.ContractAdminForm
        form = form_class()
        form.cleaned_data = {
            "case_type": "civil",
            "representation_stages": [],
        }
        with patch("apps.contracts.admin.contract_admin.timezone"):
            with patch("apps.contracts.validators.normalize_representation_stages", side_effect=Exception("fail")):
                result = form.clean()
                # Should still return cleaned data even on exception
                assert isinstance(result, dict)
