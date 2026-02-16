"""Business logic services."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from .id_service import FolderTemplateIdService


@dataclass(frozen=True)
class FolderTemplateStructureRules:
    id_service: FolderTemplateIdService

    def validate_and_fix_structure_ids(
        self, structure: dict[str, Any], template_id: int | None = None
    ) -> tuple[bool, dict[str, Any], list[str]]:
        if not structure or not isinstance(structure, dict):
            return False, structure, []

        current_ids = self.id_service.collect_structure_ids(structure)
        internal_duplicates = self.id_service.find_internal_duplicates(current_ids)  # type: ignore[arg-type]
        global_duplicates = self.id_service.find_global_duplicates(current_ids, template_id)  # type: ignore[arg-type]

        all_duplicates = internal_duplicates | global_duplicates
        if not all_duplicates:
            return False, structure, []

        import copy

        fixed_structure = copy.deepcopy(structure)
        self.id_service.replace_duplicate_ids_in_structure(fixed_structure, all_duplicates)
        fix_messages = [f"已自动修复 {len(all_duplicates)} 个重复ID: {', '.join(sorted(all_duplicates))}"]
        return True, fixed_structure, fix_messages

    def validate_structure_ids(
        self, structure: dict[str, Any], template_id: int | None = None
    ) -> tuple[bool, list[str]]:
        if not structure or not isinstance(structure, dict):
            return True, []

        current_ids = self.id_service.collect_structure_ids(structure)
        internal_duplicates = self.id_service.find_internal_duplicates(current_ids)  # type: ignore[arg-type]
        if internal_duplicates:
            return False, [f"结构内部存在重复ID: {', '.join(internal_duplicates)}"]

        global_duplicates = self.id_service.find_global_duplicates(current_ids, template_id)  # type: ignore[arg-type]
        if global_duplicates:
            return False, [f"结构ID与其他模板重复: {', '.join(global_duplicates)}"]

        return True, []
