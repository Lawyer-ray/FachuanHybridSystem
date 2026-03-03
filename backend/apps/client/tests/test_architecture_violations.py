"""
Bug Condition Exploration Tests - Client 模块架构违规检测

使用 AST 分析扫描 Service 层文件，检测以下违规：
- Service 层模块级直接 `from apps.client.models import ...` 不在 TYPE_CHECKING 块内
- 私有方法调用 `self.service._get_client_internal()`
- `delete_media_file` 返回类型为 None 而非 bool
- `get_clients_by_ids` 存在未使用的 `user` 参数
- `PropertyClueAttachmentOut` 缺少 `resolve_media_url` 方法

这些测试编码的是"期望行为"（修复后的正确状态）。
在未修复代码上运行时，测试会 FAIL，证明 bug 存在。
修复完成后，测试会 PASS，确认 bug 已修复。

**Validates: Requirements 1.1, 1.2, 1.3, 1.4, 1.6, 1.7, 1.10, 1.11, 1.12**
"""

from __future__ import annotations

import ast
import inspect
import logging
from pathlib import Path
from typing import Any

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

logger = logging.getLogger(__name__)

# backend/ 根目录
BACKEND_DIR: Path = Path(__file__).resolve().parent.parent.parent.parent

# Service 层中存在运行时 Model 导入违规的文件列表
SERVICE_FILES_WITH_MODEL_IMPORT_VIOLATION: list[str] = [
    "apps/client/services/client_admin_service.py",
    "apps/client/services/property_clue_service.py",
    "apps/client/services/client_identity_doc_service.py",
    "apps/client/services/client_admin_file_mixin.py",
    "apps/client/services/client_service_adapter.py",
    "apps/client/services/client_query_facade.py",
]


def _parse_file(rel_path: str) -> ast.Module:
    """解析 Python 文件为 AST。"""
    full_path: Path = BACKEND_DIR / rel_path
    source: str = full_path.read_text(encoding="utf-8")
    return ast.parse(source, filename=rel_path)


def _has_runtime_model_import(tree: ast.Module) -> list[dict[str, Any]]:
    """
    检测模块级 `from apps.client.models import ...` 是否在 TYPE_CHECKING 块之外。

    返回违规导入列表，每项包含 line（行号）和 names（导入名称）。
    """
    violations: list[dict[str, Any]] = []

    for node in ast.iter_child_nodes(tree):
        # 跳过 TYPE_CHECKING 块内的导入
        if isinstance(node, ast.If):
            test = node.test
            is_type_checking: bool = False
            if (isinstance(test, ast.Name) and test.id == "TYPE_CHECKING") or (
                isinstance(test, ast.Attribute) and test.attr == "TYPE_CHECKING"
            ):
                is_type_checking = True
            if is_type_checking:
                continue

        # 检测模块级 from apps.client.models import ...
        if isinstance(node, ast.ImportFrom):
            if node.module and node.module.startswith("apps.client.models"):
                names: list[str] = [alias.name for alias in (node.names or [])]
                violations.append(
                    {
                        "line": node.lineno,
                        "names": names,
                    }
                )

    return violations


def _has_private_method_call(tree: ast.Module, method_name: str) -> list[dict[str, Any]]:
    """
    检测 AST 中是否存在对指定私有方法的调用。

    返回违规调用列表，每项包含 line（行号）和 call（调用表达式）。
    """
    violations: list[dict[str, Any]] = []

    for node in ast.walk(tree):
        if isinstance(node, ast.Call):
            func = node.func
            if isinstance(func, ast.Attribute) and func.attr == method_name:
                violations.append(
                    {
                        "line": node.lineno,
                        "call": f"*.{method_name}()",
                    }
                )

    return violations


def _get_function_return_annotation(tree: ast.Module, func_name: str) -> str | None:
    """
    获取模块级函数的返回类型注解字符串。

    返回 None 表示无返回类型注解。
    """
    for node in ast.walk(tree):
        if isinstance(node, ast.FunctionDef) and node.name == func_name:
            if node.returns is None:
                return None
            return ast.dump(node.returns)
    return None


def _has_unused_param_in_method(
    tree: ast.Module,
    class_name: str,
    method_name: str,
    param_name: str,
) -> bool:
    """
    检测类方法中是否存在未使用的参数（参数名不以 _ 开头）。

    返回 True 表示参数存在且未以 _ 开头（即未标记为未使用）。
    """
    for node in ast.walk(tree):
        if isinstance(node, ast.ClassDef) and node.name == class_name:
            for item in node.body:
                if isinstance(item, ast.FunctionDef) and item.name == method_name:
                    for arg in item.args.args + item.args.kwonlyargs:
                        if arg.arg == param_name:
                            return True
    return False


def _class_has_method(tree: ast.Module, class_name: str, method_name: str) -> bool:
    """检测类是否包含指定方法。"""
    for node in ast.walk(tree):
        if isinstance(node, ast.ClassDef) and node.name == class_name:
            for item in node.body:
                if isinstance(item, (ast.FunctionDef, ast.AsyncFunctionDef)):
                    if item.name == method_name:
                        return True
    return False


