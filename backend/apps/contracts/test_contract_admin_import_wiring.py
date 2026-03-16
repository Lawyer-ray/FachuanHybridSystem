"""Regression tests for contract admin import wiring."""

from __future__ import annotations

import pytest
from django.contrib.admin.sites import AdminSite

from apps.cases.models import Case
from apps.contracts.admin.contract_admin import ContractAdmin
from apps.contracts.models import Contract


@pytest.mark.django_db
def test_contract_admin_handle_json_import_keeps_case_binding_behavior() -> None:
    admin_obj = ContractAdmin(Contract, AdminSite())

    success, skipped, errors = admin_obj.handle_json_import(
        data_list=[
            {
                "name": "admin-import-contract",
                "case_type": "civil",
                "cases": [{"name": "imported-from-contract-admin"}],
            }
        ],
        user="tester",
        zip_file=None,
    )

    contract = Contract.objects.get(name="admin-import-contract")
    imported_case = Case.objects.get(name="imported-from-contract-admin")

    assert success == 1
    assert skipped == 0
    assert errors == []
    assert imported_case.contract_id == contract.id
