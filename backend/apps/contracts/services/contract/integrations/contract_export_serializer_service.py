"""合同导出序列化服务。"""

from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING, Callable, cast

if TYPE_CHECKING:
    from apps.cases.models import Case
    from apps.client.models import Client
    from apps.contracts.models import Contract


ReminderPayload = dict[str, object]
SerializedPayload = dict[str, object]

if TYPE_CHECKING:
    CaseSerializer = Callable[[Case], SerializedPayload]
else:
    CaseSerializer = Callable[[object], SerializedPayload]


def _serialize_contract_client(client: Client) -> SerializedPayload:
    from apps.client.services.client_export_serializer_service import serialize_client_obj

    return cast(SerializedPayload, serialize_client_obj(client))


def _export_contract_reminders(contract: Contract) -> list[ReminderPayload]:
    from apps.core.interfaces import ServiceLocator

    reminder_service = ServiceLocator.get_reminder_service()
    return cast(
        list[ReminderPayload],
        reminder_service.export_contract_reminders_internal(contract_id=contract.id),
    )


def _serialize_exported_contract_reminders(reminders: list[ReminderPayload]) -> list[SerializedPayload]:
    result: list[SerializedPayload] = []
    for reminder in reminders:
        due_at = reminder.get("due_at")
        if isinstance(due_at, datetime):
            due_at_value = due_at.isoformat()
        elif due_at is None:
            due_at_value = ""
        else:
            due_at_value = str(due_at)

        metadata = reminder.get("metadata")
        metadata_value = metadata if isinstance(metadata, dict) else {}

        result.append(
            {
                "reminder_type": reminder.get("reminder_type"),
                "content": reminder.get("content"),
                "due_at": due_at_value,
                "metadata": metadata_value,
            }
        )
    return result


def serialize_contract_obj(
    obj: Contract,
    *,
    case_serializer: CaseSerializer | None = None,
) -> SerializedPayload:
    """将单个 Contract 实例序列化为 dict。"""
    if case_serializer is None:
        from apps.cases.services.case.case_export_serializer_service import (
            serialize_case_obj as default_case_serializer,
        )

        case_serializer = default_case_serializer

    exported_reminders = _export_contract_reminders(obj)

    return {
        "name": obj.name,
        "case_type": obj.case_type,
        "filing_number": obj.filing_number,
        "status": obj.status,
        "specified_date": str(obj.specified_date) if obj.specified_date else None,
        "start_date": str(obj.start_date) if obj.start_date else None,
        "end_date": str(obj.end_date) if obj.end_date else None,
        "is_filed": obj.is_filed,
        "fee_mode": obj.fee_mode,
        "fixed_amount": str(obj.fixed_amount) if obj.fixed_amount is not None else None,
        "risk_rate": str(obj.risk_rate) if obj.risk_rate is not None else None,
        "custom_terms": obj.custom_terms,
        "representation_stages": obj.representation_stages,
        "parties": [
            {"role": p.role, "client": _serialize_contract_client(p.client)} for p in obj.contract_parties.all()
        ],
        "assignments": [
            {
                "is_primary": a.is_primary,
                "order": a.order,
                "lawyer": {"real_name": a.lawyer.real_name, "phone": a.lawyer.phone, "username": a.lawyer.username},
            }
            for a in obj.assignments.all()
        ],
        "finalized_materials": [
            {
                "file_path": m.file_path,
                "original_filename": m.original_filename,
                "category": m.category,
                "remark": m.remark,
            }
            for m in obj.finalized_materials.all()
            if m.file_path
        ],
        "supplementary_agreements": [
            {
                "name": sa.name,
                "parties": [
                    {
                        "role": sp.role,
                        "client": {
                            "name": sp.client.name,
                            "client_type": sp.client.client_type,
                            "id_number": sp.client.id_number,
                            "phone": sp.client.phone,
                            "legal_representative": sp.client.legal_representative,
                            "is_our_client": sp.client.is_our_client,
                        },
                    }
                    for sp in sa.parties.all()
                ],
            }
            for sa in obj.supplementary_agreements.all()
        ],
        "payments": [
            {
                "amount": str(p.amount),
                "received_at": str(p.received_at),
                "invoice_status": p.invoice_status,
                "invoiced_amount": str(p.invoiced_amount),
                "note": p.note,
                "invoices": [
                    {
                        "file_path": inv.file_path,
                        "original_filename": inv.original_filename,
                        "remark": inv.remark,
                        "invoice_code": inv.invoice_code,
                        "invoice_number": inv.invoice_number,
                        "invoice_date": str(inv.invoice_date) if inv.invoice_date else None,
                        "amount": str(inv.amount) if inv.amount is not None else None,
                        "tax_amount": str(inv.tax_amount) if inv.tax_amount is not None else None,
                        "total_amount": str(inv.total_amount) if inv.total_amount is not None else None,
                    }
                    for inv in p.invoices.all()
                ],
            }
            for p in obj.payments.all()
        ],
        "finance_logs": [
            {
                "action": fl.action,
                "level": fl.level,
                "payload": fl.payload,
                "actor": {"real_name": fl.actor.real_name, "phone": fl.actor.phone, "username": fl.actor.username},
            }
            for fl in obj.finance_logs.all()
        ],
        "reminders": _serialize_exported_contract_reminders(exported_reminders),
        "client_payment_records": [
            {
                "amount": str(r.amount),
                "image_path": r.image_path,
                "note": r.note,
                "created_at": r.created_at.isoformat(),
            }
            for r in obj.client_payment_records.all()
        ],
        "cases": [case_serializer(c) for c in obj.cases.all()],
    }
