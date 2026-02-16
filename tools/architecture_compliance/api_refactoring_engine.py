"""
API层重构引擎

解析 Model.objects 调用，提取 Model 名称和 ORM 方法，
生成对应的 Service 方法调用代码，使用 AST 重写替换代码。
"""
from __future__ import annotations

import ast
import copy
from dataclasses import dataclass, field
from typing import Optional

from .logging_config import get_logger
from .models import ApiViolation, RefactoringResult

logger = get_logger("api_refactoring_engine")


@dataclass
class ParsedOrmCall:
    """解析后的 ORM 调用信息"""

    model_name: str
    orm_method: str
    is_chained: bool = False
    chain_methods: list[str] = field(default_factory=list)
    line_number: int = 0
    col_offset: int = 0
    end_line_number: int = 0
    end_col_offset: int = 0


@dataclass
class ServiceCallSpec:
    """生成的 Service 方法调用规格"""

    service_var: str  # e.g. "document_recognition_task_service"
    method_name: str  # e.g. "create_document_recognition_task"
    needs_manual_review: bool = False
    review_reason: str = ""


def _to_snake_case(name: str) -> str:
    """
    将 CamelCase 转为 snake_case。

    与 api_scanner._suggest_service_method 使用相同的转换逻辑。

    Args:
        name: CamelCase 名称

    Returns:
        snake_case 名称
    """
    chars: list[str] = []
    for i, ch in enumerate(name):
        if ch.isupper() and i > 0:
            chars.append("_")
        chars.append(ch.lower())
    return "".join(chars)


def _build_service_method_name(snake_name: str, orm_method: str) -> str:
    """
    根据 snake_case Model 名称和 ORM 方法生成 Service 方法名。

    与 api_scanner._suggest_service_method 保持一致的映射。

    Args:
        snake_name: snake_case 格式的 Model 名称
        orm_method: ORM 方法名

    Returns:
        Service 方法名
    """
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
    return method_map.get(orm_method, f"{orm_method}_{snake_name}s")


