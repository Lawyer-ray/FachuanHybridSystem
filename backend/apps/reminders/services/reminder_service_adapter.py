"""
提醒服务适配器

实现 IReminderService 接口，供其他模块（如案件模块、自动化模块）调用。
"""

import logging
from collections.abc import Iterable
from datetime import datetime
from typing import TYPE_CHECKING, Any, ClassVar, cast

from django.db import transaction
from django.utils import timezone

from apps.reminders.models import Reminder, ReminderType
from apps.reminders.services.reminder_service import ReminderService

if TYPE_CHECKING:
    from apps.core.dtos import ReminderDTO, ReminderTypeDTO

logger = logging.getLogger(__name__)


class ReminderServiceAdapter:
    """提醒服务适配器，提供提醒模块的核心功能给其他模块使用。"""

    DOCUMENT_TYPE_TO_REMINDER_TYPE: ClassVar[dict[str, str]] = {
        "court_summons": "hearing",
        "hearing_summons": "hearing",
        "evidence_deadline_notice": "evidence_deadline",
        "fee_notice": "payment_deadline",
        "submission_notice": "submission_deadline",
        "ruling": "appeal_deadline",
        "verdict": "appeal_deadline",
        "asset_preservation": "asset_preservation_expires",
    }

    def __init__(self) -> None:
        self._service = ReminderService()

    def create_reminder_internal(
        self, case_log_id: int, reminder_type: str, reminder_time: datetime | None, user_id: int | None = None
    ) -> "ReminderDTO | None":
        """内部方法：为案件日志创建提醒。"""
        if reminder_type not in ReminderType.values:
            logger.warning("无效的提醒类型: %s", reminder_type, extra={"case_log_id": case_log_id})
            return None
        if not reminder_time:
            logger.warning("提醒时间为空，跳过创建", extra={"case_log_id": case_log_id})
            return None

        reminder_type_label = ReminderType(reminder_type).label
        metadata = {"created_by_user_id": user_id} if user_id else {}

        reminder = self._service.create_reminder(
            case_log_id=case_log_id,
            reminder_type=reminder_type,
            content=str(reminder_type_label),
            due_at=reminder_time,
            metadata=metadata,
        )

        logger.info(
            "创建提醒成功",
            extra={"reminder_id": reminder.pk, "case_log_id": case_log_id, "reminder_type": reminder_type},
        )
        return self._to_reminder_dto(reminder)

    def get_reminder_type_by_code_internal(self, code: str) -> "ReminderTypeDTO | None":
        """内部方法：根据代码获取提醒类型。"""
        from apps.core.dtos import ReminderTypeDTO

        if code not in ReminderType.values:
            return None

        rt = ReminderType(code)
        return ReminderTypeDTO(id=hash(code), code=code, name=str(rt.label), description=None)

    def get_reminder_type_for_document_internal(self, document_type: str) -> "ReminderTypeDTO | None":
        """内部方法：根据文书类型获取对应的提醒类型。"""
        reminder_type_code = self.DOCUMENT_TYPE_TO_REMINDER_TYPE.get(document_type)
        if not reminder_type_code:
            return None
        return self.get_reminder_type_by_code_internal(reminder_type_code)

    def get_existing_reminder_times_internal(self, case_log_id: int, reminder_type: str) -> set[datetime]:
        """内部方法：获取案件日志已存在的提醒时间集合。"""
        due_at_values = Reminder.objects.filter(
            case_log_id=case_log_id,
            reminder_type=reminder_type,
        ).values_list("due_at", flat=True)
        return set(cast(Iterable[datetime], due_at_values))

    @transaction.atomic
    def create_contract_reminders_internal(self, *, contract_id: int, reminders: list[dict[str, Any]]) -> int:
        """内部方法：批量创建合同提醒。"""
        if not contract_id or not reminders:
            return 0

        objs: list[Reminder] = []
        for item in reminders:
            reminder_type = (item.get("reminder_type") or "").strip()
            content = (item.get("content") or "").strip()
            due_at = item.get("due_at")
            metadata = item.get("metadata") or {}

            if not reminder_type or reminder_type not in ReminderType.values:
                continue
            if not content:
                continue
            if not due_at or not isinstance(due_at, datetime):
                continue
            if timezone.is_naive(due_at):
                due_at = timezone.make_aware(due_at)

            objs.append(
                Reminder(
                    contract_id=contract_id,
                    reminder_type=reminder_type,
                    content=content,
                    due_at=due_at,
                    metadata=metadata,
                )
            )

        if not objs:
            return 0

        Reminder.objects.bulk_create(objs)
        return len(objs)

    def _to_reminder_dto(self, reminder: Reminder) -> "ReminderDTO":
        """将 Reminder Model 转换为 DTO。"""
        from apps.core.dtos import ReminderDTO

        return ReminderDTO(
            id=reminder.pk,
            case_log_id=reminder.case_log_id if reminder.case_log_id else None,
            contract_id=reminder.contract_id if reminder.contract_id else None,
            reminder_type=str(reminder.reminder_type),
            reminder_time=str(reminder.due_at) if reminder.due_at else "",
            is_completed=False,
            created_at=str(reminder.created_at) if reminder.created_at else None,
        )
