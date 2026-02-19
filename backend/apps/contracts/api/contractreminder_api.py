"""
合同提醒 API 层
符合三层架构规范：只做请求/响应处理，业务逻辑在 Service 层
"""

from __future__ import annotations

from typing import Any

from django.http import HttpRequest
from django.utils.dateparse import parse_date
from ninja import Router

from apps.core.exceptions import ValidationException
from apps.core.request_context import extract_request_context

from ..schemas import ContractReminderIn, ContractReminderOut, ContractReminderUpdate
from ..services.contract_reminder_service import ContractReminderService

router = Router()


def _get_reminder_service() -> ContractReminderService:
    """工厂函数：创建 ContractReminderService 实例"""
    return ContractReminderService()


@router.get("/reminders", response=list[ContractReminderOut])
def list_contract_reminders(request: HttpRequest, contract_id: int | None = None) -> list[Any]:
    """获取提醒列表"""
    service = _get_reminder_service()
    ctx = extract_request_context(request)
    return list(
        service.list_reminders(
            contract_id=contract_id,
            user=ctx.user,
            perm_open_access=ctx.perm_open_access,
        )
    )


@router.post("/reminders", response=ContractReminderOut)
def create_contract_reminder(request: HttpRequest, payload: ContractReminderIn) -> Any:
    """创建提醒记录"""
    service = _get_reminder_service()
    due_date = parse_date(payload.due_date) if payload.due_date else None
    if due_date is None:
        raise ValidationException(message="到期日期不能为空", code="INVALID_DUE_DATE")
    return service.create_reminder(
        contract_id=payload.contract_id,
        kind=payload.kind,
        content=payload.content,
        due_date=due_date,
    )


@router.get("/reminders/{reminder_id}", response=ContractReminderOut)
def get_contract_reminder(request: HttpRequest, reminder_id: int) -> Any:
    """获取单个提醒记录"""
    service = _get_reminder_service()
    return service.get_reminder(reminder_id)


@router.put("/reminders/{reminder_id}", response=ContractReminderOut)
def update_contract_reminder(request: HttpRequest, reminder_id: int, payload: ContractReminderUpdate) -> Any:
    """更新提醒记录"""
    service = _get_reminder_service()
    data = payload.dict(exclude_unset=True)
    if "due_date" in data and isinstance(data["due_date"], str):
        data["due_date"] = parse_date(data["due_date"])
    return service.update_reminder(reminder_id, data)


@router.delete("/reminders/{reminder_id}")
def delete_contract_reminder(request: HttpRequest, reminder_id: int) -> Any:
    """删除提醒记录"""
    service = _get_reminder_service()
    return service.delete_reminder(reminder_id)
