"""
API 文件更新器

协调 ApiRefactoringEngine 和 ServiceMethodExtractor，
对 API 文件执行完整的重构流程：
1. 将 Model.objects 调用替换为 Service 调用
2. 添加工厂函数（延迟导入 + 实例化）
3. 移除不再使用的 Model 导入
4. 写回更新后的文件
"""
from __future__ import annotations

import ast
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

from .api_refactoring_engine import (
    ApiRefactoringEngine,
    ParsedOrmCall,
    ServiceCallSpec,
    _to_snake_case,
)
from .errors import RefactoringError, RefactoringSyntaxError
from .logging_config import get_logger
from .models import ApiViolation, RefactoringResult
from .service_method_extractor import ServiceFileUpdate, ServiceMethodExtractor

logger = get_logger("api_file_updater")


@dataclass
class FileUpdatePlan:
    """单个 API 文件的完整更新计划"""

    file_path: Path
    original_source: str
    rewritten_source: str = ""
    factory_functions: dict[str, str] = field(default_factory=dict)
    """model_name -> 工厂函数源代码"""
    service_var_mappings: dict[str, str] = field(default_factory=dict)
    """model_name -> service 变量名 (如 "contract_service")"""
    models_to_remove_from_imports: set[str] = field(default_factory=set)
    """重构后不再需要的 Model 名称"""
    service_file_updates: list[ServiceFileUpdate] = field(default_factory=list)
    """需要更新的 Service 文件列表"""
    changes: list[str] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)


@dataclass
class _ModelUsageInfo:
    """单个 Model 在文件中的使用情况"""

    model_name: str
    violation_count: int = 0
    non_violation_usage_count: int = 0


