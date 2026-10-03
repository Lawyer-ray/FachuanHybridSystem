"""数据完整性约束与 PROTECT 行为测试（P1）。

两个行为主题：
- 唯一约束兜底导入幂等：绕过 service 的直接重复写入必须被 DB 拒绝
  （IntegrityError），而非静默落两条——这是并发/重复导入不产生重复
  收款/发票/证件的最后防线
- 律师删除保护：有指派/授权记录的律师删除被 PROTECT 拦截（办案历史
  不得随删人静默消失），清空指派后可删
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal

import pytest
from django.db import IntegrityError, transaction
from django.db.models import ProtectedError

from apps.cases.models import CaseAccessGrant, CaseAssignment
from apps.client.models import ClientIdentityDoc
from apps.contracts.models import ContractAssignment, ContractPayment, Invoice, SupplementaryAgreement
from apps.testing.factories import CaseFactory, ClientFactory, ContractFactory, LawyerFactory


@pytest.mark.django_db
class TestUniqueConstraintGuards:
    def test_duplicate_payment_rejected(self):
        contract = ContractFactory()
        ContractPayment.objects.create(
            contract=contract, amount=Decimal("100"), received_at=date(2026, 1, 1)
        )
        with pytest.raises(IntegrityError):
            with transaction.atomic():
                ContractPayment.objects.create(
                    contract=contract, amount=Decimal("100"), received_at=date(2026, 1, 1)
                )

    def test_distinct_payments_still_allowed(self):
        """同合同同日不同金额、或同金额不同日，是合法业务数据。"""
        contract = ContractFactory()
        ContractPayment.objects.create(
            contract=contract, amount=Decimal("100"), received_at=date(2026, 1, 1)
        )
        ContractPayment.objects.create(
            contract=contract, amount=Decimal("200"), received_at=date(2026, 1, 1)
        )
        ContractPayment.objects.create(
            contract=contract, amount=Decimal("100"), received_at=date(2026, 2, 1)
        )
        assert ContractPayment.objects.filter(contract=contract).count() == 3

    def test_duplicate_invoice_file_rejected(self):
        contract = ContractFactory()
        payment = ContractPayment.objects.create(
            contract=contract, amount=Decimal("1"), received_at=date(2026, 1, 1)
        )
        Invoice.objects.create(payment=payment, file_path="invoices/a.pdf")
        with pytest.raises(IntegrityError):
            with transaction.atomic():
                Invoice.objects.create(payment=payment, file_path="invoices/a.pdf")

    def test_duplicate_identity_doc_type_rejected(self):
        client = ClientFactory(client_type="legal", legal_representative="r")
        ClientIdentityDoc.objects.create(client=client, doc_type="business_license")
        with pytest.raises(IntegrityError):
            with transaction.atomic():
                ClientIdentityDoc.objects.create(client=client, doc_type="business_license")

    def test_duplicate_supplementary_name_rejected_but_blank_exempt(self):
        """具名补充协议同合同唯一；未命名（空串）允许多份。"""
        contract = ContractFactory()
        SupplementaryAgreement.objects.create(contract=contract, name="补充协议一")
        with pytest.raises(IntegrityError):
            with transaction.atomic():
                SupplementaryAgreement.objects.create(contract=contract, name="补充协议一")
        SupplementaryAgreement.objects.create(contract=contract, name="")
        SupplementaryAgreement.objects.create(contract=contract, name="")
        assert contract.supplementary_agreements.count() == 3


@pytest.mark.django_db
class TestLawyerDeleteProtection:
    def test_case_assignment_blocks_delete(self):
        lawyer = LawyerFactory()
        case = CaseFactory()
        CaseAssignment.objects.create(case=case, lawyer=lawyer)
        with pytest.raises(ProtectedError):
            lawyer.delete()

    def test_contract_assignment_blocks_delete(self):
        lawyer = LawyerFactory()
        contract = ContractFactory()
        ContractAssignment.objects.create(contract=contract, lawyer=lawyer)
        with pytest.raises(ProtectedError):
            lawyer.delete()

    def test_access_grant_blocks_delete(self):
        lawyer = LawyerFactory()
        case = CaseFactory()
        CaseAccessGrant.objects.create(case=case, grantee=lawyer)
        with pytest.raises(ProtectedError):
            lawyer.delete()

    def test_deletable_after_transfer(self):
        """转办清空指派后可删——PROTECT 挡的是静默丢失，不是禁止离职。"""
        lawyer = LawyerFactory()
        case = CaseFactory()
        assignment = CaseAssignment.objects.create(case=case, lawyer=lawyer)
        with transaction.atomic():
            assignment.delete()
        lawyer.delete()
        assert not CaseAssignment.objects.filter(case=case).exists()
