"""Business logic services."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any

from apps.core.tasking import TaskScheduler

logger = logging.getLogger("apps.automation")


@dataclass(frozen=True)
class DocumentDeliveryDjangoQScheduleManager:
    task_scheduler: TaskScheduler

    def setup(self, *, interval_minutes: int, schedule_name: str, command_name: str) -> str:
        logger.info(f"设置文书送达 Django Q 调度: interval={interval_minutes}分钟, name={schedule_name}")

        removed = self.task_scheduler.delete_schedules(name=schedule_name)
        if removed > 0:
            logger.info(f"已移除 {removed} 个现有的调度任务: {schedule_name}")

        args_list: list[Any] = [command_name]
        task_id = self.task_scheduler.schedule_interval(
            func="django.core.management.call_command",
            minutes=interval_minutes,
            name=schedule_name,
            args=args_list,
            repeats=-1,
        )

        logger.info(
            f"Django Q 调度任务已创建: name={schedule_name}, interval={interval_minutes}分钟, task_id={task_id}"
        )
        return task_id

    def remove(self, *, schedule_name: str) -> int:
        logger.info(f"移除文书送达 Django Q 调度: name={schedule_name}")
        removed = self.task_scheduler.delete_schedules(name=schedule_name)
        logger.info(f"已移除 {removed} 个调度任务: {schedule_name}")
        return removed
