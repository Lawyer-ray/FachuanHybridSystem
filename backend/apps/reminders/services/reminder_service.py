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
    ) -> QuerySet[Reminder]:
        if contract_id is not None and case_log_id is not None:
            raise ValidationException(_("不能同时查询合同和案件日志的提醒"))
        if contract_id is None and case_log_id is None:
            raise ValidationException(_("必须指定合同或案件日志"))
        normalize_target_id(contract_id, field_name=_("contract_id"))
        normalize_target_id(case_log_id, field_name=_("case_log_id"))

        qs = Reminder.objects.order_by("-due_at", "-id")

        if contract_id is not None:
            qs = qs.filter(contract_id=contract_id)
        if case_log_id is not None:
            qs = qs.filter(case_log_id=case_log_id)

        return qs

    def get_reminder(self, reminder_id: int, *, select_related: bool = False) -> Reminder:
        try:
            qs = Reminder.objects.select_related("contract", "case_log") if select_related else Reminder.objects
            return qs.get(id=reminder_id)
        except Reminder.DoesNotExist:
            raise NotFoundError(_("提醒记录 %(id)s 不存在") % {"id": reminder_id}) from None

    @transaction.atomic
    def create_reminder(
        self,
        *,
        contract_id: int | None = None,
        case_log_id: int | None = None,
        reminder_type: str | Any,  # 支持字符串或 ReminderType 枚举
        content: str,
        due_at: datetime,
        metadata: dict[str, Any] | None = None,
    ) -> Reminder:
        validate_binding_exclusive(contract_id=contract_id, case_log_id=case_log_id)
        validate_fk_exists(contract_id=contract_id, case_log_id=case_log_id)
        # 处理枚举类型或字符串类型
        if hasattr(reminder_type, "value"):
            reminder_type = reminder_type.value
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
        reminder = self.get_reminder(reminder_id, select_related=False)
        changed = self._apply_update_fields(reminder, data)
        if changed:
            changed.append("updated_at")
            reminder.save(update_fields=changed)
        return reminder

    def _apply_update_fields(self, reminder: Reminder, data: dict[str, Any]) -> list[str]:
        """将 data 中的字段应用到 reminder 实例，返回变更的字段名列表。"""
        changed: list[str] = []
        # 计算新的绑定关系：如果字段在 data 中，使用新值；否则保持原值
        new_contract_id: int | None = data.get("contract_id") if "contract_id" in data else reminder.contract_id
        new_case_log_id: int | None = data.get("case_log_id") if "case_log_id" in data else reminder.case_log_id
        fk_changed = "contract_id" in data or "case_log_id" in data

        if "contract_id" in data:
            new_contract_id = normalize_target_id(data["contract_id"], field_name=_("contract_id"))
        if "case_log_id" in data:
            new_case_log_id = normalize_target_id(data["case_log_id"], field_name=_("case_log_id"))

        if fk_changed:
            # 校验最终状态必须且只能绑定一个
            validate_binding_exclusive(contract_id=new_contract_id, case_log_id=new_case_log_id)
            validate_fk_exists(
                contract_id=new_contract_id if "contract_id" in data else None,
                case_log_id=new_case_log_id if "case_log_id" in data else None,
            )
            if "contract_id" in data:
                reminder.contract_id = new_contract_id
                changed.append("contract_id")
            if "case_log_id" in data:
                reminder.case_log_id = new_case_log_id
                changed.append("case_log_id")

        if "reminder_type" in data and data["reminder_type"] is not None:
            # 处理枚举类型或字符串类型
            reminder_type_value = data["reminder_type"]
            if hasattr(reminder_type_value, "value"):
                reminder_type_value = reminder_type_value.value
            reminder.reminder_type = normalize_reminder_type(reminder_type_value)
            changed.append("reminder_type")
        if "content" in data and data["content"] is not None:
            reminder.content = normalize_content(data["content"])
            changed.append("content")
        if "metadata" in data:
            reminder.metadata = normalize_metadata(data["metadata"])
            changed.append("metadata")
        if "due_at" in data and data["due_at"] is not None:
            reminder.due_at = normalize_due_at(data["due_at"])
            changed.append("due_at")

        return changed

    def delete_reminder(self, reminder_id: int) -> None:
        reminder = self.get_reminder(reminder_id, select_related=False)
        count, _ = reminder.delete()
        if count == 0:
            raise NotFoundError(_("提醒记录 %(id)s 不存在") % {"id": reminder_id})

    def get_existing_due_times(self, case_log_id: int, reminder_type: str) -> set[datetime]:
        """获取案件日志已存在的提醒到期时间集合。"""
        return set(
            Reminder.objects.filter(
                case_log_id=case_log_id,
                reminder_type=reminder_type,
            ).values_list("due_at", flat=True)
        )