# ---------------------------------------------------------------------------
# Property 1: Service 层无运行时 Model 导入 (Hypothesis PBT)
# ---------------------------------------------------------------------------
@pytest.mark.property_test
@settings(max_examples=len(SERVICE_FILES_WITH_MODEL_IMPORT_VIOLATION))
@given(
    file_rel_path=st.sampled_from(SERVICE_FILES_WITH_MODEL_IMPORT_VIOLATION),
)
def test_service_no_runtime_model_import(file_rel_path: str) -> None:
    """
    Property 1: Fault Condition - Service 层无运行时 Model 导入

    *For any* Service 层文件，模块级不应包含 `from apps.client.models import ...`
    （除非在 TYPE_CHECKING 块内）。

    在未修复代码上运行时 FAIL，证明 bug 存在。

    **Validates: Requirements 1.1, 1.2, 1.3, 1.4, 1.6, 1.7**
    """
    tree: ast.Module = _parse_file(file_rel_path)
    violations: list[dict[str, Any]] = _has_runtime_model_import(tree)

    assert not violations, f"架构违规: {file_rel_path} 存在运行时 Model 导入 (不在 TYPE_CHECKING 块内):\n" + "\n".join(
        f"  第 {v['line']} 行: from apps.client.models import {', '.join(v['names'])}" for v in violations
    )


# ---------------------------------------------------------------------------
# Property 1 补充: 私有方法调用检测
# ---------------------------------------------------------------------------
@pytest.mark.property_test
def test_no_private_method_call_in_adapter() -> None:
    """
    Property 1: Fault Condition - client_service_adapter.py 不应调用私有方法

    检测 `client_service_adapter.py` 中是否存在
    `self.service._get_client_internal()` 私有方法调用。

    在未修复代码上运行时 FAIL，证明 bug 存在。

    **Validates: Requirements 1.6**
    """
    rel_path: str = "apps/client/services/client_service_adapter.py"
    tree: ast.Module = _parse_file(rel_path)
    violations: list[dict[str, Any]] = _has_private_method_call(tree, "_get_client_internal")

    assert not violations, (
        f"封装违规: {rel_path} 存在私有方法调用:\n"
        + "\n".join(f"  第 {v['line']} 行: {v['call']}" for v in violations)
        + "\n应通过 self.internal_query_service.get_client() 查询"
    )


# ---------------------------------------------------------------------------
# Property 1 补充: delete_media_file 返回类型检测
# ---------------------------------------------------------------------------
@pytest.mark.property_test
def test_delete_media_file_returns_bool() -> None:
    """
    Property 1: Fault Condition - storage.py 的 delete_media_file 应返回 bool

    检测 `delete_media_file` 的返回类型注解是否为 `bool`（而非 `None`）。

    在未修复代码上运行时 FAIL，证明 bug 存在。

    **Validates: Requirements 1.10**
    """
    rel_path: str = "apps/client/services/storage.py"
    tree: ast.Module = _parse_file(rel_path)

    # 查找 delete_media_file 函数
    found: bool = False
    returns_bool: bool = False

    for node in ast.walk(tree):
        if isinstance(node, ast.FunctionDef) and node.name == "delete_media_file":
            found = True
            if node.returns is not None:
                annotation_str: str = ast.unparse(node.returns)
                if annotation_str == "bool":
                    returns_bool = True
            break

    assert found, f"未找到 delete_media_file 函数: {rel_path}"
    assert returns_bool, (
        f"返回类型违规: {rel_path} 的 delete_media_file 返回类型不是 bool。"
        "删除失败时应返回 False 而非 None，让调用方能感知删除结果。"
    )


# ---------------------------------------------------------------------------
# Property 1 补充: 未使用参数检测
# ---------------------------------------------------------------------------
@pytest.mark.property_test
def test_no_unused_user_param_in_batch_query() -> None:
    """
    Property 1: Fault Condition - get_clients_by_ids 不应有未使用的 user 参数

    检测 `client_batch_query_service.py` 的 `get_clients_by_ids` 方法
    是否存在名为 `user` 的参数（应移除或重命名为 `_user`）。

    在未修复代码上运行时 FAIL，证明 bug 存在。

    **Validates: Requirements 1.11**
    """
    rel_path: str = "apps/client/services/query/client_batch_query_service.py"
    tree: ast.Module = _parse_file(rel_path)

    has_unused: bool = _has_unused_param_in_method(
        tree,
        class_name="ClientBatchQueryService",
        method_name="get_clients_by_ids",
        param_name="user",
    )

    assert not has_unused, (
        f"未使用参数违规: {rel_path} 的 "
        "ClientBatchQueryService.get_clients_by_ids 存在未使用的 `user` 参数。"
        "应移除或重命名为 `_user`。"
    )


# ---------------------------------------------------------------------------
# Property 1 补充: PropertyClueAttachmentOut 缺少 resolve_media_url
# ---------------------------------------------------------------------------
@pytest.mark.property_test
def test_property_clue_attachment_out_has_resolve_media_url() -> None:
    """
    Property 1: Fault Condition - PropertyClueAttachmentOut 应有 resolve_media_url

    检测 `schemas.py` 的 `PropertyClueAttachmentOut` 类是否包含
    `resolve_media_url` 方法。

    在未修复代码上运行时 FAIL，证明 bug 存在。

    **Validates: Requirements 1.12**
    """
    rel_path: str = "apps/client/schemas.py"
    tree: ast.Module = _parse_file(rel_path)

    has_method: bool = _class_has_method(
        tree,
        class_name="PropertyClueAttachmentOut",
        method_name="resolve_media_url",
    )

    assert has_method, (
        f"缺少方法违规: {rel_path} 的 PropertyClueAttachmentOut "
        "缺少 resolve_media_url 静态方法。"
        "附件的 media_url 字段不会自动填充，始终为 None。"
    )
