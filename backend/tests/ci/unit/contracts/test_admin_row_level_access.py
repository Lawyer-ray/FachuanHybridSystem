"""Contracts Admin 行级访问控制测试（审计五-2 专项）.

覆盖：合同详情页行级校验、关联 ModelAdmin（收款记录）列表行级过滤。
2026-10-19 安全审计补充：contract FK 表单可选项行级过滤、save_model 二次校验、
自定义 AJAX/批量视图行级校验。
"""

from __future__ import annotations

import json
from decimal import Decimal
from typing import Any
from unittest.mock import MagicMock

import pytest
from django.contrib.admin.sites import AdminSite
from django.contrib.auth import get_user_model
from django.contrib.auth.models import Permission
from django.core.exceptions import PermissionDenied
from django.test import RequestFactory

from apps.contracts.admin.client_payment_admin import ClientPaymentRecordAdmin
from apps.contracts.admin.contract_admin import ContractAdmin
from apps.contracts.admin.contractpayment_admin import ContractPaymentAdmin
from apps.contracts.admin.supplementary_agreement_admin import SupplementaryAgreementAdmin
from apps.contracts.models import (
    ClientPaymentRecord,
    Contract,
    ContractAssignment,
    ContractPayment,
    SupplementaryAgreement,
)
from apps.organization.models import Lawyer

User = get_user_model()


def _grant_contract_perm(user: Lawyer, codename: str) -> Lawyer:
    """授予 contracts 应用的模型权限并重取用户（刷新权限缓存）。"""
    user.user_permissions.add(
        Permission.objects.get(content_type__app_label="contracts", codename=codename),
    )
    refreshed = User.objects.get(pk=user.pk)
    return refreshed  # type: ignore[no-any-return]


def _make_request(path: str, user: Any, *, method: str = "get", data: Any = None) -> Any:
    factory = RequestFactory()
    if method == "post":
        request = factory.post(path, data=data, content_type="application/json")
    else:
        request = factory.get(path, data=data)
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
class TestContractForeignKeyRowFilter:
    """安全审计（2026-10-19）：关联 Admin 的 contract FK 表单可选项行级过滤 + save_model 二次校验"""

    def _setup_contracts(self) -> tuple[Contract, Contract, Lawyer]:
        mine = Contract.objects.create(name="我可访问合同", case_type="civil")
        other = Contract.objects.create(name="他人合同F", case_type="civil")
        staff = Lawyer.objects.create_user(username="fk_staff", real_name="表单过滤律师", is_staff=True)
        ContractAssignment.objects.create(contract=mine, lawyer=staff)
        return mine, other, staff

    @pytest.mark.parametrize(
        ("admin_cls", "model_cls"),
        [
            (ContractPaymentAdmin, ContractPayment),
            (ClientPaymentRecordAdmin, ClientPaymentRecord),
            (SupplementaryAgreementAdmin, SupplementaryAgreement),
        ],
    )
    def test_formfield_for_foreignkey_filters_contract_choices(self, admin_cls: Any, model_cls: Any) -> None:
        """contract FK 下拉可选项仅含行级可访问合同（口径同 get_queryset）"""
        mine, other, staff = self._setup_contracts()
        request = _make_request(f"/admin/contracts/{model_cls._meta.model_name}/", staff)

        field = admin_cls(model_cls, AdminSite()).formfield_for_foreignkey(
            model_cls._meta.get_field("contract"), request
        )

        assert set(field.queryset.values_list("id", flat=True)) == {mine.pk}

    def test_save_model_denies_inaccessible_contract(self) -> None:
        """保存时对 obj.contract 二次校验：无权合同 → PermissionDenied，不落库"""
        _mine, other, staff = self._setup_contracts()
        request = _make_request("/admin/contracts/clientpaymentrecord/", staff)
        obj = ClientPaymentRecord(contract=other, amount=Decimal("100.00"))

        with pytest.raises(PermissionDenied):
            ClientPaymentRecordAdmin(ClientPaymentRecord, AdminSite()).save_model(request, obj, MagicMock(), False)

    def test_get_cases_by_contract_view_denies_inaccessible_contract(self) -> None:
        """AJAX 案件列表端点对 contract_id 补行级校验：无权合同 → 403"""
        _mine, other, staff = self._setup_contracts()
        staff = _grant_contract_perm(staff, "view_clientpaymentrecord")
        request = _make_request(
            "/admin/contracts/clientpaymentrecord/get-cases-by-contract/", staff, data={"contract_id": str(other.pk)}
        )

        with pytest.raises(PermissionDenied):
            ClientPaymentRecordAdmin(ClientPaymentRecord, AdminSite()).get_cases_by_contract_view(request)

    def test_get_cases_by_contract_view_allows_accessible_contract(self) -> None:
        mine, _other, staff = self._setup_contracts()
        staff = _grant_contract_perm(staff, "view_clientpaymentrecord")
        request = _make_request(
            "/admin/contracts/clientpaymentrecord/get-cases-by-contract/", staff, data={"contract_id": str(mine.pk)}
        )

        response = ClientPaymentRecordAdmin(ClientPaymentRecord, AdminSite()).get_cases_by_contract_view(request)

        assert response.status_code == 200
        assert json.loads(response.content) == {"cases": []}


