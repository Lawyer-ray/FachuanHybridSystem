"""Dependency injection wiring."""

from __future__ import annotations

from typing import cast

from apps.core.interfaces import ServiceLocator
from apps.core.tasking import TaskSubmissionService


def get_task_submission_service() -> TaskSubmissionService:
    return cast(TaskSubmissionService, ServiceLocator.get_task_submission_service())
