"""API endpoints."""

from __future__ import annotations

from typing import Any

from django.db.models import Q
from django.http import HttpResponse
from django.utils.translation import gettext_lazy as _
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
    from apps.cases.models import Case
    from apps.cases.models.log import CaseLog
    from apps.contracts.models.contract import Contract

    keyword = q.strip()
    limit_per_group = 12

    contract_qs = Contract.objects.all()
    case_qs = Case.objects.all()
    case_log_qs = CaseLog.objects.select_related("case").all()

    if keyword:
        contract_qs = contract_qs.filter(name__icontains=keyword)
        case_qs = case_qs.filter(name__icontains=keyword)
        case_log_qs = case_log_qs.filter(
            Q(case__name__icontains=keyword) | Q(content__icontains=keyword)
        )

    groups: list[dict[str, object]] = []

    contract_items = [
        {"id": row["id"], "name": row["name"], "target_type": "contract", "target_type_label": str(_("合同"))}
        for row in contract_qs.order_by("-id").values("id", "name")[:limit_per_group]
    ]
    if contract_items:
        groups.append({"key": "contract", "label": str(_("合同")), "items": contract_items})

    case_items = [
        {"id": row["id"], "name": row["name"], "target_type": "case", "target_type_label": str(_("案件"))}
        for row in case_qs.order_by("-id").values("id", "name")[:limit_per_group]
    ]
    if case_items:
        groups.append({"key": "case", "label": str(_("案件")), "items": case_items})

    case_log_items: list[dict[str, object]] = []
    for item in case_log_qs.order_by("-id")[:limit_per_group]:
        preview = item.content.strip().replace("\n", " ")
        if len(preview) > 24:
            preview = f"{preview[:24]}..."
        label = f"#{item.id} {item.case.name}｜{preview or str(_('无内容'))}"
        case_log_items.append({"id": item.id, "name": label, "target_type": "case_log", "target_type_label": str(_("案件日志"))})
    if case_log_items:
        groups.append({"key": "case_log", "label": str(_("案件日志")), "items": case_log_items})

    merged_items: list[dict[str, object]] = []
    for group in groups:
        group_items = group.get("items", [])
        if isinstance(group_items, list):
            merged_items.extend(group_items)

    return {"items": merged_items, "groups": groups}


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
