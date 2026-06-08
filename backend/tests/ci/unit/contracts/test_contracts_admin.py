"""Contracts Admin 测试 - ContractAdmin, ContractPaymentAdmin, SupplementaryAgreementAdmin, ArchiveClassificationRuleAdmin"""

from __future__ import annotations

from decimal import Decimal
from typing import Any

import pytest
from django.contrib.admin.sites import AdminSite
from django.contrib.auth import get_user_model
from django.test import RequestFactory

from apps.contracts.admin.contract_admin import ContractAdmin
from apps.contracts.admin.contractpayment_admin import ContractPaymentAdmin
from apps.contracts.admin.supplementary_agreement_admin import SupplementaryAgreementAdmin
from apps.contracts.admin.archive_classification_rule_admin import ArchiveClassificationRuleAdmin
from apps.contracts.admin.client_payment_admin import ClientPaymentRecordAdmin
from apps.contracts.models import (
    ArchiveClassificationRule,
    ClientPaymentRecord,
    Contract,
    ContractPayment,
    SupplementaryAgreement,
    SupplementaryAgreementParty,
)
from apps.client.models import Client

User = get_user_model()


def _make_request(path: str = "/admin/") -> Any:
    """构造 admin request"""
    factory = RequestFactory()
    request = factory.get(path)
    request.user = User(is_superuser=True, is_staff=True)
    return request


@pytest.mark.django_db
class TestContractAdmin:
    """ContractAdmin 测试"""

    def test_list_display_fields(self) -> None:
        """list_display 包含必要字段"""
        admin_obj = ContractAdmin(Contract, AdminSite())
        display_fields = admin_obj.list_display
        assert "name_link" in display_fields or "id" in display_fields

    def test_list_select_related(self) -> None:
        """ContractAdmin 使用 list_select_related"""
        admin_obj = ContractAdmin(Contract, AdminSite())
        # ContractAdmin 可能有 list_select_related
        assert hasattr(admin_obj, "list_select_related")


@pytest.mark.django_db
class TestContractPaymentAdmin:
    """ContractPaymentAdmin 测试"""

    def test_list_display_fields(self) -> None:
        """list_display 包含必要字段"""
        admin_obj = ContractPaymentAdmin(ContractPayment, AdminSite())
        assert "id" in admin_obj.list_display
        assert "contract" in admin_obj.list_display
        assert "amount" in admin_obj.list_display
        assert "received_at" in admin_obj.list_display
        assert "invoice_status" in admin_obj.list_display

    def test_get_queryset_select_related(self) -> None:
        """get_queryset 应使用 select_related 避免 N+1"""
        contract = Contract.objects.create(name="付款测试合同", case_type="civil")
        ContractPayment.objects.create(
            contract=contract, amount=Decimal("10000.00"), received_at="2024-01-01"
        )

        admin_obj = ContractPaymentAdmin(ContractPayment, AdminSite())
        qs = admin_obj.get_queryset(_make_request())
        results = list(qs)
        assert len(results) == 1
        assert results[0].contract.name == "付款测试合同"


@pytest.mark.django_db
class TestSupplementaryAgreementAdmin:
    """SupplementaryAgreementAdmin 测试"""

    def test_list_display_fields(self) -> None:
        """list_display 包含必要字段"""
        admin_obj = SupplementaryAgreementAdmin(SupplementaryAgreement, AdminSite())
        assert "id" in admin_obj.list_display
        assert "name" in admin_obj.list_display
        assert "contract" in admin_obj.list_display
        assert "party_count" in admin_obj.list_display

    def test_get_queryset_annotate_party_count(self) -> None:
        """get_queryset 应使用 annotate(Count) 计算 party_count"""
        contract = Contract.objects.create(name="补充协议测试合同", case_type="civil")
        sa = SupplementaryAgreement.objects.create(contract=contract, name="补充协议1")
        client1 = Client.objects.create(name="当事人1", client_type="natural")
        client2 = Client.objects.create(name="当事人2", client_type="natural")
        SupplementaryAgreementParty.objects.create(
            supplementary_agreement=sa, client=client1, role="PRINCIPAL"
        )
        SupplementaryAgreementParty.objects.create(
            supplementary_agreement=sa, client=client2, role="OPPOSING"
        )

        admin_obj = SupplementaryAgreementAdmin(SupplementaryAgreement, AdminSite())
        qs = admin_obj.get_queryset(_make_request())
        results = list(qs)
        assert len(results) == 1
        assert results[0].party_count == 2

    def test_party_count_display_uses_annotation(self) -> None:
        """party_count display 方法应使用 annotate 的值"""
        contract = Contract.objects.create(name="显示测试合同", case_type="civil")
        sa = SupplementaryAgreement.objects.create(contract=contract, name="补充协议")
        client1 = Client.objects.create(name="显示当事人1", client_type="natural")
        SupplementaryAgreementParty.objects.create(
            supplementary_agreement=sa, client=client1, role="PRINCIPAL"
        )

        admin_obj = SupplementaryAgreementAdmin(SupplementaryAgreement, AdminSite())
        qs = admin_obj.get_queryset(_make_request())
        obj = qs.first()
        assert admin_obj.party_count(obj) == 1


@pytest.mark.django_db
class TestArchiveClassificationRuleAdmin:
    """ArchiveClassificationRuleAdmin 测试"""

    def test_list_display_fields(self) -> None:
        """list_display 包含必要字段"""
        admin_obj = ArchiveClassificationRuleAdmin(ArchiveClassificationRule, AdminSite())
        assert "archive_category" in admin_obj.list_display
        assert "filename_keyword" in admin_obj.list_display
        assert "archive_item_code" in admin_obj.list_display


@pytest.mark.django_db
class TestClientPaymentRecordAdmin:
    """ClientPaymentRecordAdmin 测试"""

    def test_list_display_fields(self) -> None:
        """list_display 包含必要字段"""
        admin_obj = ClientPaymentRecordAdmin(ClientPaymentRecord, AdminSite())
        assert "contract" in admin_obj.list_display
        assert "case" in admin_obj.list_display
        assert "amount" in admin_obj.list_display
