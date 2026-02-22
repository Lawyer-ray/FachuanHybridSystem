"""
架构违规探索测试（Bug Condition Exploration）

Property 1: Fault Condition - Service 层 try/except 和 @staticmethod 违规检测

使用 AST 静态分析检测目标文件中的 try/except 和 @staticmethod 违规。
此测试在未修复代码上 FAIL（确认违规存在），修复后 PASS（确认违规已修复）。

Validates: Requirements 1.1, 1.2, 1.3, 1.4, 1.5, 1.6, 1.7, 1.8, 1.9, 1.10
"""

import ast
import logging
from pathlib import Path
from typing import NamedTuple

import pytest

logger = logging.getLogger(__name__)

# backend 根目录
BACKEND_ROOT: Path = Path(__file__).resolve().parent.parent.parent.parent


class TryExceptViolation(NamedTuple):
    """try/except 违规记录"""

    file: str
    method: str
    line_no: int


class StaticMethodViolation(NamedTuple):
    """@staticmethod 违规记录"""

    file: str
    class_name: str
    method: str
    line_no: int


def _find_try_except_in_method(
    tree: ast.Module,
    method_name: str,
) -> list[int]:
    """在 AST 中查找指定方法内的 try/except 块行号。

    Args:
        tree: 已解析的 AST 模块
        method_name: 目标方法名

    Returns:
        try/except 块的行号列表
    """
    results: list[int] = []
    for node in ast.walk(tree):
        if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        if node.name != method_name:
            continue
        # 在该方法体内查找 Try 节点
        for child in ast.walk(node):
            if isinstance(child, ast.Try):
                results.append(child.lineno)
    return results


def _find_staticmethod_in_class(
    tree: ast.Module,
    class_name: str,
) -> list[tuple[str, int]]:
    """在 AST 中查找指定类内的 @staticmethod 装饰器。

    Args:
        tree: 已解析的 AST 模块
        class_name: 目标类名

    Returns:
        (方法名, 行号) 列表
    """
    results: list[tuple[str, int]] = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.ClassDef):
            continue
        if node.name != class_name:
            continue
        for item in node.body:
            if not isinstance(item, (ast.FunctionDef, ast.AsyncFunctionDef)):
                continue
            for decorator in item.decorator_list:
                if isinstance(decorator, ast.Name) and decorator.id == "staticmethod":
                    results.append((item.name, decorator.lineno))
    return results


def _parse_file(rel_path: str) -> ast.Module | None:
    """解析文件为 AST，文件不存在则返回 None。

    Args:
        rel_path: 相对于 backend 根目录的路径

    Returns:
        AST 模块或 None
    """
    full_path: Path = BACKEND_ROOT / rel_path
    if not full_path.exists():
        return None
    source: str = full_path.read_text(encoding="utf-8")
    return ast.parse(source)


# ==================== try/except 检测配置 ====================

# (相对路径, 需检测的方法列表)
TRY_EXCEPT_TARGETS: list[tuple[str, list[str]]] = [
    (
        "apps/core/services/system_config_service.py",
        ["update_config", "delete_config", "get_config", "get_value"],
    ),
    (
        "apps/core/services/cause_court_query_service.py",
        ["get_cause_by_id_internal"],
    ),
    (
        "apps/core/services/cause_court_initialization_service.py",
        ["_get_zxfw_token"],
    ),
]

# ==================== @staticmethod 检测配置 ====================

# (相对路径, 需检测的类列表)
STATICMETHOD_TARGETS: list[tuple[str, list[str]]] = [
    (
        "apps/core/infrastructure/cache.py",
        ["CacheTimeout"],
    ),
    (
        "apps/core/cache.py",
        ["_CacheTimeout"],
    ),
    (
        "apps/core/infrastructure/monitoring.py",
        ["PerformanceMonitor"],
    ),
    (
        "apps/core/monitoring.py",
        ["PerformanceMonitor"],
    ),
    (
        "apps/core/schemas.py",
        ["TimestampMixin", "DisplayLabelMixin", "FileFieldMixin"],
    ),
    (
        "apps/core/exceptions/automation_factory.py",
        ["AutomationExceptions"],
    ),
]


@pytest.mark.property_test
def test_service_layer_no_try_except_in_target_methods() -> None:
    """
    Property 1 (try/except): Service 层目标方法不包含 try/except

    断言指定 Service 方法中不存在 try/except 块。
    未修复代码上此测试 FAIL（确认违规存在）。

    Validates: Requirements 1.1, 1.2, 1.3, 1.4, 1.5, 1.6
    """
    violations: list[TryExceptViolation] = []

    for rel_path, methods in TRY_EXCEPT_TARGETS:
        tree: ast.Module | None = _parse_file(rel_path)
        assert tree is not None, f"文件不存在: {rel_path}"

        for method_name in methods:
            hits: list[int] = _find_try_except_in_method(tree, method_name)
            for line_no in hits:
                violations.append(
                    TryExceptViolation(
                        file=rel_path,
                        method=method_name,
                        line_no=line_no,
                    )
                )

    assert not violations, (
        f"Service 层发现 {len(violations)} 处 try/except 违规:\n"
        + "\n".join(
            f"  - {v.file}:{v.line_no} method={v.method}"
            for v in violations
        )
    )


@pytest.mark.property_test
def test_service_layer_no_staticmethod_in_target_classes() -> None:
    """
    Property 1 (@staticmethod): Service 层目标类不包含 @staticmethod

    断言指定类中不存在 @staticmethod 装饰器。
    未修复代码上此测试 FAIL（确认违规存在）。

    Validates: Requirements 1.7, 1.8, 1.9, 1.10
    """
    violations: list[StaticMethodViolation] = []

    for rel_path, classes in STATICMETHOD_TARGETS:
        tree: ast.Module | None = _parse_file(rel_path)
        assert tree is not None, f"文件不存在: {rel_path}"

        for class_name in classes:
            hits: list[tuple[str, int]] = _find_staticmethod_in_class(
                tree, class_name
            )
            for method_name, line_no in hits:
                violations.append(
                    StaticMethodViolation(
                        file=rel_path,
                        class_name=class_name,
                        method=method_name,
                        line_no=line_no,
                    )
                )

    assert not violations, (
        f"Service 层发现 {len(violations)} 处 @staticmethod 违规:\n"
        + "\n".join(
            f"  - {v.file}:{v.line_no} {v.class_name}.{v.method}"
            for v in violations
        )
    )
