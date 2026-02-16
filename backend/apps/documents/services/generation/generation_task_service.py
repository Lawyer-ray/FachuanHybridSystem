"""Business logic services."""

import logging
from typing import Any, cast

from django.conf import settings
from django.utils import timezone

from apps.core.dtos import GenerationTaskDTO
from apps.documents.models import GenerationMethod, GenerationStatus, GenerationTask

logger = logging.getLogger(__name__)


class GenerationTaskService:
    def create_ai_task_internal(
        self,
        *,
        case_id: int,
        litigation_session_id: int,
        document_type: str,
        template_id: int | None,
        created_by_id: int | None,
        metadata: dict[str, Any],
    ) -> GenerationTaskDTO:
        task = GenerationTask.objects.create(
            case_id=case_id,
            litigation_session_id=litigation_session_id,
            generation_method=GenerationMethod.AI,
            document_type=document_type,
            template_id=template_id,
            status=GenerationStatus.PROCESSING,
            metadata=metadata or {},
            created_by_id=created_by_id,
        )
        return self._to_dto(task)

    def mark_task_completed_internal(
        self,
        *,
        task_id: int,
        result_file: str,
        metadata_updates: dict[str, Any],
    ) -> GenerationTaskDTO:
        task = GenerationTask.objects.filter(id=task_id).first()
        if not task:
            return GenerationTaskDTO(id=task_id, status=GenerationStatus.FAILED, created_at=timezone.now())

        task.status = GenerationStatus.COMPLETED
        task.result_file = result_file
        task.completed_at = timezone.now()
        task.metadata = task.metadata or {}
        task.metadata.update(metadata_updates or {})
        task.save(update_fields=["status", "result_file", "completed_at", "metadata"])
        return self._to_dto(task)

    def mark_task_failed_internal(
        self,
        *,
        task_id: int,
        error_message: str,
    ) -> GenerationTaskDTO:
        task = GenerationTask.objects.filter(id=task_id).first()
        if not task:
            return GenerationTaskDTO(id=task_id, status=GenerationStatus.FAILED, created_at=timezone.now())

        task.status = GenerationStatus.FAILED
        task.error_message = str(error_message or "")
        task.completed_at = timezone.now()
        task.save(update_fields=["status", "error_message", "completed_at"])
        return self._to_dto(task)

    def get_task_internal(self, task_id: int) -> GenerationTaskDTO | None | None:
        task = GenerationTask.objects.filter(id=task_id).first()
        if not task:
            return None
        return self._to_dto(task)

    def _to_dto(self, task: GenerationTask) -> GenerationTaskDTO:
        document_name: str | None = None
        document_url = None
        if task.result_file:
            try:
                document_name = task.result_file.name.split("/")[-1]
            except Exception:
                logger.exception("操作失败")

                document_name = None

            try:
                document_url = task.result_file.url
            except Exception:
                logger.exception("操作失败")

                media_url = getattr(settings, "MEDIA_URL", "/media/")
                file_name = getattr(task.result_file, "name", None) or str(task.result_file)
                if file_name:
                    document_url = f"{media_url}{file_name}"

        return GenerationTaskDTO(
            id=cast(int, task.pk),
            status=task.status,
            created_at=task.created_at,
            created_by_id=getattr(task, "created_by_id", None),
            document_name=document_name,
            document_url=document_url,
        )
