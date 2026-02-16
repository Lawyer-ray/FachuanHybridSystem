"""Module for folder template usecases."""
from __future__ import annotations


from typing import Any

from dataclasses import dataclass

from apps.documents.models import FolderTemplate
from apps.documents.services.folder_template.command_service import FolderTemplateCommandService
from apps.documents.services.folder_template.query_service import FolderTemplateQueryService
from apps.documents.services.folder_template.structure_rules import FolderTemplateStructureRules
from apps.documents.services.folder_template.validation_service import FolderTemplateValidationService


@dataclass(frozen=True)
class FolderTemplateUsecases:
    command_service: FolderTemplateCommandService
    query_service: FolderTemplateQueryService
    validation_service: FolderTemplateValidationService
    structure_rules: FolderTemplateStructureRules

    def list_templates(
        self, *, case_type: str | None = None, case_stage: str | None = None, is_active: bool | None = None
    ) -> list[FolderTemplate]:
        return self.query_service.list_templates(case_type=case_type, case_stage=case_stage, is_active=is_active)

    def get_template_by_id(self, *, template_id: int) -> FolderTemplate:
        return self.query_service.get_template_by_id(template_id=template_id)

    def get_template_for_case(self, *, case_type: str, case_stage: str) -> FolderTemplate | None:
        return self.query_service.get_template_for_case(case_type=case_type, case_stage=case_stage)

    def get_duplicate_id_report(self) -> dict[str, Any]:
        return self.query_service.get_duplicate_id_report()

    def create_template(
        self,
        *,
        name: str,
        case_type: str,
        case_stage: str,
        structure: dict[str, Any],
        is_default: bool = False,
        is_active: bool = True,
        **kwargs,
    ) -> FolderTemplate:
        return self.command_service.create_template(
            name=name,
            case_type=case_type,
            case_stage=case_stage,
            structure=structure,
            is_default=is_default,
            is_active=is_active,
            **kwargs,
        )

    def update_structure(self, *, template_id: int, structure: dict[str, Any]) -> FolderTemplate:
        return self.command_service.update_structure(template_id=template_id, structure=structure)

    def delete_template(self, *, template_id: int) -> bool:
        return self.command_service.delete_template(template_id=template_id)

    def create_template_from_dict(self, *, data: dict[str, Any]) -> FolderTemplate:
        return self.command_service.create_template_from_dict(data=data)

    def update_template_from_dict(self, *, template_id: int, data: dict[str, Any]) -> FolderTemplate:
        return self.command_service.update_template_from_dict(template_id=template_id, data=data)

    def validate_structure(self, *, structure: dict[str, Any]) -> tuple[bool, str]:
        return self.validation_service.validate_structure(structure)

    def validate_structure_ids(self, *, structure: dict[str, Any], template_id: int | None = None) -> tuple[bool, list[str]]:
        return self.structure_rules.validate_structure_ids(structure, template_id)

    def validate_and_fix_structure_ids(
        self, *, structure: dict[str, Any], template_id: int | None = None
    ) -> tuple[bool, dict, list[str]]:
        return self.structure_rules.validate_and_fix_structure_ids(structure, template_id)
