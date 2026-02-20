"""Business logic services."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, cast

from apps.documents.models import FolderTemplate

from .id_service import FolderTemplateIdService


@dataclass(frozen=True)
class FolderTemplateStructureIdRepairService:
    id_service: FolderTemplateIdService

    def detect_cross_template_duplicates(self, *, templates: list[FolderTemplate]) -> set[str]:
        global_used_ids: set[str] = set()
        duplicate_ids: set[str] = set()

        for template in templates:
            if template.structure and isinstance(template.structure, dict):
                template_ids = self.id_service.collect_structure_ids(template.structure) or []
                for id_val in template_ids:
                    if id_val in global_used_ids:
                        duplicate_ids.add(id_val)
                    else:
                        global_used_ids.add(id_val)

        return duplicate_ids

    def repair_structure_ids_global(
        self, *, structure: dict[str, Any], global_used_ids: set[str]
    ) -> tuple[dict[str, Any], int]:
        if not isinstance(structure, dict):
            return structure, 0

        changes = 0

        def next_unique_id() -> str:
            new_id = self.id_service.generate_unique_id()
            while new_id in global_used_ids:
                new_id = self.id_service.generate_unique_id()
            return new_id

        def repair_node(node) -> None: # type: ignore
            nonlocal changes
            if not isinstance(node, dict):
                return cast(None, node)

            current_id = node.get("id")
            if not current_id or current_id in global_used_ids:
                new_id = next_unique_id()
                node["id"] = new_id
                global_used_ids.add(new_id)
                changes += 1
            else:
                global_used_ids.add(current_id)

            children = node.get("children")
            if isinstance(children, list):
                node["children"] = [repair_node(child) for child in children] # type: ignore

            return node # type: ignore

        fixed_structure = structure.copy()
        children = fixed_structure.get("children")
        if isinstance(children, list):
            fixed_structure["children"] = [repair_node(child) for child in children] # type: ignore

        return fixed_structure, changes
