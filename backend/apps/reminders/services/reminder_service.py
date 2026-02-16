"""Business logic services."""

from __future__ import annotations

from datetime import datetime
from typing import Any, cast

from django.db import transaction
from django.db.models import QuerySet
from django.utils import timezone

from apps.core.exceptions import NotFoundError, ValidationException
from apps.reminders.models import Reminder


class ReminderService:
    def list_reminders(
        self,
        contract_id: int | None = None,
        case_log_id: int | None = None,
    ) -> QuerySet[Reminder, Reminder]:
        qs = Reminder.objects.all().select_related("contract", "case_log").order_by("-due_at", "-id")

        if contract_id:
            qs = qs.filter(contract_id=contract_id)
        if case_log_id:
            qs = qs.filter(case_log_id=case_log_id)

        return qs

    def get_reminder(self, reminder_id: int) -> Reminder:
        try:
            reminder = Reminder.objects.select_related("contract", "case_log").get(id=reminder_id)
            return cast(Reminder, reminder)
        except Reminder.DoesNotExist:
            raise NotFoundError(f"提醒记录 {reminder_id} 不存在") from None

    @transaction.atomic
    def create_reminder(
        self,
        *,
        contract_id: int | None = None,
        case_log_id: int | None = None,
        reminder_type: str,
        content: str,
        due_at: datetime,
        metadata: dict[str, Any] | None = None,
    ) -> Reminder:
        if bool(contract_id) == bool(case_log_id):
            raise ValidationException("必须且只能绑定合同或案件日志之一")

        if not reminder_type or not reminder_type.strip():
            raise ValidationException("提醒类型不能为空")
        if not content or not content.strip():
            raise ValidationException("提醒事项不能为空")
        if not due_at:
            raise ValidationException("到期时间不能为空")

        if timezone.is_naive(due_at):
            due_at = timezone.make_aware(due_at)

        reminder = Reminder.objects.create(
            contract_id=contract_id,
            case_log_id=case_log_id,
            reminder_type=reminder_type,
            content=content,
            due_at=due_at,
            metadata=metadata or {},
        )
        return reminder

    @transaction.atomic
    def update_reminder(self, reminder_id: int, data: dict[str, Any]) -> Reminder:
        reminder = self.get_reminder(reminder_id)

        current_contract_id = cast(int | None, reminder.contract_id)
        current_case_log_id = cast(int | None, reminder.case_log_id)
        contract_id = cast(int | None, data.get("contract_id", current_contract_id))
        case_log_id = cast(int | None, data.get("case_log_id", current_case_log_id))
        if ("contract_id" in data or "case_log_id" in data) and bool(contract_id) == bool(case_log_id):
            raise ValidationException("必须且只能绑定合同或案件日志之一")

        if "contract_id" in data:
            reminder.contract_id = cast(int | None, data["contract_id"])
        if "case_log_id" in data:
            reminder.case_log_id = cast(int | None, data["case_log_id"])
        if "reminder_type" in data and data["reminder_type"] is not None:
            reminder.reminder_type = data["reminder_type"]
        if "content" in data and data["content"] is not None:
            reminder.content = data["content"]
        if "metadata" in data and data["metadata"] is not None:
            reminder.metadata = data["metadata"]
        if "due_at" in data and data["due_at"] is not None:
            due_at = data["due_at"]
            if not isinstance(due_at, datetime):
                raise ValidationException("到期时间格式不正确")
            if timezone.is_naive(due_at):
                due_at = timezone.make_aware(due_at)
            reminder.due_at = due_at

        reminder.full_clean()
        reminder.save()
        return reminder

    @transaction.atomic
    def delete_reminder(self, reminder_id: int) -> dict[str, bool]:
        reminder = self.get_reminder(reminder_id)
        reminder.delete()
        return {"success": True}
