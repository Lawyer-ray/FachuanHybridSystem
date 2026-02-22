"""
第二轮架构违规探索测试

通过 AST 静态分析验证 10 处架构违规已被消除。
每个测试方法对应一处违规检查。

Validates: Requirements 1.1, 1.2, 1.3, 1.4, 1.5, 1.6, 1.7, 1.8, 1.9, 1.10
"""

from __future__ import annotations

import ast
import logging
from pathlib import Path
from typing import Any

import pytest

logger = logging.getLogger(__name__)

# 项目根目录
_BACKEND_ROOT: Path = Path(__file__).resolve().parent.parent.parent.parent


def _parse_file(relative_path: str) -> ast.Module:
    """解析指定文件的 AST"""
    file_path: Path = _BACKEND_ROOT / relative_path
    source: str = file_path.read_text(encoding="utf-8")
    return ast.parse(source, filename=str(file_path))


def _get_function_node(tree: ast.Module, func_name: str) -> ast.FunctionDef | None:
    """获取模块级函数的 AST 节点"""
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name == func_name:
            return node
    return None


def _get_method_node(tree: ast.Module, class_name: str, method_name: str) -> ast.FunctionDef | None:
    """获取类方法的 AST 节点"""
    for node in ast.walk(tree):
        if isinstance(node, ast.ClassDef) and node.name == class_name:
            for item in node.body:
                if isinstance(item, (ast.FunctionDef, ast.AsyncFunctionDef)) and item.name == method_name:
                    return item
    return None


def _get_property_node(tree: ast.Module, class_name: str, prop_name: str) -> ast.FunctionDef | None:
    """获取类 @property 方法的 AST 节点"""
    for node in ast.walk(tree):
        if isinstance(node, ast.ClassDef) and node.name == class_name:
            for item in node.body:
                if isinstance(item, ast.FunctionDef) and item.name == prop_name:
                    for decorator in item.decorator_list:
                        if isinstance(decorator, ast.Name) and decorator.id == "property":
                            return item
    return None


def _has_import_from(tree: ast.Module, module: str, name: str) -> bool:
    """检查模块顶层是否有 from module import name"""
    for node in ast.iter_child_nodes(tree):
        if isinstance(node, ast.ImportFrom) and node.module == module:
            for alias in node.names:
                if alias.name == name:
                    return True
    return False


def _has_local_import_in_func(func_node: ast.FunctionDef, module: str, name: str) -> bool:
    """检查函数体内是否有局部 from module import name"""
    for node in ast.walk(func_node):
        if isinstance(node, ast.ImportFrom) and node.module == module:
            for alias in node.names:
                if alias.name == name:
                    return True
    return False


def _func_body_contains_while(func_node: ast.FunctionDef, target_name: str) -> bool:
    """检查函数体内是否包含 while target_name: 循环"""
    for node in ast.walk(func_node):
        if isinstance(node, ast.While):
            test = node.test
            if isinstance(test, ast.Name) and test.id == target_name:
                return True
    return False


def _func_body_contains_call(func_node: ast.FunctionDef, call_pattern: str) -> bool:
    """
    检查函数体内是否包含指定的调用模式。
    支持 'obj.method()' 和 'obj.attr.method()' 格式。
    """
    source_lines: list[str] = ast.get_source_segment.__doc__ or ""  # type: ignore[assignment]
    # 使用 ast.dump 遍历所有 Call 节点
    for node in ast.walk(func_node):
        if isinstance(node, ast.Call):
            call_str = _call_to_string(node.func)
            if call_str and call_pattern in call_str:
                return True
    return False


def _call_to_string(node: ast.expr) -> str | None:
    """将 AST 调用表达式转为字符串表示"""
    if isinstance(node, ast.Attribute):
        value_str = _call_to_string(node.value)
        if value_str:
            return f"{value_str}.{node.attr}"
        return node.attr
    if isinstance(node, ast.Name):
        return node.id
    return None


def _func_source_contains(relative_path: str, func_node: ast.FunctionDef, pattern: str) -> bool:
    """通过读取源码文本检查函数体内是否包含指定字符串模式"""
    file_path: Path = _BACKEND_ROOT / relative_path
    source_lines: list[str] = file_path.read_text(encoding="utf-8").splitlines()
    # func_node.lineno 是函数定义行（1-indexed），end_lineno 是函数结束行
    start: int = func_node.lineno - 1
    end: int = func_node.end_lineno or start + 1
    func_source: str = "\n".join(source_lines[start:end])
    return pattern in func_source


# ============================================================
# 测试类
# ============================================================


