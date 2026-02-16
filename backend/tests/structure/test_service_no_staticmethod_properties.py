"""
结构护栏测试: Service 层零 @staticmethod

Feature: backend-quality-10, Property 5: Service 层零 @staticmethod
Validates: Requirements 10.4, 7.1

使用 AST 解析扫描所有 apps/*/services/ 目录下的 Python 文件，
检测 @staticmethod 装饰器。AST 解析比正则更可靠，能准确识别
装饰器节点而非注释或字符串中的 @staticmethod 文本。
"""

import ast
import os
from pathlib import Path
from typing import NamedTuple

import pytest


class Violation(NamedTuple):
    file: str
    line_no: int
    function_name: str


def _collect_service_files(apps_path: Path) -> list[Path]:
    """收集所有 Service 层 Python 文件"""
    service_files: list[Path] = []
    for py_file in apps_path.glob("*/services/**/*.py"):
        if py_file.name == "__init__.py":
            continue
        service_files.append(py_file)
    return service_files


def _find_staticmethod_decorators(source: str) -> list[tuple[int, str]]:
    """使用 AST 解析检测 @staticmethod 装饰器。

    遍历 AST 树，查找 FunctionDef 节点中装饰器为
    ast.Name(id='staticmethod') 的情况。
    返回 (行号, 函数名) 列表。
    """
    results: list[tuple[int, str]] = []
    try:
        tree: ast.Module = ast.parse(source)
    except SyntaxError:
        return results

    for node in ast.walk(tree):
        if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        for decorator in node.decorator_list:
            if isinstance(decorator, ast.Name) and decorator.id == "staticmethod":
                results.append((decorator.lineno, node.name))
    return results


def _scan_file_for_staticmethod(
    file_path: Path,
    backend_path: Path,
) -> list[Violation]:
    """扫描单个文件中的 @staticmethod 装饰器"""
    violations: list[Violation] = []
    content: str = file_path.read_text(encoding="utf-8")

    hits: list[tuple[int, str]] = _find_staticmethod_decorators(content)
    for line_no, func_name in hits:
        violations.append(
            Violation(
                file=os.path.relpath(str(file_path), str(backend_path)),
                line_no=line_no,
                function_name=func_name,
            )
        )
    return violations


@pytest.mark.property_test
def test_service_layer_no_staticmethod() -> None:
    """
    Property 5: Service 层零 @staticmethod

    *For any* apps/*/services/ 目录下的 Python 文件，该文件内容不应包含
    @staticmethod 装饰器。

    Feature: backend-quality-10, Property 5: Service 层零 @staticmethod
    Validates: Requirements 10.4, 7.1
    """
    backend_path: Path = Path(__file__).resolve().parent.parent.parent
    apps_path: Path = backend_path / "apps"

    service_files: list[Path] = _collect_service_files(apps_path)
    assert len(service_files) > 0, "未找到任何 Service 层文件，请检查目录结构"

    all_violations: list[Violation] = []

    for file_path in service_files:
        all_violations.extend(_scan_file_for_staticmethod(file_path, backend_path))

    assert not all_violations, f"Service 层发现 {len(all_violations)} 处 @staticmethod 违规：\n" + "\n".join(
        f"  - {v.file}:{v.line_no} @staticmethod def {v.function_name}()" for v in all_violations
    )
