"""Business logic services."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from django.utils import timezone

from apps.core.exceptions import NotFoundError, ValidationException
from apps.documents.models import (
    DocumentTemplate,
    FolderTemplate,
    GenerationConfig,
    GenerationMethod,
    GenerationStatus,
    GenerationTask,
)


@dataclass
class ConfigValidationResult:
    is_valid: bool
    error: str = ""


class GenerationService:
    def create_generation_config(
        self,
        name: str,
        case_type: str,
        case_stage: str,
        document_template_id: int,
        folder_path: str,
        priority: int = 0,
        condition: dict[str, Any] | None = None,
        is_active: bool = True,
    ) -> GenerationConfig:
        if not folder_path or not folder_path.strip():
            raise ValidationException("文件夹路径不能为空")

        template = DocumentTemplate.objects.filter(id=document_template_id).first()
        if not template:
            raise NotFoundError("文书模板不存在")
        if not getattr(template, "is_active", True):
            raise ValidationException("文书模板已禁用")

        config = GenerationConfig.objects.create(
            name=name,
            config_type="generation_rule",
            is_active=is_active,
            value={
                "case_type": case_type,
                "case_stage": case_stage,
                "document_template_id": document_template_id,
                "folder_path": folder_path.strip(),
                "priority": int(priority or 0),
                "condition": condition or {},
            },
            description="",
        )
        return config

    def update_generation_config(self, config_id: int, **updates: Any) -> Any:
        config = GenerationConfig.objects.filter(id=config_id).first()
        if not config:
            raise NotFoundError("生成配置不存在")

        if "name" in updates and updates["name"] is not None:
            config.name = updates["name"]

        value = dict(config.value or {})
        self._apply_value_updates(value, updates)  # type: ignore[attr-defined]
        self._validate_template_update(updates)  # type: ignore[attr-defined]
        config.value = value

        if "is_active" in updates and updates["is_active"] is not None:
            config.is_active = bool(updates["is_active"])

        config.save()
        return config

        def _apply_value_updates(value: dict[str, Any], updates: dict[str, Any]) -> None:
            for key in ("case_type", "case_stage", "folder_path", "priority", "condition", "document_template_id"):
                if key not in updates or updates[key] is None:
                    continue
                if key == "folder_path":
                    if not str(updates[key]).strip():
                        raise ValidationException("文件夹路径不能为空")
                    value[key] = str(updates[key]).strip()
                else:
                    value[key] = updates[key]

        def _validate_template_update(updates: dict[str, Any]) -> None:
            if "document_template_id" not in updates or updates["document_template_id"] is None:
                return
            template = DocumentTemplate.objects.filter(id=updates["document_template_id"]).first()
            if not template:
                raise NotFoundError("文书模板不存在")
            if not getattr(template, "is_active", True):
                raise ValidationException("文书模板已禁用")

    def delete_generation_config(self, config_id: int) -> bool:
        config = GenerationConfig.objects.filter(id=config_id).first()
        if not config:
            return False
        config.is_active = False
        config.save(update_fields=["is_active"])
        return True

    def get_configs_for_case(
        self, case_type: str, case_stage: str, include_inactive: bool = False
    ) -> list[GenerationConfig]:
        from django.db.models import IntegerField, Value
        from django.db.models.fields.json import KeyTextTransform
        from django.db.models.functions import Cast, Coalesce

        qs = GenerationConfig.objects.filter(config_type="generation_rule")
        if not include_inactive:
            qs = qs.filter(is_active=True)

        qs = qs.filter(value__case_type=case_type, value__case_stage=case_stage).annotate(
            priority_int=Coalesce(Cast(KeyTextTransform("priority", "value"), IntegerField()), Value(0))
        )
        return list(qs.order_by("-priority_int", "-id"))

    def validate_config_references(self, config: GenerationConfig) -> tuple[bool, str]:
        template_id = config.document_template_id
        if not template_id:
            return False, "配置未关联文书模板"
        template = DocumentTemplate.objects.filter(id=template_id).first()
        if not template:
            return False, "文书模板不存在"
        if not getattr(template, "is_active", True):
            return False, "文书模板已禁用"
        return True, ""

    def create_task(  # type: ignore[no-untyped-def]
        self,
        folder_template_id: int | None = None,
        output_path: str | None = None,
        **kwargs,
    ) -> GenerationTask:
        if folder_template_id is not None:
            exists = FolderTemplate.objects.filter(id=folder_template_id).exists()
            if not exists:
                raise NotFoundError("文件夹模板不存在")

        task = GenerationTask.objects.create(
            document_type=kwargs.get("document_type") or "unknown",
            generation_method=kwargs.get("generation_method") or GenerationMethod.TEMPLATE,
            status=GenerationStatus.PENDING,
            metadata={},
        )

        task.folder_template_id = folder_template_id  # type: ignore[assignment]
        task.output_path = output_path  # type: ignore[assignment]
        generated_files: list[Any] = []
        error_logs: list[Any] = []
        task.save(update_fields=["metadata"])
        return task

    def update_task_status(self, task_id: int, status: str, error_message: str | None = None) -> Any:
        task = GenerationTask.objects.filter(id=task_id).first()
        if not task:
            raise NotFoundError("生成任务不存在")

        valid_statuses = {s for s, _ in GenerationStatus.choices}
        if status not in valid_statuses:
            raise ValidationException("无效的任务状态")

        task.status = status
        if status in (GenerationStatus.COMPLETED, GenerationStatus.FAILED):
            task.completed_at = timezone.now()
        else:
            task.completed_at = None

        if status == GenerationStatus.FAILED and error_message:
            task.error_message = error_message
            task.save(update_fields=["status", "completed_at", "error_message"])
            self.add_error_log(task.id, error_message=error_message, error_type="error")
            return GenerationTask.objects.get(id=task.id)

        task.save(update_fields=["status", "completed_at"])
        return task

    def add_generated_file(self, task_id: int, file_path: str, file_name: str) -> Any:
        task = GenerationTask.objects.filter(id=task_id).first()
        if not task:
            raise NotFoundError("生成任务不存在")
        files = task.generated_files
        files.append({"path": file_path, "name": file_name, "created_at": timezone.now().isoformat()})
        task.generated_files = files
        task.save(update_fields=["metadata"])
        return task

    def add_error_log(self, task_id: int, error_message: str, error_type: str = "error") -> Any:
        task = GenerationTask.objects.filter(id=task_id).first()
        if not task:
            raise NotFoundError("生成任务不存在")
        logs = task.error_logs
        logs.append({"message": error_message, "type": error_type, "created_at": timezone.now().isoformat()})
        task.error_logs = logs
        task.save(update_fields=["metadata"])
        return task

    def list_tasks(self, status: str | None = None) -> list[GenerationTask]:
        qs = GenerationTask.objects.all()
        if status:
            qs = qs.filter(status=status)
        return list(qs.order_by("id"))

    def generate(self, task: GenerationTask) -> None:
        if not getattr(task, "case_id", None):
            raise ValidationException("任务未关联案件")
        raise NotImplementedError
