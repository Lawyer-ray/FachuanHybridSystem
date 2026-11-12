"""记账层（`_recompute_invoiced_amount`）的负金额口径。

本文件只锁一件事：**`invoiced_amount` 是净额，负数分支必须显式放行**。

为什么值得单独一个文件：这条口径没改对时，系统不会报错，只会安静地把
「已冲红、待重开」显示成「已全额开票」——此刻项目里一张有效票都没有，
而项目页说“已开满”。那是本项目最贵的一类错（账目自证清白）。

口径（已定稿，见 docs/harness/backend/invoice-intake-red.md §4.6 / §8 D-1）：

    invoiced = Sum(total_amount)            # 净额，含红票负数
    if invoiced > 0: invoiced = min(invoiced, payment.amount)   # 上限只对正数成立
    invoiced = max(invoiced, 0)             # 模型约束 chk_contractpayment_invoiced_nonneg
    invoiced == 0 且名下有红票 → VOIDED_PENDING_REISSUE（不是 UNINVOICED）
"""

from __future__ import annotations

from decimal import Decimal
from typing import Any

import pytest

from apps.contracts.models import Contract, ContractPayment, Invoice, InvoiceStatus
from apps.contracts.services.payment.invoice_file_service import InvoiceFileService
from apps.testing.factories import ContractFactory


@pytest.fixture
def contract(db: Any) -> Contract:
    return ContractFactory(name="负金额口径测试项目")


@pytest.fixture
def payment(db: Any, contract: Contract) -> ContractPayment:
    return ContractPayment.objects.create(
        contract=contract,
        amount=Decimal("10000.00"),
        invoiced_amount=Decimal("10000.00"),
        invoice_status=InvoiceStatus.INVOICED_FULL,
    )


def _invoice(payment: ContractPayment, amount: str) -> Invoice:
    """按张序号生成唯一 file_path（uniq_invoice_payment_file_path）。"""
    seq = Invoice.objects.filter(payment=payment).count()
    return Invoice.objects.create(
        payment=payment,
        file_path=f"contracts/invoices/{payment.pk}/{seq}.pdf",
        original_filename=f"{amount}.pdf",
        total_amount=Decimal(amount),
    )


def _recompute(payment: ContractPayment) -> ContractPayment:
    InvoiceFileService().recompute_payment_invoicing(payment)
    payment.refresh_from_db()
    return payment


@pytest.mark.django_db
class TestNetAmountSemantics:
    def test_negative_sum_not_capped_by_min(self, payment: ContractPayment) -> None:
        """红票让合计变负：min() 截断是错的（会算成“已全额开票”），必须放行到 max(0)。"""
        _invoice(payment, "10000.00")
        _invoice(payment, "-10000.00")
        result = _recompute(payment)
        assert result.invoiced_amount == Decimal("0.00")
        assert result.invoice_status == InvoiceStatus.VOIDED_PENDING_REISSUE

    def test_red_only_without_original_invoice(self, payment: ContractPayment) -> None:
        """只有一张红票（历史脏数据）：净额为负 → 0，同样是“已冲红待重开”。"""
        _invoice(payment, "-10000.00")
        result = _recompute(payment)
        assert result.invoiced_amount == Decimal("0.00")
        assert result.invoice_status == InvoiceStatus.VOIDED_PENDING_REISSUE

    def test_red_then_reissue_returns_to_full(self, payment: ContractPayment) -> None:
        _invoice(payment, "10000.00")
        _invoice(payment, "-10000.00")
        _invoice(payment, "10000.00")
        result = _recompute(payment)
        assert result.invoiced_amount == Decimal("10000.00")
        assert result.invoice_status == InvoiceStatus.INVOICED_FULL

    def test_partial_red_reduces_net_amount(self, payment: ContractPayment) -> None:
        """部分冲红（红票金额小于原票）：净额是差，状态回部分开票。"""
        _invoice(payment, "10000.00")
        _invoice(payment, "-4000.00")
        result = _recompute(payment)
        assert result.invoiced_amount == Decimal("6000.00")
        assert result.invoice_status == InvoiceStatus.INVOICED_PARTIAL

    def test_over_invoiced_still_capped_for_positive_sum(self, payment: ContractPayment) -> None:
        """正数分支仍受收款金额上限约束（模型约束 chk_contractpayment_invoiced_le_amount）。"""
        _invoice(payment, "30000.00")
        _invoice(payment, "20000.00")
        result = _recompute(payment)
        assert result.invoiced_amount == Decimal("10000.00")
        assert result.invoice_status == InvoiceStatus.INVOICED_FULL

    def test_zero_sum_without_red_is_uninvoiced(self, payment: ContractPayment) -> None:
        """没有任何发票 → 未开票（不能误报成已冲红）。"""
        Invoice.objects.filter(payment=payment).delete()
        result = _recompute(payment)
        assert result.invoiced_amount == Decimal("0.00")
        assert result.invoice_status == InvoiceStatus.UNINVOICED

    def test_negative_amount_is_never_stored_negative(self, payment: ContractPayment) -> None:
        """净额为负时存的是 0，不是负数：约束 chk_contractpayment_invoiced_nonneg 不允许负值。"""
        _invoice(payment, "-10000.00")
        result = _recompute(payment)
        assert result.invoiced_amount >= Decimal("0")


@pytest.mark.django_db
class TestContractLevelInvoiceNotAffected:
    def test_contract_attached_invoice_does_not_touch_payment(self, contract: Contract) -> None:
        """先开票后付款的票挂在合同名下，与任何收款的开票金额无关。"""
        payment = ContractPayment.objects.create(contract=contract, amount=Decimal("10000.00"))
        Invoice.objects.create(
            contract=contract,
            file_path="contracts/invoices/c0/0.pdf",
            original_filename="c0.pdf",
            total_amount=Decimal("10000.00"),
        )
        result = _recompute(payment)
        assert result.invoiced_amount == Decimal("0.00")
        assert result.invoice_status == InvoiceStatus.UNINVOICED
