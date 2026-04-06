"""Business logic services."""

from __future__ import annotations

import logging
from datetime import datetime
from typing import TYPE_CHECKING, Any, cast

from django.db import transaction
from django.db.models import QuerySet
from django.utils.translation import gettext_lazy as _

from apps.core.exceptions import NotFoundError, ValidationException
from ..models import Reminder
from .validators import (
    normalize_content,
    normalize_due_at,
    normalize_metadata,
    normalize_reminder_type,
    normalize_target_id,
    validate_binding_exclusive,
    validate_fk_exists,
)

logger: logging.Logger = logging.getLogger(__name__)

if TYPE_CHECKING:
    from ..ports import CaseLogTargetQueryPort, CaseTargetQueryPort, ContractTargetQueryPort


class ReminderService:
    def __init__(
        self,
        *,
        contract_target_query: ContractTargetQueryPort | None = None,
        case_target_query: CaseTargetQueryPort | None = None,
        case_log_target_query: CaseLogTargetQueryPort | None = None,
    ) -> None:
        self._contract_target_query = contract_target_query or self._build_contract_target_query()
        self._case_target_query = case_target_query or self._build_case_target_query()
        self._case_log_target_query = case_log_target_query or self._build_case_log_target_query()

    def _build_contract_target_query(self) -> ContractTargetQueryPort:
        from apps.contracts.adapters import ContractReminderTargetQueryAdapter

        return cast("ContractTargetQueryPort", ContractReminderTargetQueryAdapter())

    def _build_case_target_query(self) -> CaseTargetQueryPort:
        from apps.cases.adapters import CaseReminderTargetQueryAdapter

        return CaseReminderTargetQueryAdapter()

    def _build_case_log_target_query(self) -> CaseLogTargetQueryPort:
        from apps.cases.adapters import CaseLogReminderTargetQueryAdapter

        return CaseLogReminderTargetQueryAdapter()

    def list_reminders(
        self,
        contract_id: int | None = None,
        case_id: int | None = None,
        case_log_id: int | None = None,
    ) -> QuerySet[Reminder]:
        contract_id = normalize_target_id(contract_id, field_name=_("contract_id"))
        case_id = normalize_target_id(case_id, field_name=_("case_id"))
        case_log_id = normalize_target_id(case_log_id, field_name=_("case_log_id"))

        selected_filters = sum(target_id is not None for target_id in (contract_id, case_id, case_log_id))
        if selected_filters > 1:
            raise ValidationException(_("不能同时按合同、案件和案件日志筛选提醒"))

        qs = Reminder.objects.order_by("-due_at", "-id")
        if contract_id is not None:
            return qs.filter(contract_id=contract_id)
        if case_id is not None:
            return qs.filter(case_id=case_id)
        if case_log_id is not None:
            return qs.filter(case_log_id=case_log_id)
        return qs

    def get_reminder(self, reminder_id: int, *, select_related: bool = False) -> Reminder:
        try:
            qs = (
                Reminder.objects.select_related("contract", "case", "case_log", "case_log__case")
                if select_related
                else Reminder.objects
            )
            return qs.get(id=reminder_id)
        except Reminder.DoesNotExist:
            raise NotFoundError(_("提醒记录 %(id)s 不存在") % {"id": reminder_id}) from None

    @transaction.atomic
    def create_reminder(
        self,
        *,
        contract_id: int | None = None,
        case_id: int | None = None,
        case_log_id: int | None = None,
        reminder_type: str | Any,
        content: str,
        due_at: datetime,
        metadata: dict[str, Any] | None = None,
    ) -> Reminder:
        contract_id = normalize_target_id(contract_id, field_name=_("contract_id"))
        case_id = normalize_target_id(case_id, field_name=_("case_id"))
        case_log_id = normalize_target_id(case_log_id, field_name=_("case_log_id"))
        validate_binding_exclusive(contract_id=contract_id, case_id=case_id, case_log_id=case_log_id)
        validate_fk_exists(
            contract_id=contract_id,
            case_id=case_id,
            case_log_id=case_log_id,
            contract_target_query=self._contract_target_query,
            case_target_query=self._case_target_query,
            case_log_target_query=self._case_log_target_query,
        )
        if hasattr(reminder_type, "value"):
            reminder_type = reminder_type.value
        reminder_type = normalize_reminder_type(reminder_type)
        content = normalize_content(content)
        due_at = normalize_due_at(due_at)
        metadata = normalize_metadata(metadata)

        return Reminder.objects.create(
            contract_id=contract_id,
            case_id=case_id,
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
        new_contract_id = reminder.contract_id
        new_case_id = reminder.case_id
        new_case_log_id = reminder.case_log_id
        fk_fields = ("contract_id", "case_id", "case_log_id")
        fk_changed = any(field in data for field in fk_fields)

        if "contract_id" in data:
            new_contract_id = normalize_target_id(data["contract_id"], field_name=_("contract_id"))
        if "case_id" in data:
            new_case_id = normalize_target_id(data["case_id"], field_name=_("case_id"))
        if "case_log_id" in data:
            new_case_log_id = normalize_target_id(data["case_log_id"], field_name=_("case_log_id"))

        if fk_changed:
            validate_binding_exclusive(contract_id=new_contract_id, case_id=new_case_id, case_log_id=new_case_log_id)
            validate_fk_exists(
                contract_id=new_contract_id if "contract_id" in data else None,
                case_id=new_case_id if "case_id" in data else None,
                case_log_id=new_case_log_id if "case_log_id" in data else None,
                contract_target_query=self._contract_target_query,
                case_target_query=self._case_target_query,
                case_log_target_query=self._case_log_target_query,
            )
            if "contract_id" in data:
                reminder.contract_id = new_contract_id
                changed.append("contract_id")
            if "case_id" in data:
                reminder.case_id = new_case_id
                changed.append("case_id")
            if "case_log_id" in data:
                reminder.case_log_id = new_case_log_id
                changed.append("case_log_id")

        if "reminder_type" in data and data["reminder_type"] is not None:
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
        count, deleted_details = reminder.delete()
        if count == 0:
            raise NotFoundError(_("提醒记录 %(id)s 不存在") % {"id": reminder_id})
        logger.debug("Deleted reminder %s, details=%s", reminder_id, deleted_details)

    def get_existing_due_times(self, case_log_id: int, reminder_type: str) -> set[datetime]:
        """获取案件日志已存在的提醒到期时间集合。"""
        normalized_case_log_id = normalize_target_id(case_log_id, field_name=_("case_log_id"))
        if normalized_case_log_id is None:
            raise ValidationException(_("case_log_id 不能为空"))
        return set(
            Reminder.objects.filter(
                case_log_id=normalized_case_log_id,
                reminder_type=reminder_type,
            ).values_list("due_at", flat=True)
        )
