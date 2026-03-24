from __future__ import annotations

import pytest
from django.contrib.admin.sites import AdminSite

from apps.contracts.admin.contract_admin import ContractAdmin
from apps.contracts.models import Contract, ContractAssignment
from apps.organization.models import AccountCredential


@pytest.mark.django_db
def test_contract_admin_shows_law_firm_oa_link(contract, lawyer) -> None:
    ContractAssignment.objects.create(contract=contract, lawyer=lawyer, is_primary=True)
    AccountCredential.objects.create(
        lawyer=lawyer,
        site_name="金诚同达OA",
        url="https://oa.example.com/login",
        account="oa-user",
        password="oa-pass",
    )

    admin = ContractAdmin(Contract, AdminSite())
    html = str(admin.law_firm_oa_link_display(contract))

    assert "oa.example.com/login" in html
    assert "打开OA系统" in html


@pytest.mark.django_db
def test_contract_admin_shows_unconfigured_when_no_oa_link(contract, lawyer) -> None:
    ContractAssignment.objects.create(contract=contract, lawyer=lawyer, is_primary=True)

    admin = ContractAdmin(Contract, AdminSite())

    assert str(admin.law_firm_oa_link_display(contract)) == "未配置"
