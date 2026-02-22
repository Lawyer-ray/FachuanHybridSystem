import ast
import os
import re
from pathlib import Path
from typing import List, Tuple

import pytest


def _backend_root() -> Path:
    return Path(__file__).resolve().parents[2]


def _iter_task_files() -> list[Path]:
    root = _backend_root() / "apps"
    files: list[Path] = []
    for app_dir in root.iterdir():
        if not app_dir.is_dir():
            continue
        for p in app_dir.rglob("tasks*.py"):
            if "__pycache__" in str(p):
                continue
            files.append(p)
        tasks_dir = app_dir / "tasks"
        if tasks_dir.exists():
            for p in tasks_dir.rglob("*.py"):
                if "__pycache__" in str(p):
                    continue
                files.append(p)
    uniq: dict[str, Path] = {str(p): p for p in files}
    return sorted(uniq.values())


def _current_app(file_path: Path) -> str:
    parts = file_path.parts
    if "apps" not in parts:
        return ""
    idx = parts.index("apps")
    if idx + 1 >= len(parts):
        return ""
    return parts[idx + 1]


def _extract_cross_app_imports(file_path: Path) -> list[tuple[int, str, str]]:
    violations: list[tuple[int, str, str]] = []
    content = file_path.read_text(encoding="utf-8")
    tree = ast.parse(content)
    lines = content.splitlines()
    cur_app = _current_app(file_path)

    patterns = [
        r"apps\.(\w+)\.models",
        r"apps\.(\w+)\.services",
    ]

    for node in ast.walk(tree):
        if not isinstance(node, ast.ImportFrom):
            continue
        if not node.module:
            continue
        for pat in patterns:
            m = re.match(pat, node.module)
            if not m:
                continue
            imported_app = m.group(1)
            if imported_app in ("core", cur_app):
                continue
            line_no = getattr(node, "lineno", 0) or 0
            stmt = lines[line_no - 1].strip() if 0 < line_no <= len(lines) else (node.module or "")
            violations.append((line_no, imported_app, stmt))
    return violations


@pytest.mark.property_test
def test_task_layer_no_cross_module_models_or_services_imports():
    backend_root = _backend_root()
    violations: list[str] = []
    for file_path in _iter_task_files():
        rel = os.path.relpath(str(file_path), str(backend_root))
        for line_no, imported_app, stmt in _extract_cross_app_imports(file_path):
            violations.append(f"{rel}:{line_no} - apps.{imported_app} import: {stmt}")
    assert not violations, "task 层跨模块导入守护失败：\n" + "\n".join(f"- {v}" for v in violations)
