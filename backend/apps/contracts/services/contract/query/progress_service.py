"""合同进度计算服务。"""

from __future__ import annotations

from decimal import Decimal
from typing import Any

from django.db.models import Sum
from django.utils.translation import gettext_lazy as _

from apps.contracts.models import Contract, ContractPayment, FeeMode
from apps.core.exceptions import NotFoundError


class ContractProgressService:
    """计算收款进度和开票汇总。"""

    def _get_contract(self, contract_id: int) -> Contract:
        """获取合同,不存在则抛 NotFoundError。"""
        try:
            return Contract.objects.get(id=contract_id)
        except Contract.DoesNotExist:
            raise NotFoundError(_("合同 %(id)s 不存在") % {"id": contract_id}) from None

    def _get_payment_totals(self, contract_id: int) -> dict[str, Decimal]:
        """获取收款汇总: total_amount, invoiced_amount。"""
        result = ContractPayment.objects.filter(contract_id=contract_id).aggregate(
            total_amount=Sum("amount"),
            invoiced_amount=Sum("invoiced_amount"),
        )
        return {
            "total_amount": Decimal(str(result["total_amount"] or 0)),
            "invoiced_amount": Decimal(str(result["invoiced_amount"] or 0)),
        }

    def get_payment_progress(self, contract: Contract) -> dict[str, Any]:
        """计算收款进度百分比。固定/半风险模式有进度,全风险/自定义为 None。"""
        totals = self._get_payment_totals(contract.id)
        received_amount = totals["total_amount"]

        total_amount = None
        if contract.fee_mode in (FeeMode.FIXED, FeeMode.SEMI_RISK):
            total_amount = contract.fixed_amount

        progress_percent = None
        is_completed = False

        if total_amount is not None and total_amount > 0:
            percent = (received_amount / total_amount) * 100
            progress_percent = min(100, max(0, int(percent)))
            is_completed = received_amount >= total_amount

        return {
            "total_amount": total_amount,
            "received_amount": received_amount,
            "progress_percent": progress_percent,
            "is_completed": is_completed,
        }

    def get_invoice_summary(self, contract: Contract) -> dict[str, Any]:
        """计算开票汇总: 已开票/未开票金额及进度百分比。"""
        totals = self._get_payment_totals(contract.id)
        total_received = totals["total_amount"]
        invoiced_amount = totals["invoiced_amount"]

        uninvoiced_amount = total_received - invoiced_amount

        invoice_percent = 0
        if total_received > 0:
            percent = (invoiced_amount / total_received) * 100
            invoice_percent = min(100, max(0, int(percent)))

        has_pending = uninvoiced_amount > 0

        return {
            "total_received": total_received,
            "invoiced_amount": invoiced_amount,
            "uninvoiced_amount": uninvoiced_amount,
            "invoice_percent": invoice_percent,
            "has_pending": has_pending,
        }
