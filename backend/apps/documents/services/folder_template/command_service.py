"""Business logic services."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any

from django.db import transaction

from apps.core.exceptions import NotFoundError, ValidationException
from apps.documents.models import FolderTemplate

from .repo import FolderTemplateRepo
from .structure_rules import FolderTemplateStructureRules
from .validation_service import FolderTemplateValidationService

logger = logging.getLogger(__name__)


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
        **kwargs: Any,
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
        self._sync_bindings_after_structure_change(template)
        self._clear_folder_template_cache()
        return template

    def _sync_bindings_after_structure_change(self, template: FolderTemplate) -> None:
        """结构变更后联动重算该模板所有启用绑定的 folder_node_path。

        - 节点改名/移动：按新结构重算路径（save 时触发模型 hook on_save_compute_folder_node_path）；
        - 节点已不存在于新结构：对应绑定置 is_active=False（不物理删除），并记录 warning。
        """
        from apps.documents.services.template.contract_template.binding_service import DocumentTemplateBindingService

        bindings = list(template.document_bindings.filter(is_active=True))
        if not bindings:
            return

        children = (template.structure or {}).get("children", [])
        binding_service = DocumentTemplateBindingService()
        for binding in bindings:
            path_parts: list[str] = []
            found = binding_service._find_node_path(children, binding.folder_node_id, path_parts)
            if not found:
                binding.is_active = False
                logger.warning(
                    "文件夹结构更新后节点不存在，绑定已停用: template_id=%s, node_id=%s, binding_id=%s",
                    template.id,
                    binding.folder_node_id,
                    binding.id,
                )
                binding.save(update_fields=["folder_node_path", "is_active", "updated_at"])
            elif "/".join(path_parts) != binding.folder_node_path:
                # 路径有变化（改名/移动），保存触发模型 hook 重算 folder_node_path
                binding.save(update_fields=["folder_node_path", "updated_at"])

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
