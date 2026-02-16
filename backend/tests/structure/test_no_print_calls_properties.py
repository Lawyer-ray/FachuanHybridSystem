"""
结构护栏测试: 全项目零 print() 调用

Feature: backend-quality-10, Property 4: 全项目零 print() 调用
Validates: Requirements 10.3, 4.1

使用 AST 解析扫描所有 apps/ 目录下的 Python 文件（排除 migrations/、
management/commands/、__init__.py、测试文件），检测 print() 函数调用。
AST 解析自动排除 docstring 和注释中的 print。
"""

import ast
import os
from pathlib import Path
from typing import NamedTuple

import pytest


class Violation(NamedTuple):
    file: str
    line_no: int
    line_content: str


# 需要排除的目录和文件模式
EXCLUDED_DIRS: set[str] = {
    "migrations",
    "management",
}

EXCLUDED_PREFIXES: tuple[str, ...] = (
    "test_",
    "conftest",
)


def _should_skip_file(file_path: Path) -> bool:
    """判断文件是否应跳过扫描"""
    if file_path.name == "__init__.py":
        return True
    if file_path.name.startswith(EXCLUDED_PREFIXES):
        return True
    # 排除 migrations/ 和 management/commands/ 目录
    parts: tuple[str, ...] = file_path.parts
    for i, part in enumerate(parts):
        if part == "migrations":
            return True
        if part == "management" and i + 1 < len(parts) and parts[i + 1] == "commands":
            return True
    return False


def _collect_app_files(apps_path: Path) -> list[Path]:
    """收集所有 apps/ 目录下需要扫描的 Python 文件"""
    py_files: list[Path] = []
    for py_file in apps_path.glob("**/*.py"):
        if _should_skip_file(py_file):
            continue
        py_files.append(py_file)
    return py_files


def _find_print_calls(source: str) -> list[int]:
    """使用 AST 解析检测 print() 函数调用，返回行号列表。

    AST 解析天然排除 docstring 和注释中的 print，
    仅检测实际的 print() 函数调用节点。
    """
    line_numbers: list[int] = []
    try:
        tree: ast.Module = ast.parse(source)
    except SyntaxError:
        return line_numbers

    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        func: ast.expr = node.func
        # 匹配直接调用: print(...)
        if isinstance(func, ast.Name) and func.id == "print":
            line_numbers.append(node.lineno)
    return line_numbers


def _scan_file_for_print_calls(
    file_path: Path,
    backend_path: Path,
) -> list[Violation]:
    """扫描单个文件中的 print() 调用"""
    violations: list[Violation] = []
    content: str = file_path.read_text(encoding="utf-8")
    lines: list[str] = content.splitlines()

    print_lines: list[int] = _find_print_calls(content)
    for line_no in print_lines:
        line_content: str = lines[line_no - 1].strip() if line_no <= len(lines) else ""
        violations.append(
            Violation(
                file=os.path.relpath(str(file_path), str(backend_path)),
                line_no=line_no,
                line_content=line_content,
            )
        )
    return violations


@pytest.mark.property_test
def test_no_print_calls_in_apps() -> None:
    """
    Property 4: 全项目零 print() 调用

    *For any* apps/ 目录下的 Python 文件（排除 migrations/、management/commands/、
    __init__.py、测试文件），该文件不应包含 print() 函数调用。

    Feature: backend-quality-10, Property 4: 全项目零 print() 调用
    Validates: Requirements 10.3, 4.1
    """
    backend_path: Path = Path(__file__).resolve().parent.parent.parent
    apps_path: Path = backend_path / "apps"

    py_files: list[Path] = _collect_app_files(apps_path)
    assert len(py_files) > 0, "未找到任何 apps/ 下的 Python 文件，请检查目录结构"

    all_violations: list[Violation] = []

    for file_path in py_files:
        all_violations.extend(_scan_file_for_print_calls(file_path, backend_path))

    assert not all_violations, f"发现 {len(all_violations)} 处 print() 调用违规：\n" + "\n".join(
        f"  - {v.file}:{v.line_no} {v.line_content}" for v in all_violations
    )
