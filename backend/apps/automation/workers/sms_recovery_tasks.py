"""Module for sms recovery tasks."""

from __future__ import annotations

import logging

from apps.core.dependencies.core import build_task_scheduler, build_task_submission_service

logger = logging.getLogger("apps.automation")


def periodic_recovery_task() -> None:
    from apps.automation.services.sms.task_recovery_service import TaskRecoveryService

    service = TaskRecoveryService(  # type: ignore[call-arg]
        task_submission_service=build_task_submission_service(),
        task_scheduler=build_task_scheduler(),
    )
    result = service.recover_all_tasks(dry_run=False)
    logger.info(f"定期恢复任务完成: {result}")
    return result  # type: ignore[return-value]
