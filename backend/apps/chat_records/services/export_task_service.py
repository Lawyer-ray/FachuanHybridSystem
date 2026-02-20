"""Business logic services."""

from django.utils.translation import gettext_lazy as _
from __future__ import annotations

from typing import Any, cast

from django.db import transaction
from django.utils import timezone

from apps.chat_records.models import ChatRecordExportTask, ChatRecordProject, ExportStatus, ExportType
from apps.core.exceptions import NotFoundError, ValidationException
from apps.core.tasking import TaskSubmissionService

from .access_policy import ensure_can_access_project


class ExportTaskService:
    def __init__(self, *, task_submission_service: TaskSubmissionService) -> None:
        self.task_submission_service = task_submission_service

    def get_project(self, *, user: Any, project_id: int) -> ChatRecordProject:
        try:
            project = ChatRecordProject.objects.get(id=project_id)
        except ChatRecordProject.DoesNotExist:
            raise NotFoundError(f"项目 {project_id} 不存在") from None
        ensure_can_access_project(user=user, project=project)
        return project

    def get_task(self, *, user: Any, task_id: str) -> ChatRecordExportTask:
        try:
            task = cast(
                ChatRecordExportTask,
                ChatRecordExportTask.objects.select_related("project").get(id=task_id),
            )
        except ChatRecordExportTask.DoesNotExist:
            raise NotFoundError(f"导出任务 {task_id} 不存在") from None
        ensure_can_access_project(user=user, project=task.project)
        return task

    @transaction.atomic
    def create_export_task(
        self, *, user: Any, project_id: int, export_type: str, layout: dict[str, Any] | None
    ) -> ChatRecordExportTask:
        if export_type not in (ExportType.PDF, ExportType.DOCX):
            raise ValidationException("导出类型不支持")

        project = self.get_project(user=user, project_id=project_id)
        task = ChatRecordExportTask.objects.create(
            project=project,
            export_type=export_type,
            layout=layout or {},
            status=ExportStatus.PENDING,
            progress=0,
            current=0,
            total=0,
            message=_("准备导出"),
        )
        return task

    def submit_task(self, *, user: Any, task_id: str) -> dict[str, bool]:
        task = self.get_task(user=user, task_id=task_id)
        if task.status == ExportStatus.RUNNING:
            raise ValidationException("任务正在处理中")

        self.task_submission_service.submit(
            "apps.chat_records.tasks.export_chat_record_task",
            args=[str(task.id)],
            task_name=f"chat_records_export_{task.id}",
        )

        ChatRecordExportTask.objects.filter(id=task.id).update(
            status=ExportStatus.RUNNING,
            started_at=timezone.now(),
            finished_at=None,
            error="",
            message=_("任务已提交"),
            progress=0,
            current=0,
            total=0,
            updated_at=timezone.now(),
        )
        return {"success": True}
