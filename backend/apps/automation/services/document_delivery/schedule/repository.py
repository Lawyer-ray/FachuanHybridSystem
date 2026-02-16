"""Data repository layer."""

from __future__ import annotations

import logging
from dataclasses import dataclass

from django.utils import timezone

from apps.automation.models import DocumentDeliverySchedule
from apps.core.exceptions import NotFoundError

logger = logging.getLogger("apps.automation")


@dataclass(frozen=True)
class DocumentDeliveryScheduleRepository:
    def get_by_id(self, *, schedule_id: int) -> DocumentDeliverySchedule:
        try:
            return DocumentDeliverySchedule.objects.get(id=schedule_id)
        except DocumentDeliverySchedule.DoesNotExist:
            raise NotFoundError(f"定时任务不存在: {schedule_id}") from None

    def list_due(self) -> list[DocumentDeliverySchedule]:
        now = timezone.now()
        qs = DocumentDeliverySchedule.objects.filter(is_active=True, next_run_at__lte=now).order_by("next_run_at")
        logger.info(f"找到 {qs.count()} 个到期的定时任务")
        return list(qs)
