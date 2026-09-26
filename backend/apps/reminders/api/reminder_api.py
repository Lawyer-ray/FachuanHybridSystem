"""API endpoints."""

from __future__ import annotations

from typing import Any

from django.http import HttpResponse
from ninja import Router

from apps.core.api.schema_utils import schema_to_update_dict
from apps.core.security import get_request_access_context
from apps.core.security.access_context import AccessContext

from ..schemas import (
    CalendarEventItemOut,
    CalendarMonthOut,
    CalendarStatsOut,
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


def _ensure_target_access(
    ctx: AccessContext,
    contract_id: int | None = None,
    case_id: int | None = None,
    case_log_id: int | None = None,
) -> None:
    """验证用户对提醒关联实体（合同/案件/案件日志）的访问权限。"""
    if case_id is not None:
        from apps.cases.services.case.case_access_policy import CaseAccessPolicy

        CaseAccessPolicy().ensure_access_ctx(case_id=case_id, ctx=ctx)
    elif contract_id is not None:
        from apps.contracts.services.contract.domain.access_policy import ContractAccessPolicy

        ContractAccessPolicy().ensure_access(
            contract_id=contract_id,
            user=ctx.user,
            org_access=ctx.org_access,
            perm_open_access=ctx.perm_open_access,
        )
    elif case_log_id is not None:
        from apps.cases.models import CaseLog

        log = CaseLog.objects.filter(pk=case_log_id).values("case_id").first()
        if log:
            from apps.cases.services.case.case_access_policy import CaseAccessPolicy

            CaseAccessPolicy().ensure_access_ctx(case_id=log["case_id"], ctx=ctx)


@router.post("/parse", response=list[ParsedReminderOut])
def parse_reminders(request: Any, payload: ParseReminderIn) -> list[ParsedReminderOut]:  # pragma: no cover
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
def list_reminders(  # pragma: no cover
    request: Any,
    contract_id: int | None = None,
    case_id: int | None = None,
    case_log_id: int | None = None,
) -> Any:
    ctx = get_request_access_context(request)
    _ensure_target_access(ctx, contract_id=contract_id, case_id=case_id, case_log_id=case_log_id)
    return _get_reminder_service().list_reminders(
        contract_id=contract_id,
        case_id=case_id,
        case_log_id=case_log_id,
    )


@router.post("/create", response=ReminderOut)
def create_reminder(request: Any, payload: ReminderIn) -> Any:  # pragma: no cover
    ctx = get_request_access_context(request)
    _ensure_target_access(
        ctx, contract_id=payload.contract_id, case_id=payload.case_id, case_log_id=payload.case_log_id
    )
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
def get_types(request: Any) -> Any:  # pragma: no cover
    return list_reminder_types()


@router.get("/target-options", response=TargetOptionsOut)
def get_target_options(request: Any, q: str = "") -> Any:  # pragma: no cover
    """获取合同/案件/案件日志的关联选项，用于提醒表单的关联选择。"""
    from ..services.target_query import get_target_options

    return get_target_options(keyword=q)


@router.get("/calendar", response=CalendarMonthOut)
def get_calendar_month(
    request: Any,
    year: int = 0,
    month: int = 0,
) -> Any:  # pragma: no cover
    """按月日历视图（首页工作台 / 前端日历）。

    返回「日 → 事件」与工作台统计。同一庭审被多次同步的情况已由后端合并，
    统计口径也按合并后计算——前端不要再自行合并或计数，否则两边会不一致。
    """
    from django.utils import timezone

    from ..services.calendar_month_service import CalendarMonthService

    today = timezone.localdate()
    view_year = year if year >= 1000 else today.year
    view_month = month if 1 <= month <= 12 else today.month

    service = CalendarMonthService()
    view = service.build_month(year=view_year, month=view_month)

    def to_out(item: Any) -> CalendarEventItemOut:
        return CalendarEventItemOut(
            id=item.id,
            kind=item.kind,
            kind_label=item.kind_label,
            title=item.title,
            content=item.content,
            day=item.day,
            time=item.time,
            time_range=item.time_range,
            place=item.place,
            person=item.person,
            case_no=item.case_no,
            hearing_type=item.hearing_type,
            target_type=item.target_type,
            target_name=item.target_name,
            case_id=item.case_id,
            is_today=item.is_today,
            is_overdue=item.is_overdue,
            members=item.members,
            member_ids=item.member_ids,
        )

    return CalendarMonthOut(
        year=view.year,
        month=view.month,
        stats=CalendarStatsOut(**vars(view.stats)),
        days={day: [to_out(item) for item in items] for day, items in view.days.items()},
    )


@router.get("/{reminder_id}", response=ReminderOut)
def get_reminder(request: Any, reminder_id: int) -> Any:  # pragma: no cover
    reminder = _get_reminder_service().get_reminder(reminder_id, select_related=True)
    ctx = get_request_access_context(request)
    _ensure_target_access(
        ctx,
        contract_id=reminder.contract_id,
        case_id=reminder.case_id,
        case_log_id=reminder.case_log_id,
    )
    return reminder


@router.put("/{reminder_id}", response=ReminderOut)
def update_reminder(request: Any, reminder_id: int, payload: ReminderUpdate) -> Any:  # pragma: no cover
    existing = _get_reminder_service().get_reminder(reminder_id)
    ctx = get_request_access_context(request)
    _ensure_target_access(
        ctx,
        contract_id=existing.contract_id,
        case_id=existing.case_id,
        case_log_id=existing.case_log_id,
    )
    data = schema_to_update_dict(payload)
    return _get_reminder_service().update_reminder(reminder_id, data)


@router.delete("/{reminder_id}")
def delete_reminder(request: Any, reminder_id: int) -> HttpResponse:  # pragma: no cover
    existing = _get_reminder_service().get_reminder(reminder_id)
    ctx = get_request_access_context(request)
    _ensure_target_access(
        ctx,
        contract_id=existing.contract_id,
        case_id=existing.case_id,
        case_log_id=existing.case_log_id,
    )
    _get_reminder_service().delete_reminder(reminder_id)
    return HttpResponse(status=204)
