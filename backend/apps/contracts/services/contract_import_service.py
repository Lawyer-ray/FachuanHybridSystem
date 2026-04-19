"""合同 JSON 导入服务（级联创建 Client 和 Lawyer）。"""

from __future__ import annotations

import logging
from datetime import datetime
from typing import TYPE_CHECKING, Callable, Final, NotRequired, Protocol, TypedDict

from django.db import transaction
from django.utils.dateparse import parse_datetime
from django.utils.translation import gettext_lazy as _

from apps.core.exceptions import ValidationException

if TYPE_CHECKING:
    from apps.cases.models import Case
    from apps.cases.services.case_import_service import CaseImportPayload
    from apps.client.models import Client
    from apps.contracts.models import Contract
    from apps.organization.models import Lawyer

ImportData = dict[str, object]


class ContractPartyImportPayload(TypedDict):
    role: NotRequired[str]
    client: NotRequired[ImportData]


class ContractAssignmentImportPayload(TypedDict):
    lawyer: NotRequired[ImportData]
    is_primary: NotRequired[bool]
    order: NotRequired[int]


class FinalizedMaterialImportPayload(TypedDict):
    file_path: NotRequired[str]
    original_filename: NotRequired[str]
    category: NotRequired[str]
    remark: NotRequired[str]


class SupplementaryAgreementPartyImportPayload(TypedDict):
    role: NotRequired[str]
    client: NotRequired[ImportData]


class SupplementaryAgreementImportPayload(TypedDict):
    name: NotRequired[str]
    parties: NotRequired[list[SupplementaryAgreementPartyImportPayload]]


class InvoiceImportPayload(TypedDict):
    file_path: NotRequired[str]
    original_filename: NotRequired[str]
    remark: NotRequired[str]
    invoice_code: NotRequired[str]
    invoice_number: NotRequired[str]
    invoice_date: NotRequired[object]
    amount: NotRequired[object]
    tax_amount: NotRequired[object]
    total_amount: NotRequired[object]


class PaymentImportPayload(TypedDict):
    amount: NotRequired[object]
    received_at: NotRequired[object]
    invoice_status: NotRequired[str]
    invoiced_amount: NotRequired[object]
    note: NotRequired[str | None]
    invoices: NotRequired[list[InvoiceImportPayload]]


class FinanceLogImportPayload(TypedDict):
    action: NotRequired[str]
    actor: NotRequired[ImportData]
    level: NotRequired[str]
    payload: NotRequired[dict[str, object]]


class ContractReminderImportPayload(TypedDict):
    reminder_type: NotRequired[str]
    content: NotRequired[str]
    due_at: NotRequired[str | datetime | None]
    metadata: NotRequired[dict[str, object]]


class ClientPaymentRecordImportPayload(TypedDict):
    amount: NotRequired[object]
    image_path: NotRequired[str | None]
    note: NotRequired[str]


class ContractImportPayload(TypedDict):
    name: NotRequired[str]
    case_type: NotRequired[str | None]
    status: NotRequired[str]
    specified_date: NotRequired[object]
    start_date: NotRequired[object]
    end_date: NotRequired[object]
    is_archived: NotRequired[bool]
    fee_mode: NotRequired[str]
    fixed_amount: NotRequired[object]
    risk_rate: NotRequired[object]
    custom_terms: NotRequired[str | None]
    representation_stages: NotRequired[list[str]]
    filing_number: NotRequired[str | None]
    parties: NotRequired[list[ContractPartyImportPayload]]
    assignments: NotRequired[list[ContractAssignmentImportPayload]]
    finalized_materials: NotRequired[list[FinalizedMaterialImportPayload]]
    supplementary_agreements: NotRequired[list[SupplementaryAgreementImportPayload]]
    payments: NotRequired[list[PaymentImportPayload]]
    finance_logs: NotRequired[list[FinanceLogImportPayload]]
    reminders: NotRequired[list[ContractReminderImportPayload]]
    client_payment_records: NotRequired[list[ClientPaymentRecordImportPayload]]
    cases: NotRequired[list[CaseImportPayload]]


if TYPE_CHECKING:
    CaseImportCallback = Callable[[CaseImportPayload, "Contract"], "Case | None"]
