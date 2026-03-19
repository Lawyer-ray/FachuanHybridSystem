"""案件导出序列化服务。"""

from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING, cast

if TYPE_CHECKING:
    from apps.cases.models import Case, CaseLog
    from apps.client.models import Client


ReminderPayload = dict[str, object]
SerializedPayload = dict[str, object]


def _serialize_client(client: Client) -> SerializedPayload:
    from apps.client.services.client_export_serializer_service import serialize_client_obj

    return cast(SerializedPayload, serialize_client_obj(client))


def _export_case_log_reminders_map(logs: list[CaseLog]) -> dict[int, list[ReminderPayload]]:
    log_ids = [int(log.id) for log in logs if getattr(log, "id", None)]
    if not log_ids:
        return {}

    from apps.core.interfaces import ServiceLocator

    reminder_service = ServiceLocator.get_reminder_service()
    return cast(
        dict[int, list[ReminderPayload]],
        reminder_service.export_case_log_reminders_batch_internal(case_log_ids=log_ids),
    )


def _serialize_exported_reminders(reminders: list[ReminderPayload]) -> list[SerializedPayload]:
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


def serialize_case_obj(obj: Case) -> SerializedPayload:
    """将单个 Case 实例序列化为 dict。"""
    logs = list(obj.logs.all())
    reminders_by_log_id = _export_case_log_reminders_map(logs)

    return {
        "name": obj.name,
        "filing_number": obj.filing_number,
        "status": obj.status,
        "case_type": obj.case_type,
        "cause_of_action": obj.cause_of_action,
        "target_amount": str(obj.target_amount) if obj.target_amount is not None else None,
        "preservation_amount": str(obj.preservation_amount) if obj.preservation_amount is not None else None,
        "current_stage": obj.current_stage,
        "is_archived": obj.is_archived,
        "effective_date": str(obj.effective_date) if obj.effective_date else None,
        "specified_date": str(obj.specified_date) if obj.specified_date else None,
        "parties": [{"legal_status": p.legal_status, "client": _serialize_client(p.client)} for p in obj.parties.all()],
        "assignments": [
            {"lawyer": {"real_name": a.lawyer.real_name, "phone": a.lawyer.phone, "username": a.lawyer.username}}
            for a in obj.assignments.all()
        ],
        "supervising_authorities": [
            {"name": sa.name, "authority_type": sa.authority_type} for sa in obj.supervising_authorities.all()
        ],
        "case_numbers": [
            {"number": cn.number, "is_active": cn.is_active, "remarks": cn.remarks} for cn in obj.case_numbers.all()
        ],
        "chats": [
            {
                "platform": ch.platform,
                "chat_id": ch.chat_id,
                "name": ch.name,
                "is_active": ch.is_active,
                "owner_id": ch.owner_id,
            }
            for ch in obj.chats.all()
        ],
        "logs": [
            {
                "content": log.content,
                "created_at": log.created_at.isoformat(),
                "actor": {"real_name": log.actor.real_name, "phone": log.actor.phone, "username": log.actor.username},
                "attachments": [
                    {"file_path": att.file.name, "filename": att.file.name.split("/")[-1]}
                    for att in log.attachments.all()
                    if att.file
                ],
                "reminders": _serialize_exported_reminders(reminders_by_log_id.get(log.id) or []),
            }
            for log in logs
        ],
    }
