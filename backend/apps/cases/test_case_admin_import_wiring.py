"""Regression tests for case admin import wiring."""

from __future__ import annotations

import pytest
from django.contrib.admin.sites import AdminSite

from apps.cases.admin.case_admin import CaseAdmin
from apps.cases.models import Case
from apps.contracts.models import Contract


@pytest.mark.django_db
def test_case_admin_handle_json_import_keeps_contract_binding_behavior() -> None:
    admin_obj = CaseAdmin(Case, AdminSite())

    success, skipped, errors = admin_obj.handle_json_import(
        data_list=[
            {
                "name": "admin-import-case",
                "contract": {
                    "name": "admin-import-contract",
                    "case_type": "civil",
                    "cases": [{"name": "should-not-be-imported"}],
                },
            }
        ],
        user="tester",
        zip_file=None,
    )

    assert success == 1
    assert skipped == 0
    assert errors == []
    assert Case.objects.filter(name="admin-import-case").exists() is True
    assert Contract.objects.filter(name="admin-import-contract").exists() is True
    assert Case.objects.filter(name="should-not-be-imported").exists() is False


@pytest.mark.django_db
def test_case_admin_handle_json_import_collects_error_without_secondary_exception() -> None:
    admin_obj = CaseAdmin(Case, AdminSite())

    success, skipped, errors = admin_obj.handle_json_import(
        data_list=[{}],
        user="tester",
        zip_file=None,
    )

    assert success == 0
    assert skipped == 0
    assert len(errors) == 1
    assert "ValidationException" in errors[0]
