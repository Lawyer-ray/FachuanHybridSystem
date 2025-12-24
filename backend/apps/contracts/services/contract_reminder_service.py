"""
合同提醒服务层
处理合同提醒相关的业务逻辑，符合三层架构规范
"""
from typing import Optional, List
from datetime import date
from django.db import transaction
from django.db.models import QuerySet

from apps.core.exceptions import NotFoundError, ValidationException
from ..models import Contract, ContractReminder


class ContractReminderService:
    """
    合同提醒服务
    
    职责：
    - 提醒记录的 CRUD 操作
    - 数据验证
    - 业务逻辑封装
    """

    def __init__(self):
        """构造函数，预留依赖注入扩展"""
        pass

    def list_reminders(
        self,
        contract_id: Optional[int] = None,
        user=None,
        perm_open_access: bool = False,
    ) -> QuerySet:
        """
        获取提醒列表
        
        Args:
            contract_id: 合同 ID（可选）
            user: 当前用户
            perm_open_access: 是否开放访问权限
            
        Returns:
            提醒记录查询集
        """
        qs = ContractReminder.objects.all().select_related("contract").order_by("-due_date")
        
        if contract_id:
            qs = qs.filter(contract_id=contract_id)
        
        return qs

    def get_reminder(self, reminder_id: int) -> ContractReminder:
        """
        获取单个提醒记录
        
        Args:
            reminder_id: 提醒 ID
            
        Returns:
            提醒对象
            
        Raises:
            NotFoundError: 提醒不存在
        """
        try:
            return ContractReminder.objects.select_related("contract").get(id=reminder_id)
        except ContractReminder.DoesNotExist:
            raise NotFoundError(f"提醒记录 {reminder_id} 不存在")

    @transaction.atomic
    def create_reminder(
        self,
        contract_id: int,
        kind: str,
        content: str,
        due_date: date,
    ) -> ContractReminder:
        """
        创建提醒记录
        
        Args:
            contract_id: 合同 ID
            kind: 提醒类型
            content: 提醒内容
            due_date: 到期日期
            
        Returns:
            创建的提醒对象
            
        Raises:
            NotFoundError: 合同不存在
            ValidationException: 数据验证失败
        """
        # 验证合同存在
        if not Contract.objects.filter(id=contract_id).exists():
            raise NotFoundError(f"合同 {contract_id} 不存在")
        
        # 验证必填字段
        if not kind or not kind.strip():
            raise ValidationException("提醒类型不能为空")
        if not content or not content.strip():
            raise ValidationException("提醒内容不能为空")
        if not due_date:
            raise ValidationException("到期日期不能为空")
        
        # 创建提醒记录
        reminder = ContractReminder.objects.create(
            contract_id=contract_id,
            kind=kind,
            content=content,
            due_date=due_date,
        )
        
        return reminder

    @transaction.atomic
    def update_reminder(
        self,
        reminder_id: int,
        data: dict,
    ) -> ContractReminder:
        """
        更新提醒记录
        
        Args:
            reminder_id: 提醒 ID
            data: 更新数据
            
        Returns:
            更新后的提醒对象
            
        Raises:
            NotFoundError: 提醒不存在
            ValidationException: 数据验证失败
        """
        reminder = self.get_reminder(reminder_id)
        
        # 更新字段
        if "contract_id" in data and data["contract_id"]:
            if not Contract.objects.filter(id=data["contract_id"]).exists():
                raise NotFoundError(f"合同 {data['contract_id']} 不存在")
            reminder.contract_id = data["contract_id"]
        
        if "kind" in data:
            reminder.kind = data["kind"]
        
        if "content" in data:
            reminder.content = data["content"]
        
        if "due_date" in data and data["due_date"]:
            reminder.due_date = data["due_date"]
        
        reminder.save()
        
        return reminder

    @transaction.atomic
    def delete_reminder(self, reminder_id: int) -> dict:
        """
        删除提醒记录
        
        Args:
            reminder_id: 提醒 ID
            
        Returns:
            {"success": True}
            
        Raises:
            NotFoundError: 提醒不存在
        """
        reminder = self.get_reminder(reminder_id)
        reminder.delete()
        
        return {"success": True}
