"""Business logic services."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from django.utils.translation import gettext_lazy as _

from apps.core.exceptions import NotFoundError
from apps.documents.models import FolderTemplate

from .id_service import FolderTemplateIdService
from .repo import FolderTemplateRepo


@dataclass(frozen=True)
class FolderTemplateQueryService:
    repo: FolderTemplateRepo
    id_service: FolderTemplateIdService

    def get_duplicate_id_report(self) -> dict[str, Any]:
        return self.id_service.get_duplicate_id_report()

    def get_template_for_case(self, *, case_type: str, case_stage: str) -> Any:
        from apps.documents.models import FolderTemplateType

        templates = (
            self.repo.filter(is_active=True, template_type=FolderTemplateType.CASE).order_by("-updated_at").all()
        )
        for template in templates:
            case_types = template.case_types or []
            case_stages = template.case_stages or []
            case_type_match = not case_types or case_type in case_types or "all" in case_types
            case_stage_match = not case_stages or case_stage in case_stages or "all" in case_stages
            if case_type_match and case_stage_match:
                return template
        return None

    def get_template_by_id(self, *, template_id: int) -> FolderTemplate:
        try:
            return self.repo.get_by_id(template_id)
        except FolderTemplate.DoesNotExist:
            raise NotFoundError(
                message=_("文件夹模板不存在"),
                code="FOLDER_TEMPLATE_NOT_FOUND",
                errors={"template_id": f"ID 为 {template_id} 的模板不存在"},
            ) from None

    def list_templates(
        self, *, case_type: str | None = None, case_stage: str | None = None, is_active: bool | None = None
    ) -> Any:
        from apps.documents.models import FolderTemplateType

        queryset = self.repo.filter(template_type=FolderTemplateType.CASE).order_by("-updated_at").all()
        results: list[FolderTemplate] = []
        for template in queryset:
            if is_active is not None and template.is_active != is_active:
                continue
            if case_type is not None:
                case_types = template.case_types or []
                if case_types and case_type not in case_types and ("all" not in case_types):
                    continue
            if case_stage is not None:
                case_stages = template.case_stages or []
                if case_stages and case_stage not in case_stages and ("all" not in case_stages):
                    continue
            results.append(template)
        return results
