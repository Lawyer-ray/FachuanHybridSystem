"""Business logic services."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from django.db.models import Q

if TYPE_CHECKING:
    from apps.documents.models import DocumentTemplate


class ContractTemplateQueryService:
    def find_matching_templates(self, case_type: str) -> list[DocumentTemplate]:
        from apps.documents.models import DocumentContractSubType, DocumentTemplate, DocumentTemplateType

        templates = DocumentTemplate.objects.filter(template_type=DocumentTemplateType.CONTRACT, is_active=True).filter(
            Q(contract_sub_type__isnull=True)
            | Q(contract_sub_type="")
            | Q(contract_sub_type=DocumentContractSubType.CONTRACT)
        )

        matched_templates: list[DocumentTemplate] = []
        for template in templates:
            contract_types = template.contract_types or []
            if case_type in contract_types or "all" in contract_types:
                matched_templates.append(template)

        return matched_templates

    def find_matching_template(self, case_type: str) -> DocumentTemplate | None:
        templates = self.find_matching_templates(case_type)
        return templates[0] if templates else None

    def list_matching_template_summaries(self, case_type: str) -> list[dict[str, Any]]:
        templates = self.find_matching_templates(case_type)
        return [
            {
                "id": template.pk,
                "name": template.name,
                "type_display": getattr(template, "get_template_type_display", lambda: "")(),
            }
            for template in templates
        ]
