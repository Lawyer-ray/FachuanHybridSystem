"""Business logic services."""

import ast
import logging
import re
from functools import lru_cache
from pathlib import Path
from typing import Any

from .code_placeholder_registry import CodePlaceholderDefinition, CodePlaceholderRegistry

logger = logging.getLogger(__name__)


class CodePlaceholderCatalogService:
    _KEY_PATTERN = re.compile(r"^[\w\u4e00-\u9fff][\w\u4e00-\u9fff\.\(\)]*$")

    def list_definitions(self) -> list[CodePlaceholderDefinition]:
        definitions: dict[str, CodePlaceholderDefinition] = {}

        for definition in self._from_code_registry():
            definitions.setdefault(definition.key, definition)

        for definition in self._from_registry():
            definitions.setdefault(definition.key, definition)

        for definition in self._from_spec_files_scan():
            definitions.setdefault(definition.key, definition)

        for definition in self._from_evidence_list():
            definitions.setdefault(definition.key, definition)

        for definition in self._from_generation_ast_scan():
            definitions.setdefault(definition.key, definition)

        return sorted(definitions.values(), key=lambda d: d.key)

    def get_definition(self, key: str) -> CodePlaceholderDefinition | None:
        for definition in self.list_definitions():
            if definition.key == key:
                return definition
        return None

    def list_keys(self) -> list[str]:
        return [d.key for d in self.list_definitions()]

    def _from_code_registry(self) -> list[CodePlaceholderDefinition]:
        return CodePlaceholderRegistry().list_definitions()

    def _from_registry(self) -> list[CodePlaceholderDefinition]:
        from apps.documents.services.placeholders import PlaceholderRegistry

        registry = PlaceholderRegistry()
        result: list[CodePlaceholderDefinition] = []
        for service in registry.get_all_services():
            source = getattr(service, "display_name", "") or getattr(service, "name", "") or service.__class__.__name__
            category = getattr(service, "category", "") or "general"
            service_description = getattr(service, "description", "") or ""
            metadata: dict[str, Any] = {}
            if hasattr(service, "get_placeholder_metadata"):
                metadata = service.get_placeholder_metadata() or {}
            for key in service.get_placeholder_keys():
                key_meta = metadata.get(key, {}) or {}
                result.append(
                    CodePlaceholderDefinition(
                        key=key,
                        source=source,
                        category=category,
                        display_name=key_meta.get("display_name") or "",
                        description=key_meta.get("description") or service_description,
                        example_value=key_meta.get("example_value") or "",
                    )
                )
        return result

    def _from_spec_files_scan(self) -> list[CodePlaceholderDefinition]:
        apps_root = Path(__file__).resolve().parents[2]
        if not apps_root.exists():
            return []
        return _scan_placeholder_spec_files(apps_root)

    def _from_evidence_list(self) -> list[CodePlaceholderDefinition]:
        from apps.documents.services.evidence_list_placeholder_service import EvidenceListPlaceholderService

        service = EvidenceListPlaceholderService()
        keys = list(service.get_placeholder_keys() or [])

        return [
            CodePlaceholderDefinition(
                key=key,
                source="证据清单",
                category="evidence",
                display_name=key,
                description="证据清单导出占位符",
            )
            for key in keys
        ]

    def _from_generation_ast_scan(self) -> list[CodePlaceholderDefinition]:
        root = Path(__file__).resolve().parents[1] / "services"
        if not root.exists():
            return []

        keys = self._scan_python_files_for_context_keys(root)
        result: list[CodePlaceholderDefinition] = []
        for key in sorted(keys):
            result.append(
                CodePlaceholderDefinition(
                    key=key,
                    source="生成器扫描",
                    category="generated",
                    display_name=key,
                    description="从生成器代码中自动提取的上下文键",
                )
            )
        return result

    def _scan_python_files_for_context_keys(self, root: Path) -> set[str]:
        collected: set[str] = set()
        for file_path in root.rglob("*.py"):
            try:
                content = file_path.read_text(encoding="utf-8")
            except Exception:
                logger.exception("操作失败")

                continue
            if "DocxTemplate" not in content and "docxtpl" not in content:
                continue
            try:
                tree = ast.parse(content, filename=str(file_path))
            except SyntaxError:
                continue

            visitor = _ContextDictKeyVisitor()
            visitor.visit(tree)
            for key in visitor.keys:
                if not self._is_placeholder_key_candidate(key):
                    continue
                if not self._looks_like_template_placeholder(key):
                    continue
                collected.add(key)

        return collected

    def _is_placeholder_key_candidate(self, key: str) -> bool:
        return bool(key and self._KEY_PATTERN.match(key))

    def _looks_like_template_placeholder(self, key: str) -> bool:
        return any("\u4e00" <= ch <= "\u9fff" for ch in key)


class _ContextDictKeyVisitor(ast.NodeVisitor):
    def __init__(self) -> None:
        self.keys: set[str] = set()

    def visit_Return(self, node: ast.Return) -> None:
        self._collect_from_value(node.value)
        self.generic_visit(node)

    def visit_Assign(self, node: ast.Assign) -> None:
        for target in node.targets:
            if isinstance(target, ast.Name) and target.id == "context":
                self._collect_from_value(node.value)
        self.generic_visit(node)

    def _collect_from_value(self, value: ast.AST | None) -> None:
        if isinstance(value, ast.Dict):
            for k in value.keys:
                if isinstance(k, ast.Constant) and isinstance(k.value, str):
                    self.keys.add(k.value)


@lru_cache(maxsize=1)
def _scan_placeholder_spec_files(apps_root: Path) -> list[CodePlaceholderDefinition]:
    result: list[CodePlaceholderDefinition] = []

    for spec_path in apps_root.rglob("placeholders/spec.py"):
        result.extend(_extract_definitions_from_spec(spec_path))

    dedup: dict[str, CodePlaceholderDefinition] = {}
    for definition in result:
        dedup.setdefault(definition.key, definition)
    return list(dedup.values())


def _extract_definitions_from_spec(spec_path: Path) -> list[CodePlaceholderDefinition]:
    try:
        content = spec_path.read_text(encoding="utf-8")
    except Exception:
        logger.exception("操作失败")

        return []
    try:
        tree = ast.parse(content, filename=str(spec_path))
    except SyntaxError:
        return []

    source, category, description = _spec_metadata(spec_path)
    definitions: list[CodePlaceholderDefinition] = []

    for node in tree.body:
        if not isinstance(node, ast.ClassDef) or not node.name.endswith("PlaceholderKeys"):
            continue
        for stmt in node.body:
            key = _extract_string_assignment(stmt)
            if key:
                definitions.append(
                    CodePlaceholderDefinition(
                        key=key,
                        source=source,
                        category=category,
                        display_name=key,
                        description=description,
                    )
                )
    return definitions


def _spec_metadata(spec_path: Path) -> tuple[str, str, str]:
    app_name = spec_path.parts[-3] if len(spec_path.parts) >= 3 else "unknown"
    if app_name == "litigation_ai":
        return "诉讼文书", "litigation", "诉讼文书生成上下文占位符"
    return f"{app_name} 占位符", app_name, "从 placeholders/spec.py 自动发现的占位符键"


def _extract_string_assignment(stmt: ast.stmt) -> str | None:
    if not isinstance(stmt, ast.Assign) or not stmt.targets:
        return None
    if isinstance(stmt.value, ast.Constant) and isinstance(stmt.value.value, str) and stmt.value.value:
        return stmt.value.value
    return None
