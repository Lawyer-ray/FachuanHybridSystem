"""Business logic services."""

from __future__ import annotations

import logging
from datetime import datetime
from typing import Any, cast

from django.db import transaction
from django.db.models import QuerySet
from django.utils import timezone
from django.utils.translation import gettext_lazy as _

from apps.core.exceptions import NotFoundError, ValidationException
from apps.reminders.models import Reminder, ReminderType

logger: logging.Logger = logging.getLogger(__name__)


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
            raise NotFoundError(_("提醒记录 %(id)s 不存在") % {"id": reminder_id}) from None

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
            raise ValidationException(_("必须且只能绑定合同或案件日志之一"))

        if not reminder_type or not reminder_type.strip():
            raise ValidationException(_("提醒类型不能为空"))
        if reminder_type not in ReminderType.values:
            raise ValidationException(_("无效的提醒类型"))
        if not content or not content.strip():
            raise ValidationException(_("提醒事项不能为空"))
        if not due_at:
            raise ValidationException(_("到期时间不能为空"))

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
        self._validate_update_binding(reminder, data)
        self._apply_update_fields(reminder, data)
        reminder.full_clean()
        reminder.save()
        return reminder

    def _validate_update_binding(self, reminder: Reminder, data: dict[str, Any]) -> None:
        """更新时校验绑定互斥。"""
        if "contract_id" not in data and "case_log_id" not in data:
            return
        contract_id: int | None = data.get("contract_id", reminder.contract_id)
        case_log_id: int | None = data.get("case_log_id", reminder.case_log_id)
        if bool(contract_id) == bool(case_log_id):
            raise ValidationException(_("必须且只能绑定合同或案件日志之一"))

    def _apply_update_fields(self, reminder: Reminder, data: dict[str, Any]) -> None:
        """将 data 中的字段应用到 reminder 实例。"""
        if "contract_id" in data:
            reminder.contract_id = data["contract_id"]
        if "case_log_id" in data:
            reminder.case_log_id = data["case_log_id"]
        if "reminder_type" in data and data["reminder_type"] is not None:
            if data["reminder_type"] not in ReminderType.values:
                raise ValidationException(_("无效的提醒类型"))
            reminder.reminder_type = data["reminder_type"]
        if "content" in data and data["content"] is not None:
            reminder.content = data["content"]
        if "metadata" in data and data["metadata"] is not None:
            reminder.metadata = data["metadata"]
        if "due_at" in data and data["due_at"] is not None:
            due_at = data["due_at"]
            if not isinstance(due_at, datetime):
                raise ValidationException(_("到期时间格式不正确"))
            if timezone.is_naive(due_at):
                due_at = timezone.make_aware(due_at)
            reminder.due_at = due_at

    @transaction.atomic
    def delete_reminder(self, reminder_id: int) -> dict[str, bool]:
        reminder = self.get_reminder(reminder_id)
        reminder.delete()
        return {"success": True}
