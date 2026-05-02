"""催收时间线与到期提醒服务"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import date, timedelta

from django.utils.translation import gettext_lazy as _

from apps.core.exceptions import ValidationException

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class TimelineNode:
    """时间线节点"""

    stage: str
    stage_display: str
    planned_date: date
    is_completed: bool


@dataclass(frozen=True)
class ReminderItem:
    """到期提醒项"""

    record_id: int
    case_id: int
    case_name: str
    current_stage: str
    next_due_date: date
    days_until_due: int


class CollectionReminderService:
    """催收时间线与到期提醒服务"""

    def get_timeline(
        self,
        record_id: int,
        custom_intervals: dict[str, int] | None = None,
    ) -> list[TimelineNode]:
        """
        返回完整催收时间线。

        1. 获取 CollectionRecord
        2. 用 start_date + 各阶段偏移天数计算计划日期
        3. 根据当前阶段判断是否已完成
        支持 custom_intervals 覆盖默认时间线
        """
        from apps.sales_dispute.models.collection_record import STAGE_ORDER, CollectionRecord, CollectionStage

        from .collection_workflow_service import DEFAULT_TIMELINE

        try:
            record = CollectionRecord.objects.get(id=record_id)
        except CollectionRecord.DoesNotExist:
            raise ValidationException(
                message=_("催收记录不存在"),
                code="COLLECTION_NOT_FOUND",
            )

        timeline = custom_intervals or DEFAULT_TIMELINE
        current_idx = STAGE_ORDER.index(record.current_stage)

        nodes: list[TimelineNode] = []
        for stage_value in STAGE_ORDER:
            if stage_value not in timeline:
                continue
            offset = timeline[stage_value]
            planned = record.start_date + timedelta(days=offset)
            stage_idx = STAGE_ORDER.index(stage_value)
            is_completed = stage_idx <= current_idx

            stage_enum = CollectionStage(stage_value)
            nodes.append(
                TimelineNode(
                    stage=stage_value,
                    stage_display=str(stage_enum.label),
                    planned_date=planned,
                    is_completed=is_completed,
                )
            )

        logger.info("催收记录 %s 时间线查询完成，共 %d 个节点", record_id, len(nodes))
        return nodes

    def get_upcoming_reminders(
        self,
        days_ahead: int = 7,
        as_of: date | None = None,
    ) -> list[ReminderItem]:
        """
        返回未来 N 天内到期的催收节点。

        查询 next_due_date 在 [as_of, as_of + days_ahead] 范围内的记录
        """
        from apps.sales_dispute.models.collection_record import CollectionRecord

        reference_date = as_of or date.today()
        end_date = reference_date + timedelta(days=days_ahead)

        records = CollectionRecord.objects.filter(
            next_due_date__gte=reference_date,
            next_due_date__lte=end_date,
        ).select_related("case")

        items: list[ReminderItem] = []
        for record in records:
            due = record.next_due_date
            if due is None:
                continue
            days_until = (due - reference_date).days
            items.append(
                ReminderItem(
                    record_id=record.id,
                    case_id=record.case_id,
                    case_name=str(record.case),
                    current_stage=record.current_stage,
                    next_due_date=due,
                    days_until_due=days_until,
                )
            )

        logger.info(
            "查询到 %d 条即将到期的催收提醒（%s 起 %d 天内）",
            len(items),
            reference_date,
            days_ahead,
        )
        return items
