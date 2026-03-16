"""合同 JSON 导入服务（级联创建 Client 和 Lawyer）。"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any, Callable, Protocol

from django.db import transaction
from django.utils.translation import gettext_lazy as _

from apps.core.exceptions import ValidationException

if TYPE_CHECKING:
    from apps.contracts.models import Contract


class ClientResolverProtocol(Protocol):
    def resolve_with_attachments(self, data: dict[str, Any]) -> Any: ...


class LawyerResolverProtocol(Protocol):
    def resolve(self, data: dict[str, Any]) -> Any: ...

logger = logging.getLogger("apps.contracts")

_CONTRACT_FIELDS: tuple[str, ...] = (
    "name",
    "case_type",
    "status",
    "specified_date",
    "start_date",
    "end_date",
    "is_archived",
    "fee_mode",
    "fixed_amount",
    "risk_rate",
    "custom_terms",
    "representation_stages",
    "filing_number",
)


class ContractImportService:
    """按 filing_number get_or_create Contract，级联创建 Client 和 Lawyer。"""

    def __init__(
        self,
        client_resolve: ClientResolverProtocol,
        lawyer_resolve: LawyerResolverProtocol,
        case_import_fn: Callable[[dict[str, Any], Any], Any] | None = None,
    ) -> None:
        self._client_resolve = client_resolve
        self._lawyer_resolve = lawyer_resolve
        self._case_import_fn = case_import_fn

    @transaction.atomic
    def resolve(self, data: dict[str, Any]) -> Contract:
        from apps.contracts.models import Contract, ContractAssignment, ContractParty

        if not data.get("name"):
            raise ValidationException(message=_("合同名称不能为空"), code="INVALID_CONTRACT_DATA")

        filing_number: str | None = data.get("filing_number") or None
        if filing_number:
            existing = Contract.objects.filter(filing_number=filing_number).first()
            if existing:
                logger.info("复用已有合同", extra={"contract_id": existing.pk, "filing_number": filing_number})
                return existing

        contract_data = {f: data[f] for f in _CONTRACT_FIELDS if f in data}
        # 空字符串 filing_number 转 None，避免 unique 冲突
        if not contract_data.get("filing_number"):
            contract_data["filing_number"] = None
        contract = Contract.objects.create(**contract_data)
        logger.info("创建新合同", extra={"contract_id": contract.pk, "contract_name": contract.name})

        for party_data in data.get("parties") or []:
            client_data = party_data.get("client")
            if not client_data:
                continue
            client = self._client_resolve.resolve_with_attachments(client_data)
            role = party_data.get("role", "PRINCIPAL")
            ContractParty.objects.get_or_create(contract=contract, client=client, defaults={"role": role})

        for assign_data in data.get("assignments") or []:
            lawyer_data = assign_data.get("lawyer")
            if not lawyer_data:
                continue
            lawyer = self._lawyer_resolve.resolve(lawyer_data)
            if lawyer is None:
                continue
            ContractAssignment.objects.get_or_create(
                contract=contract,
                lawyer=lawyer,
                defaults={
                    "is_primary": assign_data.get("is_primary", False),
                    "order": assign_data.get("order", 0),
                },
            )

        from apps.contracts.models import FinalizedMaterial

        for m in data.get("finalized_materials") or []:
            if m.get("file_path"):
                FinalizedMaterial.objects.get_or_create(
                    contract=contract,
                    file_path=m["file_path"],
                    defaults={
                        "original_filename": m.get("original_filename", ""),
                        "category": m.get("category", "other"),
                        "remark": m.get("remark", ""),
                    },
                )

        from apps.contracts.models import SupplementaryAgreement, SupplementaryAgreementParty

        for sa_data in data.get("supplementary_agreements") or []:
            sa, _created = SupplementaryAgreement.objects.get_or_create(
                contract=contract,
                name=sa_data.get("name") or "",
            )
            for sp_data in sa_data.get("parties") or []:
                client_data = sp_data.get("client")
                if not client_data:
                    continue
                client = self._client_resolve.resolve_with_attachments(client_data)
                SupplementaryAgreementParty.objects.get_or_create(
                    supplementary_agreement=sa,
                    client=client,
                    defaults={"role": sp_data.get("role", "PRINCIPAL")},
                )

        from apps.contracts.models import ContractPayment
        from apps.contracts.models.invoice import Invoice

        for p_data in data.get("payments") or []:
            if p_data.get("amount") and p_data.get("received_at"):
                payment, _ = ContractPayment.objects.get_or_create(
                    contract=contract,
                    received_at=p_data["received_at"],
                    amount=p_data["amount"],
                    defaults={
                        "invoice_status": p_data.get("invoice_status", "UNINVOICED"),
                        "invoiced_amount": p_data.get("invoiced_amount", 0),
                        "note": p_data.get("note"),
                    },
                )
                for inv_data in p_data.get("invoices") or []:
                    if inv_data.get("file_path"):
                        Invoice.objects.get_or_create(
                            payment=payment,
                            file_path=inv_data["file_path"],
                            defaults={
                                "original_filename": inv_data.get("original_filename", ""),
                                "remark": inv_data.get("remark", ""),
                                "invoice_code": inv_data.get("invoice_code", ""),
                                "invoice_number": inv_data.get("invoice_number", ""),
                                "invoice_date": inv_data.get("invoice_date"),
                                "amount": inv_data.get("amount"),
                                "tax_amount": inv_data.get("tax_amount"),
                                "total_amount": inv_data.get("total_amount"),
                            },
                        )

        from apps.contracts.models import ContractFinanceLog

        for fl_data in data.get("finance_logs") or []:
            actor_data = fl_data.get("actor")
            if not actor_data:
                continue
            actor = self._lawyer_resolve.resolve(actor_data)
            if actor is None:
                continue
            ContractFinanceLog.objects.get_or_create(
                contract=contract,
                action=fl_data.get("action", ""),
                actor=actor,
                level=fl_data.get("level", "INFO"),
                payload=fl_data.get("payload", {}),
            )

        # 还原重要日期提醒
        reminders_list = []
        for r_data in data.get("reminders") or []:
            if r_data.get("due_at") and r_data.get("reminder_type"):
                from datetime import datetime

                due_at = r_data["due_at"]
                if isinstance(due_at, str):
                    from django.utils.dateparse import parse_datetime

                    due_at = parse_datetime(due_at)
                if isinstance(due_at, datetime):
                    reminders_list.append({
                        "reminder_type": r_data["reminder_type"],
                        "content": r_data.get("content", ""),
                        "due_at": due_at,
                        "metadata": r_data.get("metadata", {}),
                    })
        if reminders_list:
            from apps.contracts.services.contract.wiring import get_reminder_service

            reminder_service = get_reminder_service()
            reminder_service.create_contract_reminders_internal(
                contract_id=contract.id,
                reminders=reminders_list,
            )

        # 还原客户回款记录
        from apps.contracts.models import ClientPaymentRecord

        for cp_data in data.get("client_payment_records") or []:
            if cp_data.get("amount"):
                ClientPaymentRecord.objects.get_or_create(
                    contract=contract,
                    amount=cp_data["amount"],
                    defaults={
                        "image_path": cp_data.get("image_path"),
                        "note": cp_data.get("note", ""),
                    },
                )

        # 还原关联案件
        if self._case_import_fn is not None:
            for case_data in data.get("cases") or []:
                if not case_data.get("name"):
                    continue
                self._case_import_fn(case_data, contract)

        return contract
