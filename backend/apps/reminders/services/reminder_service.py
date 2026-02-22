"""Business logic services."""

from __future__ import annotations

import logging
from datetime import datetime
from typing import Any

from django.db import transaction
from django.db.models import QuerySet
from django.utils.translation import gettext_lazy as _

from apps.core.exceptions import NotFoundError, ValidationException
from apps.reminders.models import Reminder
from apps.reminders.services.validators import (
    normalize_content,
    normalize_due_at,
    normalize_metadata,
    normalize_reminder_type,
    normalize_target_id,
    validate_binding_exclusive,
    validate_fk_exists,
)

logger: logging.Logger = logging.getLogger(__name__)


class ReminderService:
    def list_reminders(
        self,
        contract_id: int | None = None,
        case_log_id: int | None = None,
    ) -> QuerySet[Reminder, Reminder]:
        if contract_id is not None and case_log_id is not None:
            raise ValidationException(_("不能同时查询合同和案件日志的提醒"))

        qs = Reminder.objects.all().select_related("contract", "case_log").order_by("-due_at", "-id")

        if contract_id is not None:
            qs = qs.filter(contract_id=contract_id)
        if case_log_id is not None:
            qs = qs.filter(case_log_id=case_log_id)

        return qs

    def get_reminder(self, reminder_id: int) -> Reminder:
        try:
            return Reminder.objects.select_related("contract", "case_log").get(id=reminder_id)
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
        validate_binding_exclusive(contract_id=contract_id, case_log_id=case_log_id)
        validate_fk_exists(contract_id=contract_id, case_log_id=case_log_id)
        reminder_type = normalize_reminder_type(reminder_type)
        content = normalize_content(content)
        due_at = normalize_due_at(due_at)
        metadata = normalize_metadata(metadata)

        return Reminder.objects.create(
            contract_id=contract_id,
            case_log_id=case_log_id,
            reminder_type=reminder_type,
            content=content,
            due_at=due_at,
            metadata=metadata,
        )

    @transaction.atomic
    def update_reminder(self, reminder_id: int, data: dict[str, Any]) -> Reminder:
        reminder = self.get_reminder(reminder_id)
        self._apply_update_fields(reminder, data)
        reminder.save()
        return reminder

    def _apply_update_fields(self, reminder: Reminder, data: dict[str, Any]) -> None:
        """将 data 中的字段应用到 reminder 实例，复用 validators 校验。"""
        new_contract_id: int | None = reminder.contract_id
        new_case_log_id: int | None = reminder.case_log_id
        fk_changed = False

        if "contract_id" in data:
            new_contract_id = normalize_target_id(data["contract_id"], field_name=_("contract_id"))
            fk_changed = True
        if "case_log_id" in data:
            new_case_log_id = normalize_target_id(data["case_log_id"], field_name=_("case_log_id"))
            fk_changed = True

        if fk_changed:
            validate_binding_exclusive(contract_id=new_contract_id, case_log_id=new_case_log_id)
            validate_fk_exists(
                contract_id=new_contract_id if "contract_id" in data else None,
                case_log_id=new_case_log_id if "case_log_id" in data else None,
            )
            if "contract_id" in data:
                reminder.contract_id = new_contract_id
            if "case_log_id" in data:
                reminder.case_log_id = new_case_log_id

        if "reminder_type" in data and data["reminder_type"] is not None:
            reminder.reminder_type = normalize_reminder_type(data["reminder_type"])
        if "content" in data and data["content"] is not None:
            reminder.content = normalize_content(data["content"])
        if "metadata" in data:
            reminder.metadata = normalize_metadata(data["metadata"])
        if "due_at" in data and data["due_at"] is not None:
            reminder.due_at = normalize_due_at(data["due_at"])

    @transaction.atomic
    def delete_reminder(self, reminder_id: int) -> None:
        reminder = self.get_reminder(reminder_id)
        reminder.delete()

    def get_existing_due_times(self, case_log_id: int, reminder_type: str) -> set[datetime]:
        """获取案件日志已存在的提醒到期时间集合。"""
        if case_log_id is None:
            raise ValidationException(_("案件日志ID 不能为空"))
        return set(
            Reminder.objects.filter(
                case_log_id=case_log_id,
                reminder_type=reminder_type,
            ).values_list("due_at", flat=True)
        )
