"""Business logic services."""

from typing import Any


class TemplateMatcher:
    def match_contract_template(self, case_type: str) -> Any:
        from django.db.models import Q

        from apps.documents.models import DocumentContractSubType, DocumentTemplate, DocumentTemplateType

        templates = DocumentTemplate.objects.filter(template_type=DocumentTemplateType.CONTRACT, is_active=True).filter(
            Q(contract_sub_type__isnull=True)
            | Q(contract_sub_type="")
            | Q(contract_sub_type=DocumentContractSubType.CONTRACT)
        )

        for template in templates:
            contract_types = template.contract_types or []
            if case_type in contract_types or "all" in contract_types:
                return template

        return None

    def match_supplementary_agreement_template(self, case_type: str) -> Any:
        from apps.documents.models import DocumentContractSubType, DocumentTemplate, DocumentTemplateType

        templates = DocumentTemplate.objects.filter(
            template_type=DocumentTemplateType.CONTRACT,
            contract_sub_type=DocumentContractSubType.SUPPLEMENTARY_AGREEMENT,
            is_active=True,
        )

        for template in templates:
            contract_types = template.contract_types or []
            if case_type in contract_types or "all" in contract_types:
                return template

        return None

    def match_folder_template(self, case_type: str) -> Any:
        from apps.documents.models import FolderTemplate, FolderTemplateType

        templates = FolderTemplate.objects.filter(template_type=FolderTemplateType.CONTRACT, is_active=True)
        for template in templates:
            contract_types = template.contract_types or []
            if case_type in contract_types or "all" in contract_types:
                return template
        return None
