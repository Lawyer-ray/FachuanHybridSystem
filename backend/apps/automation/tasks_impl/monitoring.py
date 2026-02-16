"""Module for monitoring."""

from __future__ import annotations

import logging

logger = logging.getLogger("apps.automation")


def check_stuck_tasks() -> None:
    from apps.core.interfaces import ServiceLocator

    monitor_service = ServiceLocator.get_monitor_service()
    stuck_tasks = monitor_service.check_stuck_tasks(timeout_minutes=30)

    if stuck_tasks:
        monitor_service.send_alert(
            "任务超时告警",
            f"发现 {len(stuck_tasks)} 个任务执行超时(>30分钟)",
            level="warning",
        )