else:
    CaseImportCallback = Callable[[ImportData, "Contract"], "Case | None"]


class ClientResolverProtocol(Protocol):
    def resolve_with_attachments(self, data: ImportData) -> Client: ...


class LawyerResolverProtocol(Protocol):
    def resolve(self, data: ImportData) -> Lawyer | None: ...


logger = logging.getLogger("apps.contracts")

_CONTRACT_FIELDS: Final[tuple[str, ...]] = (
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


def _parse_contract_reminders_for_create(
    reminder_data_list: list[ContractReminderImportPayload],
) -> list[dict[str, object]]:
    reminders: list[dict[str, object]] = []
    for reminder_data in reminder_data_list:
        reminder_type = reminder_data.get("reminder_type")
        due_at = reminder_data.get("due_at")
        if not reminder_type or due_at is None:
            continue
        parsed_due_at = parse_datetime(due_at) if isinstance(due_at, str) else due_at
        if not isinstance(parsed_due_at, datetime):
            continue
        metadata = reminder_data.get("metadata")
        reminders.append(
            {
                "reminder_type": reminder_type,
                "content": reminder_data.get("content", ""),
                "due_at": parsed_due_at,
                "metadata": metadata if isinstance(metadata, dict) else {},
            }
        )
    return reminders


class ContractImportService:
    """按 filing_number get_or_create Contract，级联创建 Client 和 Lawyer。"""

    def __init__(
        self,
        client_resolve: ClientResolverProtocol,
        lawyer_resolve: LawyerResolverProtocol,
        case_import_fn: CaseImportCallback | None = None,
    ) -> None:
        self._client_resolve = client_resolve
        self._lawyer_resolve = lawyer_resolve
        self._case_import_fn = case_import_fn

    def bind_case_import(
        self,
        case_import_fn: CaseImportCallback | None,
    ) -> None:
        """绑定案件导入回调（用于导入链路中的循环依赖组装）。"""
        self._case_import_fn = case_import_fn

    @transaction.atomic
    def resolve(self, data: ContractImportPayload) -> Contract:
        from apps.contracts.models import Contract, ContractAssignment, ContractParty

        if not data.get("name"):
            raise ValidationException(message=_("合同名称不能为空"), code="INVALID_CONTRACT_DATA")

        filing_number: str | None = data.get("filing_number") or None
        if filing_number:
            existing = Contract.objects.filter(filing_number=filing_number).first()
            if existing:
                logger.info("复用已有合同", extra={"contract_id": existing.pk, "filing_number": filing_number})
                return existing

        contract_data = {f: data[f] for f in _CONTRACT_FIELDS if f in data}  # type: ignore[literal-required]
        # 空字符串 filing_number 转 None，避免 unique 冲突
        if not contract_data.get("filing_number"):
            contract_data["filing_number"] = None
        contract = Contract.objects.create(**contract_data)
        logger.info("创建新合同", extra={"contract_id": contract.pk, "contract_name": contract.name})

        for party_data in data.get("parties") or []:
            client_data = party_data.get("client")
            if not isinstance(client_data, dict):
                continue
            client = self._client_resolve.resolve_with_attachments(client_data)
            role = party_data.get("role", "PRINCIPAL")
            ContractParty.objects.get_or_create(contract=contract, client=client, defaults={"role": role})

        for assign_data in data.get("assignments") or []:
            lawyer_data = assign_data.get("lawyer")
            if not isinstance(lawyer_data, dict):
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
                        "category": m.get("category", "invoice"),
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
                if not isinstance(client_data, dict):
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
            if not isinstance(actor_data, dict):
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
        reminders_list = _parse_contract_reminders_for_create(data.get("reminders") or [])
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
                if not isinstance(case_data, dict) or not case_data.get("name"):
                    continue
                self._case_import_fn(case_data, contract)

        return contract


def build_contract_import_service_for_admin() -> ContractImportService:
    """构建 admin 导入使用的 ContractImportService（包含循环依赖绑定）。"""
    from apps.core.dependencies.business_import import build_case_and_contract_import_services_for_admin

    _, contract_svc = build_case_and_contract_import_services_for_admin()
    return contract_svc
