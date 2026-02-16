"""
API层架构违规扫描器

检测API层代码中直接使用ORM的违规模式：
- Model.objects.* 调用
- 直接ORM方法调用（.filter, .get, .create 等）

仅扫描 api/ 目录下的文件。
"""
from __future__ import annotations

import ast
from pathlib import Path
from typing import Optional

from .logging_config import get_logger
from .models import ApiViolation, Violation
from .scanner import ViolationScanner

logger = get_logger("api_scanner")

# 需要检测的ORM方法集合
_ORM_METHODS: frozenset[str] = frozenset({
    "filter",
    "get",
    "create",
    "all",
    "exclude",
    "update",
    "delete",
    "annotate",
    "aggregate",
    "values",
    "values_list",
    "first",
    "last",
    "count",
    "exists",
    "bulk_create",
    "bulk_update",
    "get_or_create",
    "update_or_create",
})


def _suggest_service_method(model_name: str, orm_method: str) -> str:
    """
    根据Model名称和ORM方法生成建议的Service方法名。

    Args:
        model_name: Model类名称（如 "Contract"）
        orm_method: ORM方法名（如 "filter"）

    Returns:
        建议的Service方法名（如 "contract_service.filter_contracts"）
    """
    # 将CamelCase转为snake_case
    snake_name_chars: list[str] = []
    for i, ch in enumerate(model_name):
        if ch.isupper() and i > 0:
            snake_name_chars.append("_")
        snake_name_chars.append(ch.lower())
    snake_name = "".join(snake_name_chars)

    method_map: dict[str, str] = {
        "filter": f"filter_{snake_name}s",
        "get": f"get_{snake_name}",
        "create": f"create_{snake_name}",
        "all": f"list_{snake_name}s",
        "exclude": f"filter_{snake_name}s",
        "update": f"update_{snake_name}s",
        "delete": f"delete_{snake_name}s",
        "first": f"get_first_{snake_name}",
        "last": f"get_last_{snake_name}",
        "count": f"count_{snake_name}s",
        "exists": f"check_{snake_name}_exists",
        "bulk_create": f"bulk_create_{snake_name}s",
        "bulk_update": f"bulk_update_{snake_name}s",
        "get_or_create": f"get_or_create_{snake_name}",
        "update_or_create": f"update_or_create_{snake_name}",
        "annotate": f"query_{snake_name}s",
        "aggregate": f"aggregate_{snake_name}s",
        "values": f"get_{snake_name}_values",
        "values_list": f"get_{snake_name}_values_list",
    }

    service_method = method_map.get(orm_method, f"{orm_method}_{snake_name}s")
    return f"{snake_name}_service.{service_method}"