class ApiRefactoringEngine:
    """
    API层重构引擎

    将 API 层中的 Model.objects 调用重构为 Service 方法调用。

    支持的模式：
    - ``Model.objects.filter(...)`` → ``service.filter_models(...)``
    - ``Model.objects.get(...)`` → ``service.get_model(...)``
    - ``Model.objects.create(...)`` → ``service.create_model(...)``
    - 链式调用如 ``Model.objects.select_related().get(...)`` → 标记为需要人工审查
    """

    # ── public API ──────────────────────────────────────────

    def refactor_violation(
        self,
        violation: ApiViolation,
        source: str,
    ) -> RefactoringResult:
        """
        重构单个 API 层违规。

        Args:
            violation: API 层违规信息
            source: 包含违规的完整源代码

        Returns:
            RefactoringResult 包含重构结果和变更后的代码
        """
        parsed = self.parse_orm_call(violation, source)
        if parsed is None:
            return RefactoringResult(
                success=False,
                file_path=violation.file_path,
                error_message=f"无法解析第 {violation.line_number} 行的 ORM 调用",
            )

        spec = self.generate_service_call(parsed)
        if spec.needs_manual_review:
            return RefactoringResult(
                success=False,
                file_path=violation.file_path,
                changes_made=[],
                error_message=f"需要人工审查: {spec.review_reason}",
            )

        new_source = self.rewrite_source(source, violation, parsed, spec)
        if new_source is None:
            return RefactoringResult(
                success=False,
                file_path=violation.file_path,
                error_message=f"AST 重写失败: 第 {violation.line_number} 行",
            )

        change_desc = (
            f"第 {violation.line_number} 行: "
            f"{violation.model_name}.objects.{parsed.orm_method}() "
            f"→ {spec.service_var}.{spec.method_name}()"
        )
        return RefactoringResult(
            success=True,
            file_path=violation.file_path,
            changes_made=[change_desc, f"new_source_length={len(new_source)}"],
        )

    # ── ORM 调用解析 ────────────────────────────────────────

    def parse_orm_call(
        self,
        violation: ApiViolation,
        source: str,
    ) -> Optional[ParsedOrmCall]:
        """
        解析 Model.objects 调用，提取 Model 名称和 ORM 方法。

        通过 AST 遍历定位违规行上的 ``Model.objects`` 模式，
        区分简单调用和链式调用。

        Args:
            violation: API 层违规信息
            source: 完整源代码

        Returns:
            ParsedOrmCall 或 None（解析失败时）
        """
        try:
            tree = ast.parse(source)
        except SyntaxError as exc:
            logger.warning("源代码解析失败: %s", exc)
            return None

        target_line = violation.line_number

        for node in ast.walk(tree):
            if not isinstance(node, ast.Call):
                continue
            if not hasattr(node, "lineno"):
                continue
            if node.lineno != target_line:
                continue

            result = self._extract_orm_call_from_node(node, violation.model_name)
            if result is not None:
                return result

        # 回退：检测独立的 Model.objects 访问（非 Call 节点）
        for node in ast.walk(tree):
            if not isinstance(node, ast.Attribute):
                continue
            if not hasattr(node, "lineno") or node.lineno != target_line:
                continue
            if node.attr != "objects":
                continue
            if isinstance(node.value, ast.Name) and node.value.id == violation.model_name:
                orm_method = violation.orm_method.replace("objects.", "")
                if not orm_method or orm_method == "objects":
                    orm_method = "all"
                return ParsedOrmCall(
                    model_name=violation.model_name,
                    orm_method=orm_method,
                    is_chained=False,
                    line_number=node.lineno,
                    col_offset=node.col_offset,
                    end_line_number=getattr(node, "end_lineno", node.lineno),
                    end_col_offset=getattr(node, "end_col_offset", node.col_offset),
                )

        logger.warning(
            "未能在第 %d 行找到 %s.objects 调用",
            target_line,
            violation.model_name,
        )
        return None

    def _extract_orm_call_from_node(
        self,
        node: ast.Call,
        model_name: str,
    ) -> Optional[ParsedOrmCall]:
        """
        从 Call 节点提取 ORM 调用信息。

        处理两种 AST 结构：

        简单调用 ``Model.objects.filter(...)``::

            Call(func=Attribute(value=Attribute(value=Name('Model'), attr='objects'), attr='filter'))

        链式调用 ``Model.objects.select_related('x').get(...)``::

            Call(func=Attribute(
                value=Call(func=Attribute(
                    value=Attribute(value=Name('Model'), attr='objects'),
                    attr='select_related')),
                attr='get'))

        Args:
            node: ast.Call 节点
            model_name: 期望的 Model 名称

        Returns:
            ParsedOrmCall 或 None
        """
        func = node.func
        if not isinstance(func, ast.Attribute):
            return None

        final_method = func.attr

        # 情况1: 简单调用 Model.objects.<method>(...)
        if isinstance(func.value, ast.Attribute):
            objects_node = func.value
            if (
                objects_node.attr == "objects"
                and isinstance(objects_node.value, ast.Name)
                and objects_node.value.id == model_name
            ):
                return ParsedOrmCall(
                    model_name=model_name,
                    orm_method=final_method,
                    is_chained=False,
                    line_number=node.lineno,
                    col_offset=node.col_offset,
                    end_line_number=getattr(node, "end_lineno", node.lineno),
                    end_col_offset=getattr(node, "end_col_offset", node.col_offset),
                )

        # 情况2: 链式调用 Model.objects.<chain_method>().<final_method>(...)
        if isinstance(func.value, ast.Call):
            chain_methods = self._collect_chain_methods(func.value, model_name)
            if chain_methods is not None:
                return ParsedOrmCall(
                    model_name=model_name,
                    orm_method=final_method,
                    is_chained=True,
                    chain_methods=chain_methods,
                    line_number=node.lineno,
                    col_offset=node.col_offset,
                    end_line_number=getattr(node, "end_lineno", node.lineno),
                    end_col_offset=getattr(node, "end_col_offset", node.col_offset),
                )

        return None

    def _collect_chain_methods(
        self,
        node: ast.Call,
        model_name: str,
    ) -> Optional[list[str]]:
        """
        递归收集链式调用中的中间方法名。

        例如 ``Model.objects.select_related('x').prefetch_related('y').get(...)``
        返回 ``['select_related', 'prefetch_related']``。

        Args:
            node: 链中的 Call 节点
            model_name: 期望的 Model 名称

        Returns:
            中间方法名列表，或 None（不是 objects 链）
        """
        func = node.func
        if not isinstance(func, ast.Attribute):
            return None

        method_name = func.attr

        # 基础情况: func.value 是 Model.objects
        if isinstance(func.value, ast.Attribute):
            if (
                func.value.attr == "objects"
                and isinstance(func.value.value, ast.Name)
                and func.value.value.id == model_name
            ):
                return [method_name]

        # 递归情况: func.value 是另一个 Call
        if isinstance(func.value, ast.Call):
            inner = self._collect_chain_methods(func.value, model_name)
            if inner is not None:
                inner.append(method_name)
                return inner

        return None

    # ── Service 调用生成 ────────────────────────────────────

    def generate_service_call(self, parsed: ParsedOrmCall) -> ServiceCallSpec:
        """
        根据解析的 ORM 调用生成对应的 Service 方法调用规格。

        链式调用（如 select_related().get()）标记为需要人工审查，
        因为查询优化逻辑应在 Service 层内部处理。

        Args:
            parsed: 解析后的 ORM 调用信息

        Returns:
            ServiceCallSpec 包含 service 变量名和方法名
        """
        snake_name = _to_snake_case(parsed.model_name)
        service_var = f"{snake_name}_service"

        if parsed.is_chained:
            chain_desc = ".".join(parsed.chain_methods)
            return ServiceCallSpec(
                service_var=service_var,
                method_name="",
                needs_manual_review=True,
                review_reason=(
                    f"链式调用 {parsed.model_name}.objects."
                    f"{chain_desc}.{parsed.orm_method}() "
                    f"需要人工审查，查询优化应在 Service 层内部处理"
                ),
            )

        method_name = _build_service_method_name(snake_name, parsed.orm_method)
        return ServiceCallSpec(
            service_var=service_var,
            method_name=method_name,
        )

    # ── AST 重写 ────────────────────────────────────────────

    def rewrite_source(
        self,
        source: str,
        violation: ApiViolation,
        parsed: ParsedOrmCall,
        spec: ServiceCallSpec,
    ) -> Optional[str]:
        """
        使用 AST 重写替换源代码中的 ORM 调用。

        将 ``Model.objects.<method>(args)`` 替换为
        ``service_var.method_name(args)``，保留原始参数。

        Args:
            source: 原始源代码
            violation: API 层违规信息
            parsed: 解析后的 ORM 调用
            spec: Service 调用规格

        Returns:
            重写后的源代码，失败时返回 None
        """
        if spec.needs_manual_review:
            return None

        try:
            tree = ast.parse(source)
        except SyntaxError as exc:
            logger.warning("AST 重写时源代码解析失败: %s", exc)
            return None

        transformer = _OrmCallTransformer(
            model_name=parsed.model_name,
            target_line=violation.line_number,
            service_var=spec.service_var,
            method_name=spec.method_name,
        )
        new_tree = transformer.visit(tree)

        if not transformer.transformed:
            logger.warning(
                "AST 转换器未找到匹配节点: 第 %d 行 %s.objects.%s",
                violation.line_number,
                parsed.model_name,
                parsed.orm_method,
            )
            return None

        ast.fix_missing_locations(new_tree)

        try:
            new_source = ast.unparse(new_tree)
        except Exception as exc:
            logger.warning("AST unparse 失败: %s", exc)
            return None

        logger.info(
            "AST 重写成功: 第 %d 行 %s.objects.%s → %s.%s",
            violation.line_number,
            parsed.model_name,
            parsed.orm_method,
            spec.service_var,
            spec.method_name,
        )
        return new_source


