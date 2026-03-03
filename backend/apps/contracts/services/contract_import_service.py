"""合同 JSON 导入服务（级联创建 Client 和 Lawyer）。"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any

from django.db import transaction
from django.utils.translation import gettext_lazy as _

from apps.core.exceptions import ValidationException

if TYPE_CHECKING:
    from apps.client.services.client_resolve_service import ClientResolveService
    from apps.contracts.models import Contract
    from apps.organization.services.lawyer_resolve_service import LawyerResolveService

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
        client_resolve: ClientResolveService,
        lawyer_resolve: LawyerResolveService,
    ) -> None:
        self._client_resolve = client_resolve
        self._lawyer_resolve = lawyer_resolve

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

        for p_data in data.get("payments") or []:
            if p_data.get("amount") and p_data.get("received_at"):
                ContractPayment.objects.get_or_create(
                    contract=contract,
                    received_at=p_data["received_at"],
                    amount=p_data["amount"],
                    defaults={
                        "invoice_status": p_data.get("invoice_status", "UNINVOICED"),
                        "invoiced_amount": p_data.get("invoiced_amount", 0),
                        "note": p_data.get("note"),
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
            ContractFinanceLog.objects.create(
                contract=contract,
                action=fl_data.get("action", ""),
                actor=actor,
                level=fl_data.get("level", "INFO"),
                payload=fl_data.get("payload", {}),
            )

        # 还原重要日期提醒
        from apps.reminders.models import Reminder

        for r_data in data.get("reminders") or []:
            if r_data.get("due_at") and r_data.get("reminder_type"):
                Reminder.objects.get_or_create(
                    contract=contract,
                    reminder_type=r_data["reminder_type"],
                    due_at=r_data["due_at"],
                    defaults={
                        "content": r_data.get("content", ""),
                        "metadata": r_data.get("metadata", {}),
                    },
                )

        # 还原关联案件
        from apps.cases.models import Case, CaseAssignment, CaseNumber, CaseParty
        from apps.cases.models.case import SupervisingAuthority

        _CASE_FIELDS: tuple[str, ...] = (
            "name", "status", "effective_date", "specified_date", "cause_of_action",
            "target_amount", "preservation_amount", "case_type", "current_stage",
            "is_archived", "filing_number",
        )
        for case_data in data.get("cases") or []:
            if not case_data.get("name"):
                continue
            fn: str | None = case_data.get("filing_number") or None
            if fn and Case.objects.filter(filing_number=fn).exists():
                continue
            cd = {f: case_data[f] for f in _CASE_FIELDS if f in case_data}
            if not cd.get("filing_number"):
                cd["filing_number"] = None
            cd["contract"] = contract
            case = Case.objects.create(**cd)
            for p_data in case_data.get("parties") or []:
                client_data = p_data.get("client")
                if not client_data:
                    continue
                client = self._client_resolve.resolve_with_attachments(client_data)
                CaseParty.objects.get_or_create(
                    case=case, client=client,
                    defaults={"legal_status": p_data.get("legal_status")},
                )
            for a_data in case_data.get("assignments") or []:
                lawyer_data = a_data.get("lawyer")
                if not lawyer_data:
                    continue
                lawyer = self._lawyer_resolve.resolve(lawyer_data)
                if lawyer:
                    CaseAssignment.objects.get_or_create(case=case, lawyer=lawyer)
            for sa_data in case_data.get("supervising_authorities") or []:
                SupervisingAuthority.objects.get_or_create(
                    case=case, name=sa_data.get("name"),
                    defaults={"authority_type": sa_data.get("authority_type", "TRIAL")},
                )
            for cn_data in case_data.get("case_numbers") or []:
                if cn_data.get("number"):
                    CaseNumber.objects.get_or_create(
                        case=case, number=cn_data["number"],
                        defaults={"is_active": cn_data.get("is_active", False), "remarks": cn_data.get("remarks")},
                    )

        return contract
