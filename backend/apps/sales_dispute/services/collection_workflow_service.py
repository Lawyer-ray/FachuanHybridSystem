"""催收工作流服务：启动催收、推进阶段、获取记录"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import date, timedelta

from django.apps import apps as django_apps
from django.db import transaction
from django.utils.translation import gettext_lazy as _

from apps.core.exceptions import ValidationException

logger = logging.getLogger(__name__)

# 标准催收时间线：各阶段相对于启动日的天数偏移
DEFAULT_TIMELINE: dict[str, int] = {
    "phone_collection": 0,
    "written_collection": 7,
    "lawyer_letter": 14,
    "ultimatum": 28,
    "litigation": 42,
}


@dataclass(frozen=True)
class CollectionRecordOutput:
    """催收记录输出"""

    record_id: int
    case_id: int
    current_stage: str
    start_date: date
    last_action_date: date | None
    next_due_date: date | None
    days_elapsed: int
    is_overdue: bool
    remarks: str


class CollectionWorkflowService:
    """催收工作流服务：启动催收、推进阶段"""

    @transaction.atomic
    def start_collection(
        self,
        case_id: int,
        start_date: date | None = None,
        remarks: str = "",
    ) -> CollectionRecordOutput:
        """
        为案件创建催收记录，初始阶段 phone_collection。

        1. 校验案件存在
        2. 校验不存在重复催收记录
        3. 创建 CollectionRecord
        4. 计算下一节点到期日（written_collection 的到期日）
        5. 创建初始 CollectionLog
        """
        from apps.sales_dispute.models.collection_record import CollectionLog, CollectionRecord, CollectionStage

        case_model = django_apps.get_model("cases", "Case")
        if not case_model.objects.filter(id=case_id).exists():
            raise ValidationException(
                message=_("案件不存在"),
                code="CASE_NOT_FOUND",
            )

        if CollectionRecord.objects.filter(case_id=case_id).exists():
            raise ValidationException(
                message=_("该案件已存在催收记录"),
                code="COLLECTION_ALREADY_EXISTS",
            )

        actual_start = start_date or date.today()
        next_due = actual_start + timedelta(days=DEFAULT_TIMELINE["written_collection"])

        record = CollectionRecord.objects.create(
            case_id=case_id,
            current_stage=CollectionStage.PHONE_COLLECTION,
            start_date=actual_start,
            last_action_date=actual_start,
            next_due_date=next_due,
            remarks=remarks,
        )

        CollectionLog.objects.create(
            record=record,
            action_type=CollectionStage.PHONE_COLLECTION,
            action_date=actual_start,
            description=_("启动催收流程，进入电话催款阶段"),
        )

        logger.info("案件 %s 启动催收流程", case_id)
        return self._to_output(record)

    @transaction.atomic
    def advance_stage(
        self,
        record_id: int,
        description: str = "",
    ) -> CollectionRecordOutput:
        """
        推进催收阶段到下一阶段。

        1. 获取当前记录
        2. 校验当前阶段不是最后阶段（litigation）
        3. 计算下一阶段
        4. 更新 current_stage、last_action_date、next_due_date
        5. 创建 CollectionLog
        """
        from apps.sales_dispute.models.collection_record import (
            STAGE_ORDER,
            CollectionLog,
            CollectionRecord,
            CollectionStage,
        )

        try:
            record = CollectionRecord.objects.select_for_update().get(id=record_id)
        except CollectionRecord.DoesNotExist:
            raise ValidationException(
                message=_("催收记录不存在"),
                code="COLLECTION_NOT_FOUND",
            )

        current_idx = STAGE_ORDER.index(record.current_stage)
        if current_idx >= len(STAGE_ORDER) - 1:
            raise ValidationException(
                message=_("当前已是最终阶段（起诉），无法继续推进"),
                code="ALREADY_LAST_STAGE",
            )

        next_stage_value = STAGE_ORDER[current_idx + 1]
        today = date.today()

        # 计算下一节点到期日：如果还有后续阶段，用时间线偏移
        next_next_idx = current_idx + 2
        if next_next_idx < len(STAGE_ORDER):
            next_next_stage = STAGE_ORDER[next_next_idx]
            next_due = record.start_date + timedelta(days=DEFAULT_TIMELINE[next_next_stage])
        else:
            next_due = None

        record.current_stage = next_stage_value
        record.last_action_date = today
        record.next_due_date = next_due
        record.save(
            update_fields=[
                "current_stage",
                "last_action_date",
                "next_due_date",
                "updated_at",
            ]
        )

        stage_display = CollectionStage(next_stage_value).label
        log_desc = description or str(_("推进至%(stage)s阶段") % {"stage": stage_display})

        CollectionLog.objects.create(
            record=record,
            action_type=next_stage_value,
            action_date=today,
            description=log_desc,
        )

        logger.info("催收记录 %s 推进至 %s", record_id, next_stage_value)
        return self._to_output(record)

    def get_collection(self, case_id: int) -> CollectionRecordOutput:
        """获取案件的催收记录"""
        from apps.sales_dispute.models.collection_record import CollectionRecord

        try:
            record = CollectionRecord.objects.get(case_id=case_id)
        except CollectionRecord.DoesNotExist:
            raise ValidationException(
                message=_("该案件暂无催收记录"),
                code="COLLECTION_NOT_FOUND",
            )

        return self._to_output(record)

    def _to_output(self, record: object) -> CollectionRecordOutput:
        """将 CollectionRecord ORM 对象转为输出 dataclass"""
        from apps.sales_dispute.models.collection_record import CollectionRecord

        assert isinstance(record, CollectionRecord)
        return CollectionRecordOutput(
            record_id=record.id,
            case_id=record.case_id,
            current_stage=record.current_stage,
            start_date=record.start_date,
            last_action_date=record.last_action_date,
            next_due_date=record.next_due_date,
            days_elapsed=record.days_elapsed,
            is_overdue=record.is_overdue,
            remarks=record.remarks,
        )

    def get_logs(self, record_id: int) -> list[dict[str, object]]:
        """获取催收记录的操作日志列表"""
        from apps.sales_dispute.models.collection_record import CollectionLog, CollectionRecord

        if not CollectionRecord.objects.filter(id=record_id).exists():
            raise ValidationException(
                message=_("催收记录不存在"),
                code="COLLECTION_NOT_FOUND",
            )

        logs = CollectionLog.objects.filter(record_id=record_id).order_by("-action_date", "-created_at")
        return [
            {
                "action_type": log.action_type,
                "action_date": log.action_date,
                "description": log.description,
                "document_type": log.document_type,
                "document_filename": log.document_filename,
            }
            for log in logs
        ]
