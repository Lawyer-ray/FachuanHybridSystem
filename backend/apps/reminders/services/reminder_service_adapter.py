"""
提醒服务适配器

实现 IReminderService 接口，供其他模块（如案件模块、自动化模块）调用。
"""

from __future__ import annotations

import logging
from datetime import datetime
from typing import TYPE_CHECKING, Any, ClassVar

from django.db import transaction
from django.utils.translation import gettext_lazy as _

from apps.core.exceptions import ValidationException

from ..models import Reminder, ReminderType
from .reminder_service import ReminderService
from .validators import (
    normalize_content,
    normalize_due_at,
    normalize_metadata,
    normalize_reminder_type,
    normalize_target_id,
    validate_fk_exists,
    validate_positive_id,
)

if TYPE_CHECKING:
    from apps.core.dto import ReminderDTO, ReminderTypeDTO

    from ..ports import CaseLogTargetQueryPort, CaseTargetQueryPort, ContractTargetQueryPort

logger = logging.getLogger(__name__)

CASE_LOG_API_REMINDER_SOURCE = "case_log_api"


class ReminderServiceAdapter(ReminderService):
    """提醒服务适配器，继承 ReminderService 提供 API 方法，同时实现 IReminderService 供其他模块调用。"""

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
    _REMINDER_TYPE_CODE_TO_ID: ClassVar[dict[str, int]] = {
        code: idx + 1 for idx, code in enumerate(ReminderType.values)
    }

    def __init__(
        self,
        *,
        contract_target_query: ContractTargetQueryPort | None = None,
        case_target_query: CaseTargetQueryPort | None = None,
        case_log_target_query: CaseLogTargetQueryPort | None = None,
    ) -> None:
        super().__init__(
            contract_target_query=contract_target_query,
            case_target_query=case_target_query,
            case_log_target_query=case_log_target_query,
        )

    def create_reminder_internal(
        self, case_log_id: int, reminder_type: str, reminder_time: datetime | None, user_id: int | None = None
    ) -> ReminderDTO | None:
        """内部方法：为案件日志创建提醒。"""
        if reminder_type not in ReminderType.values:
            logger.warning("无效的提醒类型: %s", reminder_type, extra={"case_log_id": case_log_id})
            return None
        if reminder_time is None:
            logger.warning("提醒时间为空，跳过创建", extra={"case_log_id": case_log_id})
            return None

        reminder_type_label = ReminderType(reminder_type).label
        metadata = {"created_by_user_id": user_id} if user_id is not None else {}

        try:
            reminder = super().create_reminder(
                case_log_id=case_log_id,
                reminder_type=reminder_type,
                content=normalize_content(str(reminder_type_label)),
                due_at=reminder_time,
                metadata=metadata,
            )
        except Exception:
            logger.exception("创建提醒失败", extra={"case_log_id": case_log_id, "reminder_type": reminder_type})
            return None

        logger.info(
            "创建提醒成功",
            extra={"reminder_id": reminder.pk, "case_log_id": case_log_id, "reminder_type": reminder_type},
        )
        return self._to_reminder_dto(reminder)

    def create_case_log_reminder_internal(
        self,
        *,
        case_log_id: int,
        reminder_type: str,
        content: str,
        reminder_time: datetime,
        user_id: int | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> ReminderDTO:
        """内部方法：按调用方提供的内容创建案件日志提醒。"""
        final_metadata: dict[str, Any] = dict(metadata) if metadata else {}
        final_metadata.setdefault("created_by_user_id", user_id)
        reminder = super().create_reminder(
            case_log_id=case_log_id,
            reminder_type=reminder_type,
            content=content,
            due_at=reminder_time,
            metadata=final_metadata,
        )
        return self._to_reminder_dto(reminder)

    def upsert_case_log_reminder_internal(
        self,
        *,
        case_log_id: int,
        reminder_type: str,
        content: str,
        reminder_time: datetime,
        user_id: int | None = None,
        metadata_source: str | None = None,
    ) -> ReminderDTO:
        """内部方法：创建或更新案件日志提醒。"""
        reminder = self._get_preferred_case_log_reminder(case_log_id=case_log_id, metadata_source=metadata_source)
        metadata: dict[str, Any] = {}
        if reminder is not None and isinstance(reminder.metadata, dict):
            metadata.update(reminder.metadata)
        if metadata_source:
            metadata["source"] = metadata_source
        if user_id is not None:
            metadata["created_by_user_id"] = user_id
        if reminder is None:
            return self.create_case_log_reminder_internal(
                case_log_id=case_log_id,
                reminder_type=reminder_type,
                content=content,
                reminder_time=reminder_time,
                user_id=user_id,
                metadata=metadata,
            )
        updated = super().update_reminder(
            reminder.id,
            {
                "reminder_type": reminder_type,
                "content": content,
                "due_at": reminder_time,
                "metadata": metadata,
            },
        )
        return self._to_reminder_dto(updated)

    def clear_case_log_reminder_internal(self, *, case_log_id: int, metadata_source: str | None = None) -> bool:
        """内部方法：清除案件日志提醒。"""
        reminder = self._get_preferred_case_log_reminder(case_log_id=case_log_id, metadata_source=metadata_source)
        if reminder is None:
            return False
        super().delete_reminder(reminder.id)
        return True

    def _get_preferred_case_log_reminder(
        self, *, case_log_id: int, metadata_source: str | None = None
    ) -> Reminder | None:
        """按 metadata_source 查找匹配的提醒记录，优先匹配 source 标记。"""
        validate_positive_id(case_log_id, field_name=_("案件日志ID"))
        reminders = list(Reminder.objects.filter(case_log_id=case_log_id).order_by("-due_at", "-id"))
        if not reminders:
            return None
        if metadata_source:
            for reminder in reminders:
                metadata = reminder.metadata if isinstance(reminder.metadata, dict) else {}
                if metadata.get("source") == metadata_source:
                    return reminder
            return None
        return reminders[0]

    def get_reminder_type_by_code_internal(self, code: str) -> ReminderTypeDTO | None:
        """内部方法：根据代码获取提醒类型。"""
        from apps.core.dto import ReminderTypeDTO

        if code not in ReminderType.values:
            return None

        rt = ReminderType(code)
        return ReminderTypeDTO(id=self._REMINDER_TYPE_CODE_TO_ID[code], code=code, name=str(rt.label), description=None)

    def get_reminder_type_for_document_internal(self, document_type: str) -> ReminderTypeDTO | None:
        """内部方法：根据文书类型获取对应的提醒类型。"""
        reminder_type_code = self.DOCUMENT_TYPE_TO_REMINDER_TYPE.get(document_type)
        if reminder_type_code is None:
            return None
        return self.get_reminder_type_by_code_internal(reminder_type_code)

    def get_existing_reminder_times_internal(self, case_log_id: int, reminder_type: str) -> set[datetime]:
        """内部方法：获取案件日志已存在的提醒时间集合。"""
        return super().get_existing_due_times(case_log_id, reminder_type)

    @transaction.atomic
    def create_contract_reminders_internal(self, *, contract_id: int, reminders: list[dict[str, Any]]) -> int:
        """内部方法：批量创建合同提醒。"""
        normalized_contract_id = normalize_target_id(contract_id, field_name=_("合同ID"))
        if normalized_contract_id is None:
            raise ValidationException(_("合同ID 不能为空"))
        if not reminders:
            return 0

        validate_fk_exists(
            contract_id=normalized_contract_id,
            case_id=None,
            case_log_id=None,
            contract_target_query=self._contract_target_query,
            case_target_query=self._case_target_query,
            case_log_target_query=self._case_log_target_query,
        )

        objs: list[Reminder] = []
        for item in reminders:
            try:
                reminder_type = normalize_reminder_type(item.get("reminder_type") or "")
                content = normalize_content(item.get("content") or "")
                due_at = item.get("due_at")
                if due_at is None or not isinstance(due_at, datetime):
                    continue
                due_at = normalize_due_at(due_at)
                metadata = normalize_metadata(item.get("metadata"))
            except (ValidationException, ValueError, TypeError):
                continue

            objs.append(
                Reminder(
                    contract_id=normalized_contract_id,
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

    @transaction.atomic
    def create_case_log_reminders_internal(self, *, case_log_id: int, reminders: list[dict[str, Any]]) -> int:
        """内部方法：批量创建案件日志提醒。"""
        normalized_case_log_id = normalize_target_id(case_log_id, field_name=_("案件日志ID"))
        if normalized_case_log_id is None:
            raise ValidationException(_("案件日志ID 不能为空"))
        if not reminders:
            return 0

        validate_fk_exists(
            contract_id=None,
            case_id=None,
            case_log_id=normalized_case_log_id,
            contract_target_query=self._contract_target_query,
            case_target_query=self._case_target_query,
            case_log_target_query=self._case_log_target_query,
        )

        objs: list[Reminder] = []
        for item in reminders:
            try:
                reminder_type = normalize_reminder_type(item.get("reminder_type") or "")
                content = normalize_content(item.get("content") or "")
                due_at = item.get("due_at")
                if due_at is None or not isinstance(due_at, datetime):
                    continue
                due_at = normalize_due_at(due_at)
                metadata = normalize_metadata(item.get("metadata"))
            except (ValidationException, ValueError, TypeError):
                continue

            objs.append(
                Reminder(
                    case_log_id=normalized_case_log_id,
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

    def export_contract_reminders_internal(self, *, contract_id: int) -> list[dict[str, Any]]:
        """内部方法：导出合同直接关联的提醒数据。"""
        validate_positive_id(contract_id, field_name=_("合同ID"))
        rows = list(
            Reminder.objects.filter(contract_id=contract_id, case_log_id__isnull=True)
            .order_by("due_at", "id")
            .values("id", "contract_id", "case_id", "case_log_id", "reminder_type", "content", "due_at", "metadata")
        )
        return [self._enrich_export_row(row) for row in rows]  # type: ignore[arg-type]

    def export_case_log_reminders_internal(self, *, case_log_id: int) -> list[dict[str, Any]]:
        """内部方法：导出案件日志关联的提醒数据。"""
        validate_positive_id(case_log_id, field_name=_("案件日志ID"))
        rows = list(
            Reminder.objects.filter(case_log_id=case_log_id)
            .order_by("due_at", "id")
            .values("id", "contract_id", "case_id", "case_log_id", "reminder_type", "content", "due_at", "metadata")
        )
        return [self._enrich_export_row(row) for row in rows]  # type: ignore[arg-type]

    def export_case_log_reminders_batch_internal(self, *, case_log_ids: list[int]) -> dict[int, list[dict[str, Any]]]:
        """内部方法：批量导出案件日志关联的提醒数据。"""
        if not case_log_ids:
            return {}

        normalized_ids: list[int] = []
        seen_ids: set[int] = set()
        for case_log_id in case_log_ids:
            validate_positive_id(case_log_id, field_name=_("案件日志ID"))
            if case_log_id in seen_ids:
                continue
            seen_ids.add(case_log_id)
            normalized_ids.append(case_log_id)

        results: dict[int, list[dict[str, Any]]] = {case_log_id: [] for case_log_id in normalized_ids}
        rows = (
            Reminder.objects.filter(case_log_id__in=normalized_ids)
            .order_by("case_log_id", "due_at", "id")
            .values(
                "id",
                "contract_id",
                "case_id",
                "case_log_id",
                "reminder_type",
                "content",
                "due_at",
                "metadata",
            )
        )
        for row in rows:
            current_case_log_id = int(row["case_log_id"])
            results[current_case_log_id].append(self._enrich_export_row(row))  # type: ignore[arg-type]
        return results

    def get_latest_case_log_reminder_internal(self, *, case_log_id: int) -> dict[str, Any] | None:
        """内部方法：获取案件日志最近一条提醒。"""
        validate_positive_id(case_log_id, field_name=_("案件日志ID"))
        row = (
            Reminder.objects.filter(case_log_id=case_log_id)
            .order_by("-due_at", "-id")
            .values("id", "contract_id", "case_id", "case_log_id", "reminder_type", "content", "due_at", "metadata")
            .first()
        )
        if row is None:
            return None
        return self._enrich_export_row(row)  # type: ignore[arg-type]

    @staticmethod
    def _enrich_export_row(row: dict[str, Any]) -> dict[str, Any]:
        reminder_type = str(row.get("reminder_type") or "")
        try:
            reminder_type_label = str(ReminderType(reminder_type).label)
        except Exception:
            reminder_type_label = reminder_type
        return {**row, "reminder_type_label": reminder_type_label}

    def _to_reminder_dto(self, reminder: Reminder) -> ReminderDTO:
        """将 Reminder Model 转换为 DTO。"""
        from apps.core.dto import ReminderDTO

        return ReminderDTO(
            id=reminder.pk,
            case_log_id=reminder.case_log_id,
            reminder_type=str(reminder.reminder_type),
            reminder_time=reminder.due_at.isoformat(),
            contract_id=reminder.contract_id,
            case_id=reminder.case_id,
            created_at=reminder.created_at.isoformat(),
        )
