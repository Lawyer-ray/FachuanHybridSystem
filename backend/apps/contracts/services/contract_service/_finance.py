"""合同财务操作：收款、财务更新"""

from __future__ import annotations

import logging
from decimal import Decimal
from typing import TYPE_CHECKING, Any

from django.db import transaction

from apps.core.exceptions import PermissionDenied, ValidationException

from ._base import ContractServiceBase

if TYPE_CHECKING:
    from apps.contracts.models import ContractPayment

logger = logging.getLogger("apps.contracts")

__all__ = ["ContractFinanceMixin"]


class ContractFinanceMixin(ContractServiceBase):
    """合同财务 Mixin"""

    def get_finance_summary(self, contract_id: int) -> dict[str, Any]:
        """获取合同财务汇总"""
        contract = self._get_contract_internal(contract_id)

        payments = contract.payments.all()
        total_received = sum(p.amount or Decimal(0) for p in payments)
        total_invoiced = sum(p.invoiced_amount or Decimal(0) for p in payments)

        unpaid = None
        if contract.fixed_amount:
            unpaid = max(Decimal(0), contract.fixed_amount - total_received)

        return {
            "contract_id": contract_id,
            "total_received": float(total_received),
            "total_invoiced": float(total_invoiced),
            "unpaid_amount": float(unpaid) if unpaid is not None else None,
            "payment_count": len(payments),
        }

    @transaction.atomic
    def add_payments(
        self,
        contract_id: int,
        payments_data: list[dict[str, Any]],
        user: Any = None,
        confirm: bool = True,
    ) -> list[ContractPayment]:
        """添加合同收款记录（委托给 ContractPaymentService）"""
        from django.utils.dateparse import parse_date

        created_payments = []

        for payment_data in payments_data:
            received_at = None
            if payment_data.get("received_at"):
                received_at = parse_date(payment_data["received_at"])

            payment = self.payment_service.create_payment(
                contract_id=contract_id,
                amount=Decimal(str(payment_data.get("amount", 0))),
                received_at=received_at,
                invoice_status=payment_data.get("invoice_status"),
                invoiced_amount=(
                    Decimal(str(payment_data.get("invoiced_amount", 0)))
                    if payment_data.get("invoiced_amount") is not None
                    else None
                ),
                note=payment_data.get("note"),
                user=user,
                confirm=confirm,
            )
            created_payments.append(payment)

        logger.info(
            "添加收款记录成功",
            extra={"contract_id": contract_id, "payment_count": len(created_payments), "action": "add_payments"},
        )

        return created_payments

    @transaction.atomic
    def update_contract_with_finance(
        self,
        contract_id: int,
        update_data: dict[str, Any],
        user: Any = None,
        confirm_finance: bool = False,
        new_payments: list[dict[str, Any]] | None = None,
    ) -> Any:
        """更新合同（包含财务数据验证）"""
        contract = self._get_contract_internal(contract_id)

        supplementary_agreements_data = update_data.pop("supplementary_agreements", None)

        finance_keys = {"fee_mode", "fixed_amount", "risk_rate", "custom_terms"}
        touch_finance = any(k in update_data for k in finance_keys)

        if touch_finance and not confirm_finance:
            raise ValidationException("关键财务操作需二次确认")

        if new_payments and not confirm_finance:
            raise ValidationException("关键财务操作需二次确认")

        is_admin = getattr(user, "is_admin", False)
        user_id = getattr(user, "id", None)

        if touch_finance:
            if not is_admin:
                raise PermissionDenied("修改财务数据需要管理员权限")

            old_finance = {k: getattr(contract, k) for k in finance_keys}

        contract = self.update_contract(contract_id, update_data)

        if supplementary_agreements_data is not None:
            from apps.contracts.models import SupplementaryAgreement

            SupplementaryAgreement.objects.filter(contract_id=contract_id).delete()

            for sa_data in supplementary_agreements_data:
                self.supplementary_agreement_service.create_supplementary_agreement(
                    contract_id=contract.id, name=sa_data.get("name"), party_ids=sa_data.get("party_ids")
                )

        if new_payments:
            self.add_payments(
                contract_id=contract_id,
                payments_data=new_payments,
                user=user,
                confirm=True,
            )

        if touch_finance:
            new_finance = {k: getattr(contract, k) for k in finance_keys}
            changes = {
                k: {"old": old_finance.get(k), "new": new_finance.get(k)}
                for k in finance_keys
                if old_finance.get(k) != new_finance.get(k)
            }

            if changes:
                self._log_finance_change(
                    contract_id=contract.id,
                    user_id=user_id, # type: ignore
                    action="update_contract_finance",
                    changes=changes,
                )

        return contract

    # update_contract 由 _crud.py 提供
    def update_contract(self, contract_id: int, data: dict[str, Any]) -> Any:
        raise NotImplementedError
