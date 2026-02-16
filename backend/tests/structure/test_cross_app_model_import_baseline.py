import ast
import re
from pathlib import Path
from typing import List, Set

import pytest


def get_backend_path() -> Path:
    return Path(__file__).parent.parent.parent


def load_baseline(backend_path: Path) -> Set[str]:
    baseline_path = backend_path / "tests" / "structure" / "baselines" / "cross_app_model_imports.txt"
    if not baseline_path.exists():
        return set()
    lines = [line.strip() for line in baseline_path.read_text(encoding="utf-8").splitlines()]
    return {line for line in lines if line and not line.startswith("#")}


def find_cross_app_model_imports(backend_path: Path) -> Set[str]:
    apps_root = backend_path / "apps"
    pattern = re.compile(r"apps\.(\w+)\.models")
    findings: Set[str] = set()

    for py_file in apps_root.rglob("*.py"):
        if "migrations" in py_file.parts or "__pycache__" in py_file.parts:
            continue
        try:
            parts = list(py_file.parts)
            idx = parts.index("apps")
            file_app = parts[idx + 1]
        except Exception:
            continue

        try:
            content = py_file.read_text(encoding="utf-8")
            tree = ast.parse(content)
            lines: List[str] = content.splitlines()
        except Exception:
            continue

        for node in ast.walk(tree):
            if not isinstance(node, ast.ImportFrom):
                continue
            if not node.module or ".models" not in node.module:
                continue
            match = pattern.match(node.module)
            if not match:
                continue
            imported_app = match.group(1)
            if imported_app == file_app:
                continue

            import_line = lines[node.lineno - 1].strip() if 1 <= node.lineno <= len(lines) else node.module
            rel_path = py_file.relative_to(backend_path).as_posix()
            findings.add(f"{rel_path}:{node.lineno}:{import_line}")

    return findings


@pytest.mark.unit
def test_cross_app_model_imports_do_not_increase():
    backend_path = get_backend_path()
    baseline = load_baseline(backend_path)
    current = find_cross_app_model_imports(backend_path)

    extra = sorted(current - baseline)
    assert not extra, "发现新增跨 app 的 models 导入（请通过 Protocol/ServiceLocator 解耦，或显式更新 baseline）:\n" + "\n".join(extra)
