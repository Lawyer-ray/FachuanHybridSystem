"""
结构护栏测试: API 层零 try/except

Feature: backend-quality-10, Property 6: API 层零 try/except
Validates: Requirements 10.5, 8.1

使用 AST 解析扫描所有 apps/*/api/ 目录下的 Python 文件，
检测 Try 节点（即 try/except 块）。AST 解析比正则更可靠，
能准确识别 try 语句而非注释或字符串中的 try 文本。
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


# 已知例外：这些文件允许 try/except
ALLOWLIST: set[str] = set()


def _collect_api_files(apps_path: Path) -> list[Path]:
    """收集所有 API 层 Python 文件"""
    api_files: list[Path] = []
    for py_file in apps_path.glob("*/api/**/*.py"):
        if py_file.name == "__init__.py":
            continue
        api_files.append(py_file)
    return api_files


def _find_try_except_nodes(source: str) -> list[int]:
    """使用 AST 解析检测 try/except 块，返回行号列表。

    遍历 AST 树，查找所有 ast.Try 节点。
    """
    line_numbers: list[int] = []
    try:
        tree: ast.Module = ast.parse(source)
    except SyntaxError:
        return line_numbers

    for node in ast.walk(tree):
        if isinstance(node, ast.Try):
            line_numbers.append(node.lineno)
    return line_numbers


def _scan_file_for_try_except(
    file_path: Path,
    backend_path: Path,
) -> list[Violation]:
    """扫描单个文件中的 try/except 块"""
    violations: list[Violation] = []
    content: str = file_path.read_text(encoding="utf-8")
    lines: list[str] = content.splitlines()

    try_lines: list[int] = _find_try_except_nodes(content)
    for line_no in try_lines:
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
def test_api_layer_no_try_except() -> None:
    """
    Property 6: API 层零 try/except

    *For any* apps/*/api/ 目录下的 Python 文件，该文件的 AST 中不应包含
    Try 节点（即不应有 try/except 块）。API 层应依赖
    apps.core.exceptions_handlers 中的全局异常处理器。

    Feature: backend-quality-10, Property 6: API 层零 try/except
    Validates: Requirements 10.5, 8.1
    """
    backend_path: Path = Path(__file__).resolve().parent.parent.parent
    apps_path: Path = backend_path / "apps"

    api_files: list[Path] = _collect_api_files(apps_path)
    assert len(api_files) > 0, "未找到任何 API 层文件，请检查目录结构"

    all_violations: list[Violation] = []

    for file_path in api_files:
        rel: str = os.path.relpath(str(file_path), str(backend_path))
        if rel in ALLOWLIST:
            continue
        all_violations.extend(_scan_file_for_try_except(file_path, backend_path))

    assert not all_violations, f"API 层发现 {len(all_violations)} 处 try/except 违规：\n" + "\n".join(
        f"  - {v.file}:{v.line_no} {v.line_content}" for v in all_violations
    )
