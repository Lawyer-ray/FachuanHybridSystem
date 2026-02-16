"""Business logic services."""

from __future__ import annotations

import re
from typing import Any


class FolderTemplateValidationService:
    INVALID_CHARS = r'[/\\:*?"<>|]'
    INVALID_CHARS_PATTERN = re.compile(INVALID_CHARS)

    def validate_structure(self, structure: dict[str, Any]) -> tuple[bool, str]:
        if not isinstance(structure, dict):
            return False, "结构必须是字典类型"

        has_cycle, cycle_path = self._check_circular_reference(structure)
        if has_cycle:
            return False, f"检测到循环引用: {cycle_path}"

        has_invalid, invalid_info = self._check_invalid_chars(structure)
        if has_invalid:
            return False, f"文件夹名称包含无效字符: {invalid_info}"

        return True, ""

    def _check_circular_reference(
        self, structure: dict[str, Any], visited_ids: set[Any] | None = None, path: list[str] | None = None
    ) -> tuple[bool, str]:
        if visited_ids is None:
            visited_ids = set()
        if path is None:
            path = []

        children = structure.get("children", [])
        if not isinstance(children, list):
            return False, ""

        for child in children:
            if not isinstance(child, dict):
                continue

            node_id = child.get("id")
            node_name = child.get("name", "unknown")
            current_path = path + [node_name]

            if node_id is not None:
                if node_id in visited_ids:
                    return True, " -> ".join(current_path)
                visited_ids.add(node_id)

            has_cycle, cycle_path = self._check_circular_reference(child, visited_ids.copy(), current_path)
            if has_cycle:
                return True, cycle_path

        return False, ""

    def _check_invalid_chars(self, structure: dict[str, Any], path: list[str] | None = None) -> tuple[bool, str]:
        if path is None:
            path = []

        children = structure.get("children", [])
        if not isinstance(children, list):
            return False, ""

        for child in children:
            if not isinstance(child, dict):
                continue

            name = child.get("name", "")
            current_path = path + [name]

            if name and self.INVALID_CHARS_PATTERN.search(name):
                invalid_chars = self.INVALID_CHARS_PATTERN.findall(name)
                return True, f"'{name}' 包含无效字符: {invalid_chars}"

            has_invalid, invalid_info = self._check_invalid_chars(child, current_path)
            if has_invalid:
                return True, invalid_info

        return False, ""
