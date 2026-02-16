"""
文书送达定时任务 Admin Service
负责处理文书送达定时任务的管理逻辑
"""

import logging
from typing import TYPE_CHECKING, Any, Optional

from apps.automation.models import DocumentDeliverySchedule
from apps.core.exceptions import NotFoundError

if TYPE_CHECKING:
    from apps.automation.services.document_delivery.data_classes import DocumentQueryResult
    from apps.automation.services.document_delivery.document_delivery_schedule_service import (
        DocumentDeliveryScheduleService,
    )


class DocumentDeliveryScheduleAdminService:
    """
    文书送达定时任务管理服务

    负责处理Admin层的业务逻辑:
    - 获取定时任务记录
    - 执行定时任务
    """

    def __init__(self, schedule_service: Optional["DocumentDeliveryScheduleService"] = None) -> None:
        self.logger = logging.getLogger(__name__)
        self._schedule_service = schedule_service

    @property
    def schedule_service(self) -> "DocumentDeliveryScheduleService":
        if self._schedule_service is None:
            raise RuntimeError("DocumentDeliveryScheduleAdminService.schedule_service 未注入")
        return self._schedule_service

    def get_schedule_by_id(self, schedule_id: int) -> DocumentDeliverySchedule:
        """
        根据ID获取定时任务记录

        Args:
            schedule_id: 定时任务ID

        Returns:
            DocumentDeliverySchedule: 定时任务记录

        Raises:
            NotFoundError: 定时任务不存在
        """
        try:
            return DocumentDeliverySchedule.objects.get(id=schedule_id)
        except DocumentDeliverySchedule.DoesNotExist:
            raise NotFoundError(
                message=f"定时任务记录不存在: ID={schedule_id}", code="SCHEDULE_NOT_FOUND", errors={}
            ) from None

    def execute_scheduled_task(self, schedule_id: int) -> "DocumentQueryResult":
        """
        执行定时任务

        Args:
            schedule_id: 定时任务ID

        Returns:
            执行结果
        """
        return self.schedule_service.execute_scheduled_task(schedule_id)

    def update_schedule(
        self,
        schedule_id: int,
        runs_per_day: int | None = None,
        hour_interval: int | None = None,
        cutoff_hours: int | None = None,
        is_active: bool | None = None,
    ) -> DocumentDeliverySchedule:
        """
        更新定时任务配置

        Args:
            schedule_id: 定时任务ID
            runs_per_day: 每天运行次数
            hour_interval: 运行间隔小时数
            cutoff_hours: 截止小时数
            is_active: 是否启用
        """
        return self.schedule_service.update_schedule(
            schedule_id,
            runs_per_day=runs_per_day,
            hour_interval=hour_interval,
            cutoff_hours=cutoff_hours,
            is_active=is_active,
        )
