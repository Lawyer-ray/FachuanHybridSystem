"""Contracts Admin 行级访问控制测试（审计五-2 专项）.

覆盖：合同详情页行级校验、关联 ModelAdmin（收款记录）列表行级过滤。
"""

from __future__ import annotations

from decimal import Decimal
from typing import Any

import pytest
from django.contrib.admin.sites import AdminSite
from django.contrib.auth import get_user_model
from django.contrib.auth.models import Permission
from django.core.exceptions import PermissionDenied
from django.test import RequestFactory

from apps.contracts.admin.contract_admin import ContractAdmin
from apps.contracts.admin.contractpayment_admin import ContractPaymentAdmin
from apps.contracts.models import Contract, ContractAssignment, ContractPayment
from apps.organization.models import Lawyer

User = get_user_model()


def _grant_contract_perm(user: Lawyer, codename: str) -> Lawyer:
    """授予 contracts 应用的模型权限并重取用户（刷新权限缓存）。"""
    user.user_permissions.add(
        Permission.objects.get(content_type__app_label="contracts", codename=codename),
    )
    refreshed = User.objects.get(pk=user.pk)
    return refreshed  # type: ignore[no-any-return]


def _make_request(path: str, user: Any) -> Any:
    request = RequestFactory().get(path)
    request.user = user
    return request


@pytest.mark.django_db
class TestContractDetailRowLevelAccess:
    """合同详情页的行级权限校验"""

    def test_detail_view_denies_staff_without_contract_access(self) -> None:
        """受限 staff（有模块级查看权限但未参与合同）访问他人合同详情 → 403"""
        contract = Contract.objects.create(name="他人合同", case_type="civil")
        staff = _grant_contract_perm(
            Lawyer.objects.create_user(username="c_rl_staff", real_name="合同受限律师", is_staff=True),
            "view_contract",
        )

        request = _make_request(f"/admin/contracts/contract/{contract.pk}/detail/", staff)

        with pytest.raises(PermissionDenied):
            ContractAdmin(Contract, AdminSite()).detail_view(request, contract.pk)


@pytest.mark.django_db
class TestContractPaymentAdminRowFilter:
    """ContractPaymentAdmin 列表行级过滤（以 contract 关联 join）"""

    def test_get_queryset_filters_by_contract_access(self) -> None:
        """非管理员用户只能看到可访问合同下的收款记录"""
        mine = Contract.objects.create(name="可见合同", case_type="civil")
        other = Contract.objects.create(name="他人合同2", case_type="civil")
        ContractPayment.objects.create(contract=mine, amount=Decimal("100.00"), received_at="2024-01-01")
        ContractPayment.objects.create(contract=other, amount=Decimal("200.00"), received_at="2024-01-02")
        staff = Lawyer.objects.create_user(username="pay_staff", real_name="收款律师")
        ContractAssignment.objects.create(contract=mine, lawyer=staff)

        request = _make_request("/admin/contracts/contractpayment/", staff)

        qs = ContractPaymentAdmin(ContractPayment, AdminSite()).get_queryset(request)
        assert set(qs.values_list("contract_id", flat=True)) == {mine.pk}

    def test_get_queryset_admin_sees_all(self) -> None:
        """is_admin（superuser）用户看到全部收款记录"""
        mine = Contract.objects.create(name="可见合同B", case_type="civil")
        other = Contract.objects.create(name="他人合同B", case_type="civil")
        ContractPayment.objects.create(contract=mine, amount=Decimal("1.00"), received_at="2024-01-01")
        ContractPayment.objects.create(contract=other, amount=Decimal("2.00"), received_at="2024-01-02")

        request = _make_request(
            "/admin/contracts/contractpayment/",
            User(is_superuser=True, is_staff=True, is_admin=True),
        )

        qs = ContractPaymentAdmin(ContractPayment, AdminSite()).get_queryset(request)
        assert qs.count() == 2
