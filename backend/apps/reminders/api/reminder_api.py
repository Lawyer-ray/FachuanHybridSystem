"""API endpoints."""

from __future__ import annotations

from typing import Any

from django.http import HttpResponse

from ninja import Router

from apps.core.api.schema_utils import schema_to_update_dict

from ..schemas import (
    ParsedReminderOut,
    ParseReminderIn,
    ReminderIn,
    ReminderOut,
    ReminderTypeItem,
    ReminderUpdate,
    TargetOptionsOut,
    list_reminder_types,
)
from ..services.wiring import get_reminder_service

router = Router()

def _get_reminder_service() -> Any:
    """工厂函数：获取 ReminderService 实例。"""
    return get_reminder_service()

@router.post("/parse", response=list[ParsedReminderOut])
def parse_reminders(request: Any, payload: ParseReminderIn) -> list[ParsedReminderOut]:
    """从文本中解析提醒事项。"""
    from ..services.reminder_parser_service import parse_reminders_from_text

    results = parse_reminders_from_text(payload.text)
    return [
        ParsedReminderOut(
            content=r.content,
            reminder_type=r.reminder_type,
            reminder_type_label=r.reminder_type_label,
            due_at=r.due_at,
            source_text=r.source_text,
        )
        for r in results
    ]

@router.get("/list", response=list[ReminderOut])
def list_reminders(
    request: Any,
    contract_id: int | None = None,
    case_id: int | None = None,
    case_log_id: int | None = None,
) -> Any:
    return _get_reminder_service().list_reminders(
        contract_id=contract_id,
        case_id=case_id,
        case_log_id=case_log_id,
    )

@router.post("/create", response=ReminderOut)
def create_reminder(request: Any, payload: ReminderIn) -> Any:
    return _get_reminder_service().create_reminder(
        contract_id=payload.contract_id,
        case_id=payload.case_id,
        case_log_id=payload.case_log_id,
        reminder_type=payload.reminder_type,
        content=payload.content,
        due_at=payload.due_at,
        metadata=payload.metadata,
    )

# 注意:/types 和 /target-options 必须在 /{reminder_id} 之前,否则会被当作 reminder_id 参数
@router.get("/types", response=list[ReminderTypeItem])
def get_types(request: Any) -> Any:
    return list_reminder_types()

@router.get("/target-options", response=TargetOptionsOut)
def get_target_options(request: Any, q: str = "") -> Any:
    """获取合同/案件/案件日志的关联选项，用于提醒表单的关联选择。"""
    from ..services.target_query import get_target_options

    return get_target_options(keyword=q)

@router.get("/{reminder_id}", response=ReminderOut)
def get_reminder(request: Any, reminder_id: int) -> Any:
    return _get_reminder_service().get_reminder(reminder_id)

@router.put("/{reminder_id}", response=ReminderOut)
def update_reminder(request: Any, reminder_id: int, payload: ReminderUpdate) -> Any:
    data = schema_to_update_dict(payload)
    return _get_reminder_service().update_reminder(reminder_id, data)

@router.delete("/{reminder_id}")
def delete_reminder(request: Any, reminder_id: int) -> HttpResponse:
    _get_reminder_service().delete_reminder(reminder_id)
    return HttpResponse(status=204)
