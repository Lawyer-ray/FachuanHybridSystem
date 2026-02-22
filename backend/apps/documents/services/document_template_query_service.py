"""Business logic services."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from .document_template_dto_assembler import DocumentTemplateDtoAssembler
logger = logging.getLogger(__name__)


class DocumentTemplateQueryService:
    def __init__(self, assembler: DocumentTemplateDtoAssembler | None = None) -> None:
        self._assembler = assembler

    @property
    def assembler(self) -> DocumentTemplateDtoAssembler:
        if self._assembler is None:
            from .document_template_dto_assembler import DocumentTemplateDtoAssembler

            self._assembler = DocumentTemplateDtoAssembler()
        return self._assembler

    def get_template_by_id_internal(self, template_id: int) -> Any:
        from apps.documents.models import DocumentTemplate

        template = DocumentTemplate.objects.filter(id=template_id).first()
        if not template:
            return None
        return self.assembler.to_dto(template)

    def get_template_by_function_code_internal(
        self, function_code: str, case_type: str | None = None, is_active: bool = True
    ) -> Any:
        from apps.documents.models import DocumentTemplate

        queryset = DocumentTemplate.objects.filter(function_code=function_code)
        if is_active:
            queryset = queryset.filter(is_active=True)
        templates = list(queryset)
        if case_type and templates:
            for template in templates:
                case_types = template.case_types or []
                if not case_types or "all" in case_types or case_type in case_types:
                    return self.assembler.to_dto(template)  # type: ignore[return-value]
            return None
        if templates:
            return self.assembler.to_dto(templates[0])  # type: ignore[return-value]
        return None

    def list_templates_by_function_code_internal(
        self, function_code: str, case_type: str | None = None, is_active: bool = True
    ) -> list[Any]:
        from apps.documents.models import DocumentTemplate

        queryset = DocumentTemplate.objects.filter(function_code=function_code)
        if is_active:
            queryset = queryset.filter(is_active=True)
        templates = list(queryset)
        result: list[Any] = []
        for template in templates:
            if case_type:
                case_types = template.case_types or []
                if case_types and "all" not in case_types and (case_type not in case_types):
                    continue
            result.append(self.assembler.to_dto(template))
        return result

    def get_templates_by_case_type_internal(self, case_type: str, is_active: bool = True) -> list[Any]:
        from apps.documents.models import DocumentTemplate

        queryset = DocumentTemplate.objects.all()
        if is_active:
            queryset = queryset.filter(is_active=True)
        templates = list(queryset)
        result: list[Any] = []
        for template in templates:
            case_types = template.case_types or []
            if not case_types or "all" in case_types or case_type in case_types:
                result.append(self.assembler.to_dto(template))
        return result

    def list_case_templates_internal(self, is_active: bool = True) -> list[Any]:
        from apps.documents.models import DocumentTemplate

        queryset = DocumentTemplate.objects.filter(template_type="case")
        if is_active:
            queryset = queryset.filter(is_active=True)
        return [self.assembler.to_dto(t) for t in queryset]

    def get_templates_by_ids_internal(self, template_ids: list[int]) -> list[Any]:
        if not template_ids:
            return []
        from apps.documents.models import DocumentTemplate

        templates = DocumentTemplate.objects.filter(id__in=template_ids)
        template_map = {t.id: t for t in templates}
        return [self.assembler.to_dto(template_map[tid]) for tid in template_ids if tid in template_map]