class ApiLayerScanner(ViolationScanner):
    """
    API层架构违规扫描器

    扫描 api/ 目录下的Python文件，检测直接使用ORM的违规模式。
    仅处理路径中包含 ``api/`` 的文件。
    """

    # ── public API override ─────────────────────────────────

    def scan_directory(self, root: Path) -> list[Violation]:
        """
        扫描目录，仅处理 api/ 子目录下的文件。

        Args:
            root: 要扫描的根目录

        Returns:
            API层违规列表
        """
        root = Path(root)
        if not root.is_dir():
            logger.warning("Path is not a directory, skipping: %s", root)
            return []

        violations: list[Violation] = []
        py_files = self._collect_python_files(root)
        api_files = [f for f in py_files if self._is_api_file(f)]
        logger.info(
            "Found %d API layer Python files (out of %d total) under %s",
            len(api_files),
            len(py_files),
            root,
        )

        for py_file in api_files:
            file_violations = self.scan_file(py_file)
            violations.extend(file_violations)

        logger.info(
            "API layer scan complete: %d violation(s) in %d file(s)",
            len(violations),
            len(api_files),
        )
        return violations

    # ── abstract method implementation ──────────────────────

    def _scan_file_ast(
        self,
        tree: ast.Module,
        source: str,
        file_path: Path,
    ) -> list[Violation]:
        """
        对单个文件的AST执行API层违规检测。

        检测模式：
        1. ``Model.objects.<method>(...)`` — 通过 objects manager 调用ORM方法
        2. ``Model.objects`` 直接访问（赋值给变量等）

        使用两遍扫描避免重复：先收集所有 Call 节点中的 objects 访问，
        再检测独立的 ``Model.objects`` 访问。

        Args:
            tree: 已解析的AST模块节点
            source: 原始源代码文本
            file_path: 文件路径

        Returns:
            检测到的ApiViolation列表
        """
        violations: list[Violation] = []
        # 记录已被 Call 节点处理过的 objects Attribute 节点 id，避免重复
        handled_objects_ids: set[int] = set()

        # 第一遍：检测 Model.objects.<method>(...) 调用
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call):
                continue
            violation, objects_node_id = self._check_call_node(
                node, source, file_path,
            )
            if violation is not None:
                violations.append(violation)
            if objects_node_id is not None:
                handled_objects_ids.add(objects_node_id)

        # 第二遍：检测独立的 Model.objects 访问
        for node in ast.walk(tree):
            if not isinstance(node, ast.Attribute):
                continue
            if id(node) in handled_objects_ids:
                continue
            violation = self._check_objects_access(node, source, file_path)
            if violation is not None:
                violations.append(violation)

        if violations:
            logger.info(
                "Found %d API violation(s) in %s",
                len(violations),
                file_path,
            )
        return violations

    def _check_call_node(
        self,
        node: ast.Call,
        source: str,
        file_path: Path,
    ) -> tuple[Optional[ApiViolation], Optional[int]]:
        """
        检查 Call 节点是否为 ``Model.objects.<method>(...)`` 调用。

        AST结构示例 (Model.objects.filter(...)):
            Call(
                func=Attribute(
                    value=Attribute(
                        value=Name(id='Model'),
                        attr='objects'
                    ),
                    attr='filter'
                )
            )

        Args:
            node: ast.Call 节点
            source: 源代码文本
            file_path: 文件路径

        Returns:
            (ApiViolation 或 None, objects Attribute 节点的 id 或 None)
        """
        func = node.func
        if not isinstance(func, ast.Attribute):
            return None, None

        orm_method = func.attr
        if orm_method not in _ORM_METHODS:
            return None, None

        # func.value 应该是 Model.objects
        objects_node = func.value
        if not isinstance(objects_node, ast.Attribute):
            return None, None
        if objects_node.attr != "objects":
            return None, None

        # objects_node.value 应该是 Model 名称（Name节点）
        model_node = objects_node.value
        if not isinstance(model_node, ast.Name):
            return None, None

        model_name: str = model_node.id
        line_number: int = node.lineno
        code_snippet = self._get_source_line(source, line_number)

        violation = ApiViolation(
            file_path=str(file_path),
            line_number=line_number,
            code_snippet=code_snippet,
            violation_type="api_direct_orm_access",
            severity="high",
            description=(
                f"API层直接使用ORM: {model_name}.objects.{orm_method}()"
            ),
            model_name=model_name,
            orm_method=f"objects.{orm_method}",
            suggested_service_method=_suggest_service_method(model_name, orm_method),
        )
        return violation, id(objects_node)

    def _check_objects_access(
        self,
        node: ast.Attribute,
        source: str,
        file_path: Path,
    ) -> Optional[ApiViolation]:
        """
        检查 ``Model.objects`` 属性访问（不带具体ORM方法调用的情况）。

        例如: ``qs = Contract.objects`` 赋值给变量后续使用。

        仅当 ``node.attr == 'objects'`` 且 ``node.value`` 是 Name 节点时匹配。
        同时排除已经作为 ``Model.objects.<method>`` 链路一部分的情况——
        通过检查该节点是否还有 Attribute 子节点来判断。

        Args:
            node: ast.Attribute 节点
            source: 源代码文本
            file_path: 文件路径

        Returns:
            ApiViolation 或 None
        """
        if node.attr != "objects":
            return None

        if not isinstance(node.value, ast.Name):
            return None

        model_name: str = node.value.id
        line_number: int = node.lineno
        code_snippet = self._get_source_line(source, line_number)

        return ApiViolation(
            file_path=str(file_path),
            line_number=line_number,
            code_snippet=code_snippet,
            violation_type="api_direct_orm_access",
            severity="high",
            description=(
                f"API层直接访问ORM manager: {model_name}.objects"
            ),
            model_name=model_name,
            orm_method="objects",
            suggested_service_method=f"使用对应的Service方法替代直接访问 {model_name}.objects",
        )

    # ── path filtering ──────────────────────────────────────

    @staticmethod
    def _is_api_file(file_path: Path) -> bool:
        """
        判断文件是否位于 api/ 目录下。

        如果文件同时位于 services/ 目录下（如 services/.../api/），
        则视为Service层文件而非API层文件，避免误报。

        Args:
            file_path: 文件路径

        Returns:
            True 表示该文件在 api/ 目录中（且不在 services/ 目录中）
        """
        parts = file_path.parts
        has_api = "api" in parts
        has_services = "services" in parts
        # services/ 下的 api/ 子目录属于Service层，不算API层
        if has_api and has_services:
            return False
        return has_api
