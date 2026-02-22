"""API endpoints."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from django.http import HttpResponse
from ninja import Router

from apps.core.api.schema_utils import schema_to_update_dict
from apps.reminders.schemas import ReminderIn, ReminderOut, ReminderTypeItem, ReminderUpdate, list_reminder_types

if TYPE_CHECKING:
    from apps.reminders.services import ReminderService

router = Router()


def _get_service() -> ReminderService:
    """获取 ReminderService 实例（延迟导入）。"""
    from apps.core.dependencies.business_organization import build_reminder_api_service

    return build_reminder_api_service()


@router.get("/list", response=list[ReminderOut])
def list_reminders(request: Any, contract_id: int | None = None, case_log_id: int | None = None) -> Any:
    service = _get_service()
    return service.list_reminders(contract_id=contract_id, case_log_id=case_log_id)


@router.post("/create", response=ReminderOut)
def create_reminder(request: Any, payload: ReminderIn) -> Any:
    service = _get_service()
    return service.create_reminder(
        contract_id=payload.contract_id,
        case_log_id=payload.case_log_id,
        reminder_type=payload.reminder_type.value,
        content=payload.content,
        due_at=payload.due_at,
        metadata=payload.metadata,
    )


# 注意:/types 必须在 /{reminder_id} 之前,否则 "types" 会被当作 reminder_id 参数
@router.get("/types", response=list[ReminderTypeItem])
def get_types(request: Any) -> Any:
    return list_reminder_types()


@router.get("/{reminder_id}", response=ReminderOut)
def get_reminder(request: Any, reminder_id: int) -> Any:
    service = _get_service()
    return service.get_reminder(reminder_id)


@router.put("/{reminder_id}", response=ReminderOut)
def update_reminder(request: Any, reminder_id: int, payload: ReminderUpdate) -> Any:
    service = _get_service()
    data = schema_to_update_dict(payload)
    return service.update_reminder(reminder_id, data)


@router.delete("/{reminder_id}")
def delete_reminder(request: Any, reminder_id: int) -> HttpResponse:
    service = _get_service()
    service.delete_reminder(reminder_id)
    return HttpResponse(status=204)