class ApiFileUpdater:
    """
    API 文件更新器

    接收一个 API 文件路径和该文件的 ApiViolation 列表，
    协调 ApiRefactoringEngine 和 ServiceMethodExtractor 完成：

    - ORM 调用 → Service 调用的 AST 重写
    - 工厂函数生成（延迟导入模式）
    - 未使用 Model 导入清理
    - 文件写回
    """

    def __init__(self) -> None:
        self._engine = ApiRefactoringEngine()
        self._extractor = ServiceMethodExtractor()

    # ── public API ──────────────────────────────────────────

    def update_file(
        self,
        file_path: Path,
        violations: list[ApiViolation],
        *,
        service_base_dir: Optional[Path] = None,
        app_label: str = "",
        dry_run: bool = False,
    ) -> RefactoringResult:
        """
        对单个 API 文件执行完整重构。

        Args:
            file_path: API 文件路径
            violations: 该文件的 ApiViolation 列表
            service_base_dir: Service 文件所在目录（用于 plan_service_update）
            app_label: Django app 标签（如 "contracts"）
            dry_run: 为 True 时不写入文件

        Returns:
            RefactoringResult
        """
        file_path = Path(file_path)
        if not file_path.exists():
            return RefactoringResult(
                success=False,
                file_path=str(file_path),
                error_message=f"文件不存在: {file_path}",
            )

        if not violations:
            return RefactoringResult(
                success=True,
                file_path=str(file_path),
                changes_made=["无违规，跳过"],
            )

        source = file_path.read_text(encoding="utf-8")
        plan = self._build_plan(file_path, source, violations, service_base_dir, app_label)

        if plan.errors and not plan.changes:
            return RefactoringResult(
                success=False,
                file_path=str(file_path),
                changes_made=plan.changes,
                error_message="; ".join(plan.errors),
            )

        final_source = self._apply_plan(plan)

        # 语法验证
        try:
            ast.parse(final_source)
        except SyntaxError as exc:
            return RefactoringResult(
                success=False,
                file_path=str(file_path),
                changes_made=plan.changes,
                error_message=f"重构后代码语法错误: {exc}",
            )

        if not dry_run:
            file_path.write_text(final_source, encoding="utf-8")
            logger.info("已写入更新后的文件: %s", file_path)

        return RefactoringResult(
            success=True,
            file_path=str(file_path),
            changes_made=plan.changes,
        )

    # ── plan 构建 ───────────────────────────────────────────

    def _build_plan(
        self,
        file_path: Path,
        source: str,
        violations: list[ApiViolation],
        service_base_dir: Optional[Path],
        app_label: str,
    ) -> FileUpdatePlan:
        """构建完整的文件更新计划。"""
        plan = FileUpdatePlan(file_path=file_path, original_source=source)
        current_source = source

        for violation in violations:
            parsed = self._engine.parse_orm_call(violation, current_source)
            if parsed is None:
                plan.errors.append(
                    f"第 {violation.line_number} 行: 无法解析 ORM 调用"
                )
                continue

            spec = self._engine.generate_service_call(parsed)
            if spec.needs_manual_review:
                plan.errors.append(
                    f"第 {violation.line_number} 行: {spec.review_reason}"
                )
                continue

            # AST 重写 ORM 调用
            new_source = self._engine.rewrite_source(
                current_source, violation, parsed, spec,
            )
            if new_source is None:
                plan.errors.append(
                    f"第 {violation.line_number} 行: AST 重写失败"
                )
                continue

            current_source = new_source
            model_name = parsed.model_name

            # 记录工厂函数需求
            if model_name not in plan.factory_functions:
                factory_code = self._generate_factory_function(model_name)
                plan.factory_functions[model_name] = factory_code
                plan.service_var_mappings[model_name] = spec.service_var

            # 记录 Model 可能需要从导入中移除
            plan.models_to_remove_from_imports.add(model_name)

            # 规划 Service 文件更新
            if service_base_dir is not None:
                service_update = self._plan_service_update(
                    parsed, service_base_dir, app_label,
                )
                if service_update is not None:
                    plan.service_file_updates.append(service_update)

            plan.changes.append(
                f"第 {violation.line_number} 行: "
                f"{model_name}.objects.{parsed.orm_method}() "
                f"→ {spec.service_var}.{spec.method_name}()"
            )

        plan.rewritten_source = current_source
        return plan

    # ── plan 应用 ───────────────────────────────────────────

    def _apply_plan(self, plan: FileUpdatePlan) -> str:
        """
        将更新计划应用到源代码，返回最终源代码。

        步骤：
        1. 从 AST 重写后的源代码开始
        2. 移除不再使用的 Model 导入
        3. 插入工厂函数
        4. 在使用处添加 service 实例化（通过工厂函数调用）
        """
        source = plan.rewritten_source

        # 确定哪些 Model 真正可以从导入中移除
        removable = self._find_removable_imports(
            source, plan.models_to_remove_from_imports,
        )
        if removable:
            source = self._remove_model_imports(source, removable)
            for name in removable:
                plan.changes.append(f"移除未使用的 Model 导入: {name}")

        # 检查已有的工厂函数，避免重复
        existing_factories = self._find_existing_factory_functions(source)
        new_factories: dict[str, str] = {}
        for model_name, factory_code in plan.factory_functions.items():
            func_name = self._factory_function_name(model_name)
            if func_name not in existing_factories:
                new_factories[model_name] = factory_code

        # 插入工厂函数（在导入块之后、第一个函数/类定义之前）
        if new_factories:
            source = self._insert_factory_functions(source, new_factories)
            for model_name in new_factories:
                func_name = self._factory_function_name(model_name)
                plan.changes.append(f"添加工厂函数: {func_name}()")

        # 在函数体中添加 service 实例化调用
        source = self._insert_service_instantiation(
            source, plan.service_var_mappings, existing_factories,
        )

        return source

    # ── 工厂函数生成 ────────────────────────────────────────

    @staticmethod
    def _factory_function_name(model_name: str) -> str:
        """生成工厂函数名: Contract → _get_contract_service"""
        snake = _to_snake_case(model_name)
        return f"_get_{snake}_service"

    @staticmethod
    def _service_class_name(model_name: str) -> str:
        """生成 Service 类名: Contract → ContractService"""
        return f"{model_name}Service"

    def _generate_factory_function(self, model_name: str) -> str:
        """
        生成工厂函数代码。

        遵循项目约定的延迟导入模式::

            def _get_contract_service():
                from ..services import ContractService
                return ContractService()
        """
        func_name = self._factory_function_name(model_name)
        service_cls = self._service_class_name(model_name)
        return (
            f"\n\ndef {func_name}():\n"
            f"    from ..services import {service_cls}\n"
            f"    return {service_cls}()\n"
        )

    # ── 导入清理 ────────────────────────────────────────────

    def _find_removable_imports(
        self,
        source: str,
        candidates: set[str],
    ) -> set[str]:
        """
        检查候选 Model 名称在源代码中是否仍被引用（除导入语句外）。

        只有当 Model 名称在非导入行中不再出现时才标记为可移除。
        """
        if not candidates:
            return set()

        try:
            tree = ast.parse(source)
        except SyntaxError:
            return set()

        # 收集导入行号
        import_lines: set[int] = set()
        for node in ast.walk(tree):
            if isinstance(node, (ast.Import, ast.ImportFrom)):
                import_lines.add(node.lineno)
                end = getattr(node, "end_lineno", node.lineno)
                for ln in range(node.lineno, end + 1):
                    import_lines.add(ln)

        # 收集非导入区域中引用的名称
        used_names: set[str] = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.Name) and node.id in candidates:
                if node.lineno not in import_lines:
                    used_names.add(node.id)

        return candidates - used_names

    def _remove_model_imports(self, source: str, names_to_remove: set[str]) -> str:
        """
        从源代码中移除指定 Model 的导入。

        处理 ``from xxx.models import A, B, C`` 格式：
        - 如果移除后还有其他名称，保留 import 语句
        - 如果移除后无名称，删除整行
        """
        try:
            tree = ast.parse(source)
        except SyntaxError:
            return source

        lines = source.splitlines(keepends=True)
        lines_to_remove: set[int] = set()
        replacements: dict[int, str] = {}

        for node in ast.iter_child_nodes(tree):
            if not isinstance(node, ast.ImportFrom):
                continue

            matching_aliases = [
                alias for alias in node.names
                if (alias.asname or alias.name) in names_to_remove
            ]
            if not matching_aliases:
                continue

            remaining = [
                alias for alias in node.names
                if (alias.asname or alias.name) not in names_to_remove
            ]

            start_line = node.lineno
            end_line = getattr(node, "end_lineno", start_line)

            if not remaining:
                # 整个 import 语句都可以删除
                for ln in range(start_line, end_line + 1):
                    lines_to_remove.add(ln)
            else:
                # 重建 import 语句
                names_str = ", ".join(
                    f"{a.name} as {a.asname}" if a.asname else a.name
                    for a in remaining
                )
                new_import = f"from {node.module} import {names_str}\n"
                replacements[start_line] = new_import
                for ln in range(start_line + 1, end_line + 1):
                    lines_to_remove.add(ln)

        if not lines_to_remove and not replacements:
            return source

        result_lines: list[str] = []
        for i, line in enumerate(lines, start=1):
            if i in lines_to_remove:
                continue
            if i in replacements:
                result_lines.append(replacements[i])
            else:
                result_lines.append(line)

        return "".join(result_lines)

    # ── 工厂函数插入 ────────────────────────────────────────

    def _find_existing_factory_functions(self, source: str) -> set[str]:
        """扫描源代码中已存在的 _get_xxx_service 工厂函数名。"""
        try:
            tree = ast.parse(source)
        except SyntaxError:
            return set()

        names: set[str] = set()
        for node in ast.iter_child_nodes(tree):
            if isinstance(node, ast.FunctionDef) and node.name.startswith("_get_"):
                if node.name.endswith("_service"):
                    names.add(node.name)
        return names

    def _insert_factory_functions(
        self,
        source: str,
        factories: dict[str, str],
    ) -> str:
        """
        在导入块之后、第一个函数/类定义之前插入工厂函数。

        如果文件中已有工厂函数，则在最后一个工厂函数之后插入。
        """
        try:
            tree = ast.parse(source)
        except SyntaxError:
            return source

        lines = source.splitlines(keepends=True)
        insert_line = self._find_factory_insert_position(tree, lines)

        factory_block = "".join(factories.values())

        # 在 insert_line 之后插入
        before = lines[:insert_line]
        after = lines[insert_line:]

        return "".join(before) + factory_block + "".join(after)

    def _find_factory_insert_position(
        self,
        tree: ast.Module,
        lines: list[str],
    ) -> int:
        """
        确定工厂函数的插入位置（行索引，0-based）。

        优先级：
        1. 最后一个已有工厂函数之后
        2. 最后一个导入语句之后
        3. 文件开头
        """
        last_factory_end: int = 0
        last_import_end: int = 0

        for node in ast.iter_child_nodes(tree):
            if isinstance(node, (ast.Import, ast.ImportFrom)):
                end = getattr(node, "end_lineno", node.lineno)
                if end > last_import_end:
                    last_import_end = end

            if isinstance(node, ast.FunctionDef) and node.name.startswith("_get_"):
                if node.name.endswith("_service"):
                    end = getattr(node, "end_lineno", node.lineno)
                    if end > last_factory_end:
                        last_factory_end = end

        if last_factory_end > 0:
            return last_factory_end
        if last_import_end > 0:
            return last_import_end
        return 0

    # ── Service 实例化插入 ──────────────────────────────────

    def _insert_service_instantiation(
        self,
        source: str,
        var_mappings: dict[str, str],
        existing_factories: set[str],
    ) -> str:
        """
        在引用 service 变量的函数体中插入工厂函数调用。

        对于每个函数，如果函数体中引用了 ``xxx_service.method()``
        但没有对应的 ``xxx_service = _get_xxx_service()`` 赋值，
        则在函数体开头插入该赋值语句。
        """
        try:
            tree = ast.parse(source)
        except SyntaxError:
            return source

        lines = source.splitlines(keepends=True)
        # 收集所有需要的 service 变量名 → 工厂函数名
        var_to_factory: dict[str, str] = {}
        for model_name, var_name in var_mappings.items():
            factory_name = self._factory_function_name(model_name)
            var_to_factory[var_name] = factory_name

        # 也包含已有的工厂函数
        for factory_name in existing_factories:
            # _get_contract_service → contract_service
            var_name = factory_name.removeprefix("_get_").removesuffix("")
            # 实际上 var_name 应该是 factory_name 去掉 _get_ 前缀
            # _get_contract_service → contract_service
            var_name = factory_name[5:]  # 去掉 "_get_"
            var_to_factory[var_name] = factory_name

        # 收集需要插入的位置
        insertions: list[tuple[int, str, str]] = []
        # (行号, 缩进, 赋值语句)

        for node in ast.iter_child_nodes(tree):
            if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                continue
            # 跳过工厂函数本身
            if node.name.startswith("_get_") and node.name.endswith("_service"):
                continue

            needed_vars = self._find_needed_service_vars(node, var_to_factory)
            if not needed_vars:
                continue

            # 确定函数体的缩进
            body_indent = self._get_body_indent(node, lines)

            # 确定插入位置：函数体第一行之前
            first_body_line = node.body[0].lineno
            for var_name in sorted(needed_vars):
                factory_name = var_to_factory[var_name]
                stmt = f"{body_indent}{var_name} = {factory_name}()\n"
                insertions.append((first_body_line, var_name, stmt))

        if not insertions:
            return source

        # 按行号倒序插入，避免行号偏移
        insertions.sort(key=lambda x: x[0], reverse=True)
        for line_no, _var_name, stmt in insertions:
            idx = line_no - 1  # 转为 0-based
            lines.insert(idx, stmt)

        return "".join(lines)

    def _find_needed_service_vars(
        self,
        func_node: ast.FunctionDef | ast.AsyncFunctionDef,
        var_to_factory: dict[str, str],
    ) -> set[str]:
        """
        在函数体中查找引用了但未赋值的 service 变量。
        """
        # 收集函数体中已有的赋值目标
        assigned: set[str] = set()
        for node in ast.walk(func_node):
            if isinstance(node, ast.Assign):
                for target in node.targets:
                    if isinstance(target, ast.Name):
                        assigned.add(target.id)

        # 收集函数体中引用的 service 变量
        referenced: set[str] = set()
        for node in ast.walk(func_node):
            if isinstance(node, ast.Name) and node.id in var_to_factory:
                referenced.add(node.id)

        return referenced - assigned

    @staticmethod
    def _get_body_indent(
        func_node: ast.FunctionDef | ast.AsyncFunctionDef,
        lines: list[str],
    ) -> str:
        """获取函数体的缩进字符串。"""
        if func_node.body:
            first_body_line = lines[func_node.body[0].lineno - 1]
            return re.match(r"^(\s*)", first_body_line).group(1)  # type: ignore[union-attr]
        return "    "

    # ── Service 文件更新规划 ────────────────────────────────

    def _plan_service_update(
        self,
        parsed: ParsedOrmCall,
        service_base_dir: Path,
        app_label: str,
    ) -> Optional[ServiceFileUpdate]:
        """
        使用 ServiceMethodExtractor 规划 Service 文件更新。

        Args:
            parsed: 解析后的 ORM 调用
            service_base_dir: Service 文件目录
            app_label: Django app 标签

        Returns:
            ServiceFileUpdate 或 None
        """
        snake_name = _to_snake_case(parsed.model_name)
        service_file = service_base_dir / f"{snake_name}_service.py"

        return self._extractor.plan_service_update(
            parsed=parsed,
            service_file=service_file,
            app_label=app_label,
        )
