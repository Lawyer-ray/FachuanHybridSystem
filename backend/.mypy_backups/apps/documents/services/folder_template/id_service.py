"""Business logic services."""
from __future__ import annotations

import random
import string
import time

from apps.documents.models import FolderTemplate
from typing import Optional
from typing import Any


class FolderTemplateIdService:
    def collect_structure_ids(self, structure: dict[str, Any]) -> Optional[list[str]]:
        ids: list[str] = []

        def collect_from_node(node) -> None:
            if not isinstance(node, dict):
                return
            if node.get("id"):
                ids.append(node["id"])
            if "children" in node and isinstance(node["children"], list):
                for child in node["children"]:
                    collect_from_node(child)

        if "children" in structure and isinstance(structure["children"], list):
            for child in structure["children"]:
                collect_from_node(child)

        return ids

    def find_internal_duplicates(self, ids: list[str]) -> set[Any][str]:
        seen = set()
        duplicates = set()
        for id_val in ids:
            if id_val in seen:
                duplicates.add(id_val)
            else:
                seen.add(id_val)
        return duplicates

    def find_global_duplicates(self, ids: list[str], exclude_template_id: int | None = None) -> set[Any][str]:
        if not ids:
            return set()

        other_templates = FolderTemplate.objects.all()
        if exclude_template_id:
            other_templates = other_templates.exclude(id=exclude_template_id)

        other_templates = list(other_templates)

        existing_ids = set()
        for template in other_templates:
            if template.structure:
                template_ids = self.collect_structure_ids(template.structure)
                existing_ids.update(template_ids)

        return set(ids) & existing_ids

    def replace_duplicate_ids_in_structure(self, structure: dict[str, Any], duplicate_ids: set[str]) -> None:
        def replace_in_node(node) -> None:
            if not isinstance(node, dict):
                return
            if "id" in node and node["id"] in duplicate_ids:
                node["id"] = self.generate_unique_id()
            if "children" in node and isinstance(node["children"], list):
                for child in node["children"]:
                    replace_in_node(child)

        if "children" in structure and isinstance(structure["children"], list):
            for child in structure["children"]:
                replace_in_node(child)

    def generate_unique_id(self) -> str:
        timestamp = int(time.time() * 1000)
        random_suffix = "".join(random.choices(string.ascii_lowercase + string.digits, k=8))
        new_id = f"folder_{timestamp}_{random_suffix}"

        while self.is_id_exists_globally(new_id):
            random_suffix = "".join(random.choices(string.ascii_lowercase + string.digits, k=8))
            new_id = f"folder_{timestamp}_{random_suffix}"

        return new_id

    def is_id_exists_globally(self, id_val: str) -> bool:
        all_templates = list(FolderTemplate.objects.all())

        for template in all_templates:
            if template.structure:
                template_ids = self.collect_structure_ids(template.structure)
                if id_val in template_ids:
                    return True
        return False

    def get_duplicate_id_report(self) -> dict[str, Any]:
        all_templates = FolderTemplate.objects.all()
        global_ids: dict[str, list[Any]] = {}

        for template in all_templates:
            if template.structure:
                template_ids = self.collect_structure_ids(template.structure)
                for id_val in template_ids:
                    if id_val not in global_ids:
                        global_ids[id_val] = []
                    global_ids[id_val].append(template.name)

        duplicates = {id_val: templates for id_val, templates in global_ids.items() if len(templates) > 1}

        return {
            "total_templates": all_templates.count(),
            "total_unique_ids": len(global_ids),
            "duplicate_count": len(duplicates),
            "duplicates": duplicates,
        }
