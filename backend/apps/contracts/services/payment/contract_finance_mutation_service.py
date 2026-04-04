"""Business logic services."""

from __future__ import annotations

import logging
from collections.abc import Callable
from decimal import Decimal
from json import JSONDecodeError, dumps, loads
from typing import TYPE_CHECKING, Any

from django.db import transaction
from django.db.models import Count, Sum
from django.utils.translation import gettext_lazy as _

from apps.contracts.models import Contract, ContractPayment
from apps.core.exceptions import NotFoundError, ValidationException
from apps.core.security import DjangoPermsMixin

logger = logging.getLogger(__name__)

if TYPE_CHECKING:
    from apps.contracts.services.contract.mutation import ContractMutationService
    from apps.contracts.services.payment.contract_payment_service import ContractPaymentService
    from apps.contracts.services.supplementary.supplementary_agreement_service import SupplementaryAgreementService


class ContractFinanceMutationService(DjangoPermsMixin):
    def __init__(
        self,
        *,
        get_contract_internal: Callable[[int], Contract],
        get_mutation_service: Callable[[], ContractMutationService] | None = None,
        supplementary_agreement_service: SupplementaryAgreementService,
        payment_service: ContractPaymentService,
    ) -> None:
        self.get_contract_internal = get_contract_internal
        self._get_mutation_service = get_mutation_service
        self.supplementary_agreement_service = supplementary_agreement_service
        self.payment_service = payment_service

    @property
    def mutation_service(self) -> ContractMutationService:
        if self._get_mutation_service is None:
            raise RuntimeError(_("ContractFinanceMutationService.mutation_service 未注入"))
        return self._get_mutation_service()

    def get_finance_summary(self, contract_id: int) -> dict[str, Any]:
        contract = Contract.objects.filter(id=contract_id).values("id", "fixed_amount").first()
        if not contract:
            raise NotFoundError(message=_("合同不存在"), code="CONTRACT_NOT_FOUND")

        agg = ContractPayment.objects.filter(contract_id=contract_id).aggregate(
            total_received=Sum("amount"),
            total_invoiced=Sum("invoiced_amount"),
            payment_count=Count("id"),
        )
        total_received = agg["total_received"] or Decimal(0)
        total_invoiced = agg["total_invoiced"] or Decimal(0)

        fixed_amount = contract.get("fixed_amount")
        unpaid = None
        if fixed_amount is not None:
            unpaid = max(Decimal(0), fixed_amount - total_received)

        return {
            "contract_id": contract_id,
            "total_received": float(total_received),
            "total_invoiced": float(total_invoiced),
            "unpaid_amount": float(unpaid) if unpaid is not None else None,
            "payment_count": int(agg["payment_count"] or 0),
        }

    @transaction.atomic
    def update_contract_with_finance(
        self,
        contract_id: int,
        update_data: dict[str, Any],
        user: Any | None = None,
        confirm_finance: bool = False,
        new_payments: list[dict[str, Any]] | None = None,
    ) -> Contract:
        contract = self.get_contract_internal(contract_id)

        supplementary_agreements_data = update_data.pop("supplementary_agreements", None)

        finance_keys = {"fee_mode", "fixed_amount", "risk_rate", "custom_terms"}
        touch_finance = any(k in update_data for k in finance_keys)

        if touch_finance and not confirm_finance:
            raise ValidationException(_("关键财务操作需二次确认"))
        if new_payments and not confirm_finance:
            raise ValidationException(_("关键财务操作需二次确认"))

        user_id = getattr(user, "id", None)

        if touch_finance:
            self.ensure_admin(user, message=_("修改财务数据需要管理员权限"))
            old_finance = {k: getattr(contract, k) for k in finance_keys}

        contract = self.mutation_service.update_contract(contract_id, update_data)

        if supplementary_agreements_data is not None:
            from apps.contracts.models import SupplementaryAgreement

            SupplementaryAgreement.objects.filter(contract_id=contract_id).delete()
            for sa_data in supplementary_agreements_data:
                self.supplementary_agreement_service.create_supplementary_agreement(
                    contract_id=contract.id, name=sa_data.get("name"), party_ids=sa_data.get("party_ids")
                )

        if new_payments:
            self.add_payments(contract_id=contract_id, payments_data=new_payments, user=user, confirm=True)

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
                    user_id=user_id,
                    action="update_contract_finance",
                    changes=changes,
                )

        return contract

    @transaction.atomic
    def add_payments(
        self,
        contract_id: int,
        payments_data: list[dict[str, Any]],
        user: Any | None = None,
        confirm: bool = True,
    ) -> list[Any]:
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

        return created_payments

    def _log_finance_change(
        self,
        contract_id: int,
        user_id: int | None,
        action: str,
        changes: dict[str, Any],
        level: str = "INFO",
    ) -> None:
        try:
            from apps.contracts.models import ContractFinanceLog

            payload = self._normalize_json_payload(changes)
            ContractFinanceLog.objects.create(
                contract_id=contract_id,
                action=action,
                level=level,
                actor_id=user_id,
                payload=payload,
            )
        except Exception:
            logger.exception("操作失败")

    def _normalize_json_payload(self, value: Any) -> Any:
        try:
            return loads(dumps(value, default=str))
        except (TypeError, ValueError, JSONDecodeError):
            return value
