"""
确保项目代码不包含 Django 6 不兼容的 format_html 单参数调用。
"""

import ast
from pathlib import Path


def _project_root() -> Path:
    return Path(__file__).parent.parent.parent


def _iter_python_files(root: Path) -> list[Path]:
    exclude_dirs = {
        "__pycache__",
        "node_modules",
        "venv",
        "venv311",
        "venv312",
        ".venv",
        "htmlcov",
        ".hypothesis",
        ".mypy_cache",
        ".pytest_cache",
        ".git",
        ".idea",
        ".vscode",
        "migrations",
        "staticfiles",
    }

    python_files: list[Path] = []
    for item in root.rglob("*.py"):
        if any(excluded in item.parts for excluded in exclude_dirs):
            continue
        python_files.append(item)
    return python_files


def _is_format_html_call(node: ast.Call) -> bool:
    func = node.func
    if isinstance(func, ast.Name) and func.id == "format_html":
        return True
    if isinstance(func, ast.Attribute) and func.attr == "format_html":
        return True
    return False


def _find_single_arg_format_html_calls(file_path: Path) -> list[tuple[str, int]]:
    try:
        content = file_path.read_text(encoding="utf-8")
        tree = ast.parse(content)
    except (SyntaxError, UnicodeDecodeError):
        return []

    hits: list[tuple[str, int]] = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        if not _is_format_html_call(node):
            continue
        if len(node.args) == 1 and not node.keywords:
            hits.append((str(file_path), node.lineno))
    return hits


def test_no_single_arg_format_html_calls():
    root = _project_root()
    hits: list[tuple[str, int]] = []
    for file_path in _iter_python_files(root):
        hits.extend(_find_single_arg_format_html_calls(file_path))

    assert not hits, "发现 Django 6 不兼容的 format_html 单参数调用:\n" + "\n".join(
        f"- {path}:{lineno}" for path, lineno in hits
    )
