"""
合同提醒 API 层
符合三层架构规范：只做请求/响应处理，业务逻辑在 Service 层
"""
from typing import Optional
from ninja import Router
from django.utils.dateparse import parse_date

from ..schemas import ContractReminderIn, ContractReminderOut, ContractReminderUpdate
from ..services.contract_reminder_service import ContractReminderService

router = Router()


def _get_reminder_service() -> ContractReminderService:
    """工厂函数：创建 ContractReminderService 实例"""
    return ContractReminderService()


@router.get("/reminders", response=list[ContractReminderOut])
def list_contract_reminders(request, contract_id: Optional[int] = None):
    """
    获取提醒列表
    
    API 层职责：
    1. 接收请求参数
    2. 调用 Service 层方法
    3. 返回响应
    """
    service = _get_reminder_service()
    user = getattr(request, "user", None)
    perm_open_access = getattr(request, "perm_open_access", False)
    
    return service.list_reminders(
        contract_id=contract_id,
        user=user,
        perm_open_access=perm_open_access,
    )


@router.post("/reminders", response=ContractReminderOut)
def create_contract_reminder(request, payload: ContractReminderIn):
    """
    创建提醒记录
    
    API 层职责：
    1. 接收请求数据
    2. 解析日期参数
    3. 调用 Service 层方法
    4. 返回响应
    """
    service = _get_reminder_service()
    
    # 解析日期
    due_date = parse_date(payload.due_date) if payload.due_date else None
    
    return service.create_reminder(
        contract_id=payload.contract_id,
        kind=payload.kind,
        content=payload.content,
        due_date=due_date,
    )


@router.get("/reminders/{reminder_id}", response=ContractReminderOut)
def get_contract_reminder(request, reminder_id: int):
    """
    获取单个提醒记录
    
    API 层职责：
    1. 接收路径参数
    2. 调用 Service 层方法
    3. 返回响应
    """
    service = _get_reminder_service()
    return service.get_reminder(reminder_id)


@router.put("/reminders/{reminder_id}", response=ContractReminderOut)
def update_contract_reminder(request, reminder_id: int, payload: ContractReminderUpdate):
    """
    更新提醒记录
    
    API 层职责：
    1. 接收请求参数
    2. 构建更新数据
    3. 调用 Service 层方法
    4. 返回响应
    """
    service = _get_reminder_service()
    
    # 构建更新数据
    data = payload.dict(exclude_unset=True)
    
    # 解析日期
    if "due_date" in data and isinstance(data["due_date"], str):
        data["due_date"] = parse_date(data["due_date"])
    
    return service.update_reminder(reminder_id, data)


@router.delete("/reminders/{reminder_id}")
def delete_contract_reminder(request, reminder_id: int):
    """
    删除提醒记录
    
    API 层职责：
    1. 接收路径参数
    2. 调用 Service 层方法
    3. 返回响应
    """
    service = _get_reminder_service()
    return service.delete_reminder(reminder_id)
