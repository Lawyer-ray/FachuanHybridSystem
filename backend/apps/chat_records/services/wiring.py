"""Dependency injection wiring."""

from __future__ import annotations


from apps.core.interfaces import ServiceLocator
from apps.core.tasking import TaskSubmissionService


def get_task_submission_service() -> TaskSubmissionService:
    return ServiceLocator.get_task_submission_service()  # type: ignore[no-any-return, attr-defined]
