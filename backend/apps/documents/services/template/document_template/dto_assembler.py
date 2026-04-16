"""Business logic services."""

from typing import Any

from apps.core.dto import DocumentTemplateDTO


class DocumentTemplateDtoAssembler:
    def to_dto(self, template: Any) -> DocumentTemplateDTO:
        case_types = template.case_types or []
        case_type = case_types[0] if case_types and case_types[0] != "all" else None

        return DocumentTemplateDTO(
            id=template.id,
            name=template.name,
            function_code="",  # 字段已删除,保留空字符串以兼容DTO
            file_path=template.get_file_location() if hasattr(template, "get_file_location") else template.file_path,
            template_type=getattr(template, "template_type", None),
            contract_sub_type=getattr(template, "contract_sub_type", None),
            case_sub_type=getattr(template, "case_sub_type", None),
            archive_sub_type=getattr(template, "archive_sub_type", None),
            case_types=list(getattr(template, "case_types", None) or []),
            case_stages=list(getattr(template, "case_stages", None) or []),
            legal_statuses=list(getattr(template, "legal_statuses", None) or []),
            legal_status_match_mode=getattr(template, "legal_status_match_mode", None),
            case_type=case_type,
            is_active=template.is_active,
        )
