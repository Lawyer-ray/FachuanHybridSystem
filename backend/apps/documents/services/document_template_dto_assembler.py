"""Business logic services."""

from typing import Any

from apps.core.dtos import DocumentTemplateDTO


class DocumentTemplateDtoAssembler:
    def to_dto(self, template: Any) -> DocumentTemplateDTO:
        case_types = template.case_types or []
        case_type = case_types[0] if case_types and case_types[0] != "all" else None

        return DocumentTemplateDTO(
            id=template.id,
            name=template.name,
            function_code=template.function_code or "",
            file_path=template.get_file_location() if hasattr(template, "get_file_location") else template.file_path,
            template_type=getattr(template, "template_type", None),
            case_sub_type=getattr(template, "case_sub_type", None),
            case_types=list(getattr(template, "case_types", None) or []),
            case_stages=list(getattr(template, "case_stages", None) or []),
            legal_statuses=list(getattr(template, "legal_statuses", None) or []),
            legal_status_match_mode=getattr(template, "legal_status_match_mode", None),
            case_type=case_type,
            is_active=template.is_active,
            description=template.description or None,
        )