class TestArchitectureViolationsAbsent:
    """验证第二轮 10 处架构违规已被消除"""

    # ----------------------------------------------------------
    # Issue 1: generation_api.py 不应包含 build_contract_query_service 导入
    # Validates: Requirements 1.1
    # ----------------------------------------------------------
    def test_generation_api_no_build_dependency_import(self) -> None:
        """generation_api.py 不应包含 from apps.core.dependencies import build_contract_query_service"""
        tree: ast.Module = _parse_file("apps/documents/api/generation_api.py")
        has_violation: bool = _has_import_from(tree, "apps.core.dependencies", "build_contract_query_service")
        assert not has_violation, (
            "generation_api.py 仍包含 'from apps.core.dependencies import build_contract_query_service' 导入"
        )

    # ----------------------------------------------------------
    # Issue 2: generation_api.py 3 个 endpoint 函数体内不应有局部 ValidationException 导入
    # Validates: Requirements 1.2
    # ----------------------------------------------------------
    @pytest.mark.parametrize(
        "func_name",
        [
            "download_contract_document",
            "download_contract_folder",
            "download_supplementary_agreement",
        ],
    )
    def test_generation_api_no_local_validation_exception_import(self, func_name: str) -> None:
        """generation_api.py endpoint 函数体内不应有局部 ValidationException 导入"""
        tree: ast.Module = _parse_file("apps/documents/api/generation_api.py")
        func_node: ast.FunctionDef | None = _get_function_node(tree, func_name)
        assert func_node is not None, f"未找到函数 {func_name}"
        has_violation: bool = _has_local_import_in_func(
            func_node, "apps.core.exceptions", "ValidationException"
        )
        assert not has_violation, (
            f"{func_name} 函数体内仍包含局部 'from apps.core.exceptions import ValidationException' 导入"
        )

    # ----------------------------------------------------------
    # Issue 3: folder_template_api.py 不应包含 build_folder_template_service 导入
    # Validates: Requirements 1.3
    # ----------------------------------------------------------
    def test_folder_template_api_no_build_service_import(self) -> None:
        """folder_template_api.py 不应包含 from apps.core.dependencies.documents import build_folder_template_service"""
        tree: ast.Module = _parse_file("apps/documents/api/folder_template_api.py")
        has_violation: bool = _has_import_from(
            tree, "apps.core.dependencies.documents", "build_folder_template_service"
        )
        assert not has_violation, (
            "folder_template_api.py 仍包含 'from apps.core.dependencies.documents import build_folder_template_service' 导入"
        )

    # ----------------------------------------------------------
    # Issue 4: evidence.py start_order 和 start_page 不应包含 while current: 循环
    # Validates: Requirements 1.4, 1.5
    # ----------------------------------------------------------
    @pytest.mark.parametrize("prop_name", ["start_order", "start_page"])
    def test_evidence_list_no_while_loop_in_property(self, prop_name: str) -> None:
        """EvidenceList.start_order/start_page 不应包含 while current: 循环"""
        tree: ast.Module = _parse_file("apps/documents/models/evidence.py")
        prop_node: ast.FunctionDef | None = _get_property_node(tree, "EvidenceList", prop_name)
        assert prop_node is not None, f"未找到 EvidenceList.{prop_name} 属性"
        has_violation: bool = _func_body_contains_while(prop_node, "current")
        assert not has_violation, (
            f"EvidenceList.{prop_name} 仍包含 'while current:' 循环"
        )

    # ----------------------------------------------------------
    # Issue 5: signals.py _create_audit_log 不应包含 TemplateAuditLog.objects.create()
    # Validates: Requirements 1.6
    # ----------------------------------------------------------
    def test_signals_no_direct_orm_create(self) -> None:
        """signals._create_audit_log 不应包含 TemplateAuditLog.objects.create()"""
        tree: ast.Module = _parse_file("apps/documents/signals.py")
        func_node: ast.FunctionDef | None = _get_function_node(tree, "_create_audit_log")
        assert func_node is not None, "未找到函数 _create_audit_log"
        has_violation: bool = _func_body_contains_call(func_node, "TemplateAuditLog.objects.create")
        assert not has_violation, (
            "_create_audit_log 仍包含 TemplateAuditLog.objects.create() 调用"
        )

    # ----------------------------------------------------------
    # Issue 6: signals.py capture_pre_save_state 不应包含 sender.objects.get()
    # Validates: Requirements 1.7
    # ----------------------------------------------------------
    def test_signals_no_direct_orm_get(self) -> None:
        """signals.capture_pre_save_state 不应包含 sender.objects.get()"""
        tree: ast.Module = _parse_file("apps/documents/signals.py")
        func_node: ast.FunctionDef | None = _get_function_node(tree, "capture_pre_save_state")
        assert func_node is not None, "未找到函数 capture_pre_save_state"
        has_violation: bool = _func_body_contains_call(func_node, "sender.objects.get")
        assert not has_violation, (
            "capture_pre_save_state 仍包含 sender.objects.get() 调用"
        )

    # ----------------------------------------------------------
    # Issue 7: signals.py _invalidate_template_matching_cache 不应包含 cache.get()/cache.set()
    # Validates: Requirements 1.8
    # ----------------------------------------------------------
    def test_signals_no_direct_cache_operations(self) -> None:
        """signals._invalidate_template_matching_cache 不应包含 cache.get()/cache.set()"""
        tree: ast.Module = _parse_file("apps/documents/signals.py")
        func_node: ast.FunctionDef | None = _get_function_node(tree, "_invalidate_template_matching_cache")
        assert func_node is not None, "未找到函数 _invalidate_template_matching_cache"
        has_cache_get: bool = _func_body_contains_call(func_node, "cache.get")
        has_cache_set: bool = _func_body_contains_call(func_node, "cache.set")
        assert not has_cache_get, "_invalidate_template_matching_cache 仍包含 cache.get() 调用"
        assert not has_cache_set, "_invalidate_template_matching_cache 仍包含 cache.set() 调用"

    # ----------------------------------------------------------
    # Issue 8: placeholder_admin.py PlaceholderUsageFilter.queryset() 不应包含 queryset.filter(key__in=...)
    # Validates: Requirements 1.9
    # ----------------------------------------------------------
    def test_placeholder_admin_no_direct_queryset_filter(self) -> None:
        """PlaceholderUsageFilter.queryset() 不应包含 queryset.filter(key__in=...)"""
        tree: ast.Module = _parse_file("apps/documents/admin/placeholder_admin.py")
        method_node: ast.FunctionDef | None = _get_method_node(
            tree, "PlaceholderUsageFilter", "queryset"
        )
        assert method_node is not None, "未找到 PlaceholderUsageFilter.queryset 方法"
        has_violation: bool = _func_source_contains(
            "apps/documents/admin/placeholder_admin.py", method_node, "queryset.filter(key__in="
        )
        has_exclude: bool = _func_source_contains(
            "apps/documents/admin/placeholder_admin.py", method_node, "queryset.exclude(key__in="
        )
        assert not has_violation, (
            "PlaceholderUsageFilter.queryset() 仍包含 queryset.filter(key__in=...) 调用"
        )
        assert not has_exclude, (
            "PlaceholderUsageFilter.queryset() 仍包含 queryset.exclude(key__in=...) 调用"
        )

    # ----------------------------------------------------------
    # Issue 9: document_template_admin.py current_file_display 不应包含 Path(obj.file_path).resolve()
    # Validates: Requirements 1.10
    # ----------------------------------------------------------
    def test_document_template_admin_current_file_no_path_resolve(self) -> None:
        """current_file_display 不应包含 Path(obj.file_path).resolve()"""
        tree: ast.Module = _parse_file("apps/documents/admin/document_template_admin.py")
        method_node: ast.FunctionDef | None = _get_method_node(
            tree, "DocumentTemplateAdmin", "current_file_display"
        )
        assert method_node is not None, "未找到 DocumentTemplateAdmin.current_file_display 方法"
        has_violation: bool = _func_source_contains(
            "apps/documents/admin/document_template_admin.py",
            method_node,
            "Path(obj.file_path).resolve()",
        )
        assert not has_violation, (
            "current_file_display 仍包含 Path(obj.file_path).resolve() 调用"
        )

    # ----------------------------------------------------------
    # Issue 10: document_template_admin.py file_location_display 不应包含 Path(obj.file_path).resolve()
    # Validates: Requirements 1.10
    # ----------------------------------------------------------
    def test_document_template_admin_file_location_no_path_resolve(self) -> None:
        """file_location_display 不应包含 Path(obj.file_path).resolve()"""
        tree: ast.Module = _parse_file("apps/documents/admin/document_template_admin.py")
        method_node: ast.FunctionDef | None = _get_method_node(
            tree, "DocumentTemplateAdmin", "file_location_display"
        )
        assert method_node is not None, "未找到 DocumentTemplateAdmin.file_location_display 方法"
        has_violation: bool = _func_source_contains(
            "apps/documents/admin/document_template_admin.py",
            method_node,
            "Path(obj.file_path).resolve()",
        )
        assert not has_violation, (
            "file_location_display 仍包含 Path(obj.file_path).resolve() 调用"
        )