class _OrmCallTransformer(ast.NodeTransformer):
    """
    AST 节点转换器：将 Model.objects.<method>(...) 替换为 service.method(...)。

    仅替换指定行号上匹配 model_name 的第一个 ORM 调用。
    保留原始调用的参数（args 和 kwargs）。
    """

    def __init__(
        self,
        model_name: str,
        target_line: int,
        service_var: str,
        method_name: str,
    ) -> None:
        super().__init__()
        self.model_name = model_name
        self.target_line = target_line
        self.service_var = service_var
        self.method_name = method_name
        self.transformed: bool = False

    def visit_Call(self, node: ast.Call) -> ast.AST:
        """
        访问 Call 节点，匹配 Model.objects.<method>(...) 并替换。

        替换逻辑：
        - 原始: ``Call(func=Attr(value=Attr(value=Name('Model'), 'objects'), '<method>'), args, kwargs)``
        - 替换: ``Call(func=Attr(value=Name('service_var'), 'method_name'), args, kwargs)``
        """
        # 先递归处理子节点
        self.generic_visit(node)

        if self.transformed:
            return node

        if node.lineno != self.target_line:
            return node

        func = node.func
        if not isinstance(func, ast.Attribute):
            return node

        # 检查是否为 Model.objects.<method> 模式
        objects_node = func.value
        if not isinstance(objects_node, ast.Attribute):
            return node
        if objects_node.attr != "objects":
            return node
        if not isinstance(objects_node.value, ast.Name):
            return node
        if objects_node.value.id != self.model_name:
            return node

        # 构建替换节点: service_var.method_name(原始参数)
        new_func = ast.Attribute(
            value=ast.Name(id=self.service_var, ctx=ast.Load()),
            attr=self.method_name,
            ctx=ast.Load(),
        )

        new_call = ast.Call(
            func=new_func,
            args=node.args,
            keywords=node.keywords,
        )

        # 复制位置信息
        ast.copy_location(new_call, node)
        ast.copy_location(new_func, node)

        self.transformed = True
        logger.info(
            "已替换 AST 节点: %s.objects.%s → %s.%s (行 %d)",
            self.model_name,
            func.attr,
            self.service_var,
            self.method_name,
            self.target_line,
        )
        return new_call
