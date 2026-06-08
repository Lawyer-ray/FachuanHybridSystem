"""Contracts Model 测试 - Contract, ContractPayment, SupplementaryAgreement, ClientPaymentRecord"""

from __future__ import annotations

from datetime import date
from decimal import Decimal
from typing import Any

import pytest
from django.utils import timezone

from apps.contracts.models import (
    Contract,
    ContractPayment,
    SupplementaryAgreement,
    SupplementaryAgreementParty,
    ClientPaymentRecord,
    ArchiveClassificationRule,
    ContractParty,
    PartyRole,
    InvoiceStatus,
)
from apps.client.models import Client


@pytest.mark.django_db
class TestContractModel:
    """Contract 模型测试"""

    def test_str_representation(self) -> None:
        """__str__ 应返回合同名称"""
        contract = Contract.objects.create(name="测试合同", case_type="civil")
        assert str(contract) == "测试合同"

    def test_create_contract_with_status(self) -> None:
        """创建合同指定状态"""
        contract = Contract.objects.create(name="状态合同", case_type="civil", status="active")
        assert contract.status == "active"

    def test_create_contract_with_case_type(self) -> None:
        """创建合同指定案件类型"""
        contract = Contract.objects.create(name="类型合同", case_type="criminal")
        assert contract.case_type == "criminal"


@pytest.mark.django_db
class TestContractPaymentModel:
    """ContractPayment 模型测试"""

    def test_str_representation(self) -> None:
        """__str__ 应返回收款信息"""
        contract = Contract.objects.create(name="收款测试合同", case_type="civil")
        payment = ContractPayment.objects.create(
            contract=contract, amount=Decimal("50000.00"), received_at=date(2024, 1, 1)
        )
        assert "50000" in str(payment)

    def test_create_payment_with_invoice_status(self) -> None:
        """创建收款指定开票状态"""
        contract = Contract.objects.create(name="开票测试合同", case_type="civil")
        payment = ContractPayment.objects.create(
            contract=contract,
            amount=Decimal("10000.00"),
            received_at=date(2024, 1, 1),
            invoice_status=InvoiceStatus.INVOICED_FULL,
            invoiced_amount=Decimal("10000.00"),
        )
        assert payment.invoice_status == InvoiceStatus.INVOICED_FULL

    def test_default_invoice_status(self) -> None:
        """默认开票状态应为未开票"""
        contract = Contract.objects.create(name="默认开票合同", case_type="civil")
        payment = ContractPayment.objects.create(
            contract=contract, amount=Decimal("5000.00"), received_at=date(2024, 1, 1)
        )
        assert payment.invoice_status == InvoiceStatus.UNINVOICED


@pytest.mark.django_db
class TestSupplementaryAgreementModel:
    """SupplementaryAgreement 模型测试"""

    def test_str_representation(self) -> None:
        """__str__ 应返回补充协议信息"""
        contract = Contract.objects.create(name="补充协议测试合同", case_type="civil")
        sa = SupplementaryAgreement.objects.create(contract=contract, name="补充协议1")
        assert "补充协议1" in str(sa)
        assert str(contract.id) in str(sa)

    def test_str_representation_unnamed(self) -> None:
        """__str__ 未命名补充协议"""
        contract = Contract.objects.create(name="未命名测试合同", case_type="civil")
        sa = SupplementaryAgreement.objects.create(contract=contract)
        assert "未命名补充协议" in str(sa)

    def test_create_party(self) -> None:
        """创建补充协议当事人"""
        contract = Contract.objects.create(name="当事人测试合同", case_type="civil")
        sa = SupplementaryAgreement.objects.create(contract=contract, name="当事人补充协议")
        client = Client.objects.create(name="补充协议当事人", client_type="natural")
        party = SupplementaryAgreementParty.objects.create(
            supplementary_agreement=sa, client=client, role=PartyRole.OPPOSING
        )
        assert party.role == PartyRole.OPPOSING
        assert party.supplementary_agreement == sa

    def test_party_str_representation(self) -> None:
        """补充协议当事人 __str__"""
        contract = Contract.objects.create(name="当事人显示合同", case_type="civil")
        sa = SupplementaryAgreement.objects.create(contract=contract, name="显示补充协议")
        client = Client.objects.create(name="显示当事人", client_type="natural")
        party = SupplementaryAgreementParty.objects.create(
            supplementary_agreement=sa, client=client, role=PartyRole.PRINCIPAL
        )
        result = str(party)
        assert str(sa.id) in result
        assert str(client.id) in result


@pytest.mark.django_db
class TestClientPaymentRecordModel:
    """ClientPaymentRecord 模型测试"""

    def test_str_representation(self) -> None:
        """__str__ 应返回回款信息"""
        contract = Contract.objects.create(name="回款测试合同", case_type="civil")
        record = ClientPaymentRecord.objects.create(
            contract=contract, amount=Decimal("30000.00")
        )
        assert "30000" in str(record)

    def test_create_record_with_case(self) -> None:
        """创建回款记录关联案件"""
        from apps.cases.models import Case

        contract = Contract.objects.create(name="案件回款合同", case_type="civil")
        case = Case.objects.create(name="回款测试案件", contract=contract)
        record = ClientPaymentRecord.objects.create(
            contract=contract, case=case, amount=Decimal("20000.00")
        )
        assert record.case.name == "回款测试案件"


@pytest.mark.django_db
class TestArchiveClassificationRuleModel:
    """ArchiveClassificationRule 模型测试"""

    def test_str_representation(self) -> None:
        """__str__ 应返回规则信息"""
        rule = ArchiveClassificationRule.objects.create(
            archive_category="litigation",
            filename_keyword="起诉状",
            archive_item_code="lt_1",
        )
        result = str(rule)
        assert "litigation" in result
        assert "起诉状" in result
        assert "lt_1" in result

    def test_unique_together(self) -> None:
        """archive_category 和 filename_keyword 应唯一"""
        ArchiveClassificationRule.objects.create(
            archive_category="litigation", filename_keyword="起诉状", archive_item_code="lt_1"
        )
        with pytest.raises(Exception):  # noqa: B017
            ArchiveClassificationRule.objects.create(
                archive_category="litigation", filename_keyword="起诉状", archive_item_code="lt_2"
            )


@pytest.mark.django_db
class TestContractPartyModel:
    """ContractParty 模型测试"""

    def test_create_party(self) -> None:
        """创建合同当事人"""
        contract = Contract.objects.create(name="合同当事人测试", case_type="civil")
        client = Client.objects.create(name="合同当事人", client_type="natural")
        party = ContractParty.objects.create(
            contract=contract, client=client, role=PartyRole.PRINCIPAL
        )
        assert party.role == PartyRole.PRINCIPAL
        assert party.contract == contract
