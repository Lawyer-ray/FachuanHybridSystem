"""Business logic services."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from django.db import transaction

from apps.core.exceptions import NotFoundError, ValidationException
from apps.documents.models import FolderTemplate

from .repo import FolderTemplateRepo
from .structure_rules import FolderTemplateStructureRules
from .validation_service import FolderTemplateValidationService


@dataclass(frozen=True)
class FolderTemplateCommandService:
    repo: FolderTemplateRepo
    validation_service: FolderTemplateValidationService
    structure_rules: FolderTemplateStructureRules

    @transaction.atomic
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
        is_valid, error_msg = self.validation_service.validate_structure(structure)
        if not is_valid:
            raise ValidationException(
                message=error_msg,
                code="INVALID_STRUCTURE",
                errors={"structure": error_msg},
            )

        is_valid, errors = self.structure_rules.validate_structure_ids(structure)
        if not is_valid:
            raise ValidationException(
                message="文件夹结构验证失败",
                code="INVALID_STRUCTURE",
                errors={"validation_errors": errors},
            )

        from apps.documents.models import FolderTemplateType

        return self.repo.create(
            name=name,
            template_type=kwargs.pop("template_type", FolderTemplateType.CASE),
            case_types=kwargs.pop("case_types", [case_type] if case_type else []),
            case_stages=kwargs.pop("case_stages", [case_stage] if case_stage else []),
            contract_types=kwargs.pop("contract_types", []),
            structure=structure,
            is_default=is_default,
            is_active=is_active,
            **kwargs,
        )

    @transaction.atomic
    def update_structure(self, *, template_id: int, structure: dict[str, Any]) -> FolderTemplate:
        try:
            template = self.repo.get_by_id(template_id)
        except FolderTemplate.DoesNotExist:
            raise NotFoundError(
                message="文件夹模板不存在",
                code="FOLDER_TEMPLATE_NOT_FOUND",
                errors={"template_id": f"ID 为 {template_id} 的模板不存在"},
            ) from None

        is_valid, error_msg = self.validation_service.validate_structure(structure)
        if not is_valid:
            raise ValidationException(
                message=error_msg,
                code="INVALID_STRUCTURE",
                errors={"structure": error_msg},
            )

        is_valid, errors = self.structure_rules.validate_structure_ids(structure, template_id)
        if not is_valid:
            raise ValidationException(
                message="文件夹结构验证失败",
                code="INVALID_STRUCTURE",
                errors={"validation_errors": errors},
            )

        template.structure = structure
        template.save(update_fields=["structure", "updated_at"])
        self._clear_folder_template_cache()
        return template

    def _clear_folder_template_cache(self) -> None:
        """清除文件夹模板缓存"""
        from apps.core.infrastructure import CacheKeys, CacheTimeout, bump_cache_version

        bump_cache_version(CacheKeys.documents_matching_version_folder_templates(), timeout=CacheTimeout.get_day())

    @transaction.atomic
    def delete_template(self, *, template_id: int) -> bool:
        try:
            template = self.repo.get_by_id(template_id)
        except FolderTemplate.DoesNotExist:
            raise NotFoundError(
                message="文件夹模板不存在",
                code="FOLDER_TEMPLATE_NOT_FOUND",
                errors={"template_id": f"ID 为 {template_id} 的模板不存在"},
            ) from None

        template.is_active = False
        template.save(update_fields=["is_active", "updated_at"])
        self._clear_folder_template_cache()
        return True

    def create_template_from_dict(self, *, data: dict[str, Any]) -> FolderTemplate:
        name = data.get("name", "")
        case_type = data.get("case_type", "")
        case_stage = data.get("case_stage", "")
        structure = data.get("structure", {})
        is_default = bool(data.get("is_default", False))
        is_active = bool(data.get("is_active", True))

        extra: dict[str, Any] = {}
        for field in ["template_type", "case_types", "case_stages", "contract_types"]:
            if field in data and data[field] is not None:
                extra[field] = data[field]

        return self.create_template(
            name=name,
            case_type=case_type,
            case_stage=case_stage,
            structure=structure,
            is_default=is_default,
            is_active=is_active,
            **extra,
        )

    def update_template_from_dict(self, *, template_id: int, data: dict[str, Any]) -> FolderTemplate:
        template = self.get_template_or_404(template_id)

        new_structure = data.get("structure")
        if new_structure is not None:
            template = self.update_structure(template_id=template_id, structure=new_structure)
        else:
            template = template

        update_fields: list[Any] = []
        for field in [
            "name",
            "is_default",
            "is_active",
            "case_types",
            "case_stages",
            "contract_types",
            "template_type",
        ]:
            if field in data and data[field] is not None:
                setattr(template, field, data[field])
                update_fields.append(field)

        if update_fields:
            template.save(update_fields=update_fields + ["updated_at"])
            self._clear_folder_template_cache()
        return template

    def get_template_or_404(self, template_id: int) -> FolderTemplate:
        try:
            return self.repo.get_by_id(template_id)
        except FolderTemplate.DoesNotExist:
            raise NotFoundError(
                message="文件夹模板不存在",
                code="FOLDER_TEMPLATE_NOT_FOUND",
                errors={"template_id": f"ID 为 {template_id} 的模板不存在"},
            ) from None