@pytest.mark.django_db
class TestContractAdminCustomViewsRowLevel:
    """安全审计（2026-10-19）：contract_admin 自定义视图补行级校验"""

    def _setup(self) -> tuple[Contract, Contract, Lawyer]:
        mine = Contract.objects.create(name="批量视图可访问合同", case_type="civil")
        other = Contract.objects.create(name="批量视图他人合同", case_type="civil")
        staff = _grant_contract_perm(
            Lawyer.objects.create_user(username="cv_staff", real_name="批量视图律师", is_staff=True),
            "change_contract",
        )
        ContractAssignment.objects.create(contract=mine, lawyer=staff)
        return mine, other, staff

    def test_reorder_materials_view_denies_inaccessible_contract(self) -> None:
        _mine, other, staff = self._setup()
        request = _make_request(
            f"/admin/contracts/contract/{other.pk}/reorder-materials/",
            staff,
            method="post",
            data=json.dumps({"ids": [1]}),
        )

        with pytest.raises(PermissionDenied):
            ContractAdmin(Contract, AdminSite()).reorder_materials_view(request, other.pk)

    def test_oa_sync_save_view_denies_inaccessible_contract(self) -> None:
        _mine, other, staff = self._setup()
        request = _make_request(
            "/admin/contracts/contract/oa-sync/save/",
            staff,
            method="post",
            data=json.dumps({"entries": [{"id": other.pk, "law_firm_oa_case_number": "X-1"}]}),
        )

        with pytest.raises(PermissionDenied):
            ContractAdmin(Contract, AdminSite()).oa_sync_save_view(request)

    def test_batch_folder_binding_save_view_denies_inaccessible_contract(self) -> None:
        _mine, other, staff = self._setup()
        request = _make_request(
            "/admin/contracts/contract/batch-folder-binding/save/",
            staff,
            method="post",
            data=json.dumps({"case_type_roots": [], "contract_selections": [{"contract_id": other.pk, "apply": True}]}),
        )

        with pytest.raises(PermissionDenied):
            ContractAdmin(Contract, AdminSite()).batch_folder_binding_save_view(request)

    def test_batch_folder_binding_preview_filters_rows_by_access(self, tmp_path: Any) -> None:
        """预览行按行级 queryset 过滤：仅返回可访问合同（契约：rows[].contract_id）"""
        from apps.contracts.admin.access import get_admin_accessible_contract_queryset
        from apps.contracts.services.contract.integrations.batch_folder_binding_service import (
            ContractBatchFolderBindingService,
        )

        mine, other, staff = self._setup()
        mine.case_type = "civil"
        mine.save(update_fields=["case_type"])
        other.case_type = "civil"
        other.save(update_fields=["case_type"])
        request = _make_request("/admin/contracts/contract/batch-folder-binding/preview/", staff)

        accessible_ids = set(get_admin_accessible_contract_queryset(request).values_list("id", flat=True))
        assert accessible_ids == {mine.pk}  # 前置断言：行级 queryset 本身正确

        result = ContractBatchFolderBindingService().preview(
            case_type_roots=[{"case_type": "civil", "root_path": str(tmp_path)}],
            contract_qs=get_admin_accessible_contract_queryset(request),
        )

        row_contract_ids = {row["contract_id"] for item in result["items"] for row in item["rows"]}
        assert row_contract_ids == {mine.pk}


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
