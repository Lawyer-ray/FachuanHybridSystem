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
    result: Set[str] = set()
    for raw in baseline_path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        # 去除内联注释（# 原因：...），保留导入路径部分
        entry = line.split(" # ")[0].strip()
        if entry:
            result.add(entry)
    return result


def _get_type_checking_linenos(tree: ast.AST) -> Set[int]:
    """返回 TYPE_CHECKING 块内所有语句的行号集合，这些导入仅用于类型注解，运行时不执行."""
    linenos: Set[int] = set()
    for node in ast.walk(tree):
        if not isinstance(node, ast.If):
            continue
        test = node.test
        # 匹配 `if TYPE_CHECKING:` 或 `if typing.TYPE_CHECKING:`
        is_type_checking = (isinstance(test, ast.Name) and test.id == "TYPE_CHECKING") or (
            isinstance(test, ast.Attribute)
            and test.attr == "TYPE_CHECKING"
            and isinstance(test.value, ast.Name)
            and test.value.id == "typing"
        )
        if not is_type_checking:
            continue
        for child in ast.walk(node):
            if hasattr(child, "lineno"):
                linenos.add(child.lineno)  # type: ignore[attr-defined]
    return linenos


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

        type_checking_lines = _get_type_checking_linenos(tree)

        for node in ast.walk(tree):
            if not isinstance(node, ast.ImportFrom):
                continue
            # 跳过 TYPE_CHECKING 块内的导入（仅用于类型注解，运行时不执行）
            if node.lineno in type_checking_lines:
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
    assert (
        not extra
    ), "发现新增跨 app 的 models 导入（请通过 Protocol/ServiceLocator 解耦，或显式更新 baseline）:\n" + "\n".join(extra)
