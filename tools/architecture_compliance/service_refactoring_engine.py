"""
Service层跨模块导入重构引擎

识别跨模块 Model 导入语句，确定对应的 ServiceLocator 方法，
生成 ServiceLocator 调用代码替换直接 Model 访问。

支持的 ORM 模式:
- ``Model.objects.get(...)``
- ``Model.objects.filter(...)``
- ``Model.objects.create(...)``
- ``Model.objects.all()``

对于复杂场景（如 Model 作为类型注解、参数传递等），
标记为需要人工审查而非自动替换。
"""
from __future__ import annotations

import ast
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

from .logging_config import get_logger
from .models import RefactoringResult, ServiceViolation

logger = get_logger("service_refactoring_engine")

# ── Model → ServiceLocator getter 映射 ─────────────────────

_MODEL_GETTER_MAP: dict[str, str] = {
    # core.models
    "SystemConfig": "get_system_config_service",
    "CauseOfAction": "get_cause_court_query_service",
    # cases.models
    "Case": "get_case_service",
    "CaseLog": "get_case_service",
    "CaseNumber": "get_case_service",
    "CaseParty": "get_case_service",
    "CaseAssignment": "get_case_service",
    "SimpleCaseType": "get_case_service",
    # contracts.models
    "PartyRole": "get_contract_service",
    # client.models
    "Client": "get_client_service",
    # organization.models
    "Lawyer": "get_lawyer_service",
}

# ORM 方法 → Service 方法名后缀映射
_ORM_METHOD_MAP: dict[str, str] = {
    "get": "get_{model}_internal",
    "filter": "query_{model}s_internal",
    "create": "create_{model}_internal",
    "all": "query_{model}s_internal",
    "exclude": "query_{model}s_internal",
    "first": "get_first_{model}_internal",
    "last": "get_last_{model}_internal",
    "count": "count_{model}s_internal",
    "exists": "check_{model}_exists_internal",
    "update": "update_{model}s_internal",
    "delete": "delete_{model}s_internal",
    "get_or_create": "get_or_create_{model}_internal",
    "update_or_create": "update_or_create_{model}_internal",
    "bulk_create": "bulk_create_{model}s_internal",
    "bulk_update": "bulk_update_{model}s_internal",
}

# 匹配 from apps.<module>.models import ... 的正则
_CROSS_MODULE_IMPORT_RE: re.Pattern[str] = re.compile(
    r"^apps\.([a-zA-Z_][a-zA-Z0-9_]*)\.models"
)


# ── 数据模型 ────────────────────────────────────────────────


@dataclass
class CrossModuleImport:
    """解析后的跨模块导入信息"""

    line_number: int
    module_path: str          # e.g. "apps.cases.models"
    target_module: str        # e.g. "cases"
    imported_names: list[str] # e.g. ["Case", "CaseLog"]
    import_statement: str     # 原始导入语句文本


@dataclass
class ModelUsage:
    """Model 在代码中的使用信息"""

    model_name: str
    usage_type: str           # "orm_call", "type_annotation", "argument", "other"
    orm_method: Optional[str] = None  # e.g. "get", "filter"
    line_number: int = 0
    code_snippet: str = ""
    is_chained: bool = False


@dataclass
class ReplacementSpec:
    """单个替换操作的规格"""

    model_name: str
    getter_method: str        # e.g. "get_case_service"
    service_method: str       # e.g. "get_case_internal"
    original_code: str
    replacement_code: str
    line_number: int
    needs_manual_review: bool = False
    review_reason: str = ""


@dataclass
class FileRefactoringPlan:
    """单个文件的重构计划"""

    file_path: str
    source_module: str
    cross_module_imports: list[CrossModuleImport] = field(default_factory=list)
    model_usages: list[ModelUsage] = field(default_factory=list)
    replacements: list[ReplacementSpec] = field(default_factory=list)
    models_with_getter: list[str] = field(default_factory=list)
    models_without_getter: list[str] = field(default_factory=list)
    needs_service_locator_import: bool = False


# ── 辅助函数 ────────────────────────────────────────────────


def _to_snake_case(name: str) -> str:
    """
    将 CamelCase 转为 snake_case。

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


def _build_service_method_name(model_name: str, orm_method: str) -> str:
    """
    根据 Model 名称和 ORM 方法生成 Service 方法名。

    Args:
        model_name: CamelCase 格式的 Model 名称
        orm_method: ORM 方法名 (get, filter, create 等)

    Returns:
        Service 方法名
    """
    snake_name = _to_snake_case(model_name)
    template = _ORM_METHOD_MAP.get(orm_method, f"{orm_method}_{snake_name}s_internal")
    return template.replace("{model}", snake_name)


def _extract_module_name(file_path: Path) -> Optional[str]:
    """
    从文件路径提取所属 apps 子模块名。

    Args:
        file_path: 文件路径

    Returns:
        模块名，无法确定时返回 None
    """
    parts = file_path.parts
    for i, part in enumerate(parts):
        if part == "apps" and i + 1 < len(parts):
            return parts[i + 1]
    return None


def _get_source_line(source: str, lineno: int) -> str:
    """获取源代码指定行"""
    lines = source.splitlines()
    if 1 <= lineno <= len(lines):
        return lines[lineno - 1].strip()
    return ""


# ── ServiceRefactoringEngine ────────────────────────────────


class ServiceRefactoringEngine:
    """
    Service层跨模块导入重构引擎

    将 Service 层中的跨模块 Model 导入替换为 ServiceLocator 调用。

    工作流程:
    1. 解析文件，识别跨模块 Model 导入
    2. 分析每个导入 Model 在代码中的使用方式
    3. 对于有 ServiceLocator getter 的 Model，生成替换代码
    4. 对于复杂场景，标记为需要人工审查
    5. 返回 RefactoringResult

    示例::

        Before:
            from apps.cases.models import Case
            case = Case.objects.get(id=case_id)

        After:
            from apps.core.interfaces import ServiceLocator
            case = ServiceLocator.get_case_service().get_case_internal(id=case_id)
    """

    # ── public API ──────────────────────────────────────────

    def analyze_file(self, file_path: Path) -> FileRefactoringPlan:
        """
        分析文件，生成重构计划。

        读取文件源代码，识别跨模块导入和 Model 使用方式，
        为每个可自动重构的使用生成替换规格。

        Args:
            file_path: Python 文件路径

        Returns:
            FileRefactoringPlan 包含完整的重构计划
        """
        file_path = Path(file_path)
        plan = FileRefactoringPlan(
            file_path=str(file_path),
            source_module=_extract_module_name(file_path) or "unknown",
        )

        source = self._read_source(file_path)
        if source is None:
            return plan

        tree = self._parse_ast(source, file_path)
        if tree is None:
            return plan

        # 步骤1: 识别跨模块导入
        plan.cross_module_imports = self._find_cross_module_imports(
            tree, source, file_path,
        )
        if not plan.cross_module_imports:
            logger.info("文件无跨模块导入: %s", file_path)
            return plan

        # 收集所有导入的 Model 名称
        all_imported_models: set[str] = set()
        for imp in plan.cross_module_imports:
            all_imported_models.update(imp.imported_names)

        # 分类: 有 getter vs 无 getter
        for model_name in sorted(all_imported_models):
            if model_name in _MODEL_GETTER_MAP:
                plan.models_with_getter.append(model_name)
            else:
                plan.models_without_getter.append(model_name)

        # 步骤2: 分析 Model 使用方式
        plan.model_usages = self._find_model_usages(
            tree, source, all_imported_models,
        )

        # 步骤3: 生成替换规格
        plan.replacements = self._generate_replacements(plan.model_usages)

        # 判断是否需要添加 ServiceLocator 导入
        plan.needs_service_locator_import = any(
            not r.needs_manual_review for r in plan.replacements
        )

        logger.info(
            "文件分析完成: %s — %d 个跨模块导入, %d 个 Model 使用, "
            "%d 个可自动替换, %d 个需人工审查",
            file_path,
            len(plan.cross_module_imports),
            len(plan.model_usages),
            sum(1 for r in plan.replacements if not r.needs_manual_review),
            sum(1 for r in plan.replacements if r.needs_manual_review),
        )
        return plan

    def refactor_violation(
        self,
        violation: ServiceViolation,
        source: str,
    ) -> RefactoringResult:
        """
        重构单个 Service 层跨模块导入违规。

        Args:
            violation: Service 层违规信息
            source: 包含违规的完整源代码

        Returns:
            RefactoringResult 包含重构结果
        """
        if violation.violation_subtype != "cross_module_import":
            return RefactoringResult(
                success=False,
                file_path=violation.file_path,
                error_message="此引擎仅处理跨模块导入违规",
            )

        file_path = Path(violation.file_path)
        tree = self._parse_ast(source, file_path)
        if tree is None:
            return RefactoringResult(
                success=False,
                file_path=violation.file_path,
                error_message="源代码解析失败",
            )

        # 识别违规行的导入
        imports = self._find_cross_module_imports(tree, source, file_path)
        target_import: Optional[CrossModuleImport] = None
        for imp in imports:
            if imp.line_number == violation.line_number:
                target_import = imp
                break

        if target_import is None:
            return RefactoringResult(
                success=False,
                file_path=violation.file_path,
                error_message=f"未在第 {violation.line_number} 行找到跨模块导入",
            )

        # 检查所有导入的 Model 是否都有 getter
        models_without_getter = [
            name for name in target_import.imported_names
            if name not in _MODEL_GETTER_MAP
        ]
        if models_without_getter:
            return RefactoringResult(
                success=False,
                file_path=violation.file_path,
                error_message=(
                    f"以下 Model 没有对应的 ServiceLocator getter: "
                    f"{', '.join(models_without_getter)}"
                ),
            )

        # 分析 Model 使用方式
        imported_set = set(target_import.imported_names)
        usages = self._find_model_usages(tree, source, imported_set)
        replacements = self._generate_replacements(usages)

        # 汇总变更
        changes: list[str] = []
        manual_reviews: list[str] = []

        for repl in replacements:
            if repl.needs_manual_review:
                manual_reviews.append(
                    f"第 {repl.line_number} 行: {repl.review_reason}"
                )
            else:
                changes.append(
                    f"第 {repl.line_number} 行: {repl.original_code} → "
                    f"{repl.replacement_code}"
                )

        # 添加导入变更
        changes.insert(
            0,
            f"第 {target_import.line_number} 行: 移除 {target_import.import_statement} "
            f"→ 添加 from apps.core.interfaces import ServiceLocator",
        )

        if manual_reviews:
            changes.append(f"需要人工审查: {len(manual_reviews)} 处")
            for review in manual_reviews:
                changes.append(f"  - {review}")

        return RefactoringResult(
            success=True,
            file_path=violation.file_path,
            changes_made=changes,
        )

    # ── 跨模块导入识别 ──────────────────────────────────────

    def _find_cross_module_imports(
        self,
        tree: ast.Module,
        source: str,
        file_path: Path,
    ) -> list[CrossModuleImport]:
        """
        在 AST 中查找所有跨模块 Model 导入。

        匹配 ``from apps.<other_module>.models import ...`` 模式，
        排除同模块导入。

        Args:
            tree: AST 模块节点
            source: 源代码文本
            file_path: 文件路径

        Returns:
            跨模块导入列表
        """
        current_module = _extract_module_name(file_path)
        imports: list[CrossModuleImport] = []

        for node in ast.walk(tree):
            if not isinstance(node, ast.ImportFrom):
                continue
            if node.module is None:
                continue

            match = _CROSS_MODULE_IMPORT_RE.match(node.module)
            if match is None:
                continue

            target_module = match.group(1)

            # 同模块导入不算跨模块
            if current_module is not None and target_module == current_module:
                continue

            imported_names = [alias.name for alias in (node.names or [])]
            import_stmt = _get_source_line(source, node.lineno)

            imports.append(CrossModuleImport(
                line_number=node.lineno,
                module_path=node.module,
                target_module=target_module,
                imported_names=imported_names,
                import_statement=import_stmt,
            ))

        return imports

    # ── Model 使用分析 ──────────────────────────────────────

    def _find_model_usages(
        self,
        tree: ast.Module,
        source: str,
        model_names: set[str],
    ) -> list[ModelUsage]:
        """
        分析 Model 在代码中的所有使用方式。

        分类:
        - orm_call: ``Model.objects.get(...)`` 等 ORM 调用
        - type_annotation: 用作类型注解 (函数参数、返回值、变量注解)
        - argument: 作为函数参数传递
        - other: 其他无法分类的使用

        Args:
            tree: AST 模块节点
            source: 源代码文本
            model_names: 需要检测的 Model 名称集合

        Returns:
            Model 使用信息列表
        """
        usages: list[ModelUsage] = []

        # 收集类型注解中使用的 Model (行号集合)
        annotation_lines: set[tuple[str, int]] = set()
        self._collect_annotation_usages(tree, model_names, annotation_lines)

        for node in ast.walk(tree):
            # 检测 Model.objects.* 调用
            if isinstance(node, ast.Call):
                usage = self._check_orm_call(node, source, model_names)
                if usage is not None:
                    usages.append(usage)
                    continue

            # 检测 Model.objects 属性访问 (无调用)
            if isinstance(node, ast.Attribute):
                usage = self._check_objects_access(node, source, model_names)
                if usage is not None:
                    usages.append(usage)
                    continue

        # 添加类型注解使用
        for model_name, lineno in sorted(annotation_lines):
            usages.append(ModelUsage(
                model_name=model_name,
                usage_type="type_annotation",
                line_number=lineno,
                code_snippet=_get_source_line(source, lineno),
            ))

        return usages

    def _check_orm_call(
        self,
        node: ast.Call,
        source: str,
        model_names: set[str],
    ) -> Optional[ModelUsage]:
        """
        检查 Call 节点是否为 Model.objects.<method>(...) 调用。

        Args:
            node: ast.Call 节点
            source: 源代码
            model_names: Model 名称集合

        Returns:
            ModelUsage 或 None
        """
        func = node.func
        if not isinstance(func, ast.Attribute):
            return None

        orm_method = func.attr

        # 简单调用: Model.objects.<method>(...)
        if isinstance(func.value, ast.Attribute):
            objects_node = func.value
            if (
                objects_node.attr == "objects"
                and isinstance(objects_node.value, ast.Name)
                and objects_node.value.id in model_names
            ):
                return ModelUsage(
                    model_name=objects_node.value.id,
                    usage_type="orm_call",
                    orm_method=orm_method,
                    line_number=node.lineno,
                    code_snippet=_get_source_line(source, node.lineno),
                    is_chained=False,
                )

        # 链式调用: Model.objects.<chain>().<method>(...)
        if isinstance(func.value, ast.Call):
            chain_info = self._trace_chain_to_objects(func.value, model_names)
            if chain_info is not None:
                model_name, _ = chain_info
                return ModelUsage(
                    model_name=model_name,
                    usage_type="orm_call",
                    orm_method=orm_method,
                    line_number=node.lineno,
                    code_snippet=_get_source_line(source, node.lineno),
                    is_chained=True,
                )

        return None

    def _check_objects_access(
        self,
        node: ast.Attribute,
        source: str,
        model_names: set[str],
    ) -> Optional[ModelUsage]:
        """
        检查 Attribute 节点是否为 Model.objects 访问（无方法调用）。

        例如: ``qs = Model.objects`` 或 ``Model.objects`` 作为参数传递。

        Args:
            node: ast.Attribute 节点
            source: 源代码
            model_names: Model 名称集合

        Returns:
            ModelUsage 或 None
        """
        if node.attr != "objects":
            return None
        if not isinstance(node.value, ast.Name):
            return None
        if node.value.id not in model_names:
            return None

        # 排除已经被 _check_orm_call 处理的情况
        # (当 objects 是 Call 的 func.value 的一部分时)
        # 这里只捕获独立的 Model.objects 访问
        return ModelUsage(
            model_name=node.value.id,
            usage_type="orm_call",
            orm_method="all",
            line_number=node.lineno,
            code_snippet=_get_source_line(source, node.lineno),
        )

    def _trace_chain_to_objects(
        self,
        node: ast.Call,
        model_names: set[str],
    ) -> Optional[tuple[str, list[str]]]:
        """
        递归追踪链式调用，判断是否源自 Model.objects。

        Args:
            node: 链中的 Call 节点
            model_names: Model 名称集合

        Returns:
            (model_name, chain_methods) 或 None
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
                and func.value.value.id in model_names
            ):
                return (func.value.value.id, [method_name])

        # 递归情况
        if isinstance(func.value, ast.Call):
            result = self._trace_chain_to_objects(func.value, model_names)
            if result is not None:
                model_name, chain = result
                chain.append(method_name)
                return (model_name, chain)

        return None

    def _collect_annotation_usages(
        self,
        tree: ast.Module,
        model_names: set[str],
        result: set[tuple[str, int]],
    ) -> None:
        """
        收集类型注解中使用的 Model 名称。

        检查函数参数注解、返回值注解和变量注解。

        Args:
            tree: AST 模块节点
            model_names: Model 名称集合
            result: 输出集合 (model_name, line_number)
        """
        for node in ast.walk(tree):
            # 函数参数和返回值注解
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                for arg in node.args.args + node.args.kwonlyargs:
                    if arg.annotation is not None:
                        self._check_annotation_node(
                            arg.annotation, model_names, result,
                        )
                if node.returns is not None:
                    self._check_annotation_node(
                        node.returns, model_names, result,
                    )

            # 变量注解
            if isinstance(node, ast.AnnAssign) and node.annotation is not None:
                self._check_annotation_node(
                    node.annotation, model_names, result,
                )

    def _check_annotation_node(
        self,
        node: ast.expr,
        model_names: set[str],
        result: set[tuple[str, int]],
    ) -> None:
        """
        递归检查注解 AST 节点中是否包含 Model 名称。

        处理简单名称、下标 (如 Optional[Model])、属性访问等。

        Args:
            node: 注解 AST 节点
            model_names: Model 名称集合
            result: 输出集合
        """
        if isinstance(node, ast.Name) and node.id in model_names:
            result.add((node.id, node.lineno))
        elif isinstance(node, ast.Subscript):
            # 处理 Optional[Model], list[Model] 等
            self._check_annotation_node(node.value, model_names, result)
            self._check_annotation_node(node.slice, model_names, result)
        elif isinstance(node, ast.Tuple):
            for elt in node.elts:
                self._check_annotation_node(elt, model_names, result)
        elif isinstance(node, ast.BinOp):
            # 处理 Model | None (Python 3.10+ union)
            self._check_annotation_node(node.left, model_names, result)
            self._check_annotation_node(node.right, model_names, result)
        elif isinstance(node, ast.Attribute):
            # 处理 module.Model 形式
            pass  # 跨模块导入通常不会用这种形式

    # ── 替换代码生成 ────────────────────────────────────────

    def _generate_replacements(
        self,
        usages: list[ModelUsage],
    ) -> list[ReplacementSpec]:
        """
        为每个 Model 使用生成替换规格。

        - ORM 调用: 生成 ServiceLocator 调用
        - 类型注解: 标记为需要人工审查（可能需要 Protocol 类型）
        - 其他: 标记为需要人工审查

        Args:
            usages: Model 使用信息列表

        Returns:
            替换规格列表
        """
        replacements: list[ReplacementSpec] = []

        for usage in usages:
            repl = self._generate_single_replacement(usage)
            if repl is not None:
                replacements.append(repl)

        return replacements

    def _generate_single_replacement(
        self,
        usage: ModelUsage,
    ) -> Optional[ReplacementSpec]:
        """
        为单个 Model 使用生成替换规格。

        Args:
            usage: Model 使用信息

        Returns:
            ReplacementSpec 或 None
        """
        getter = _MODEL_GETTER_MAP.get(usage.model_name)

        if usage.usage_type == "type_annotation":
            return ReplacementSpec(
                model_name=usage.model_name,
                getter_method=getter or "",
                service_method="",
                original_code=usage.code_snippet,
                replacement_code="",
                line_number=usage.line_number,
                needs_manual_review=True,
                review_reason=(
                    f"{usage.model_name} 用作类型注解，"
                    f"建议替换为 Protocol 类型或保留"
                ),
            )

        if usage.usage_type == "orm_call":
            return self._generate_orm_replacement(usage, getter)

        # 其他使用方式
        return ReplacementSpec(
            model_name=usage.model_name,
            getter_method=getter or "",
            service_method="",
            original_code=usage.code_snippet,
            replacement_code="",
            line_number=usage.line_number,
            needs_manual_review=True,
            review_reason=(
                f"{usage.model_name} 的使用方式无法自动重构，需要人工审查"
            ),
        )

    def _generate_orm_replacement(
        self,
        usage: ModelUsage,
        getter: Optional[str],
    ) -> ReplacementSpec:
        """
        为 ORM 调用生成 ServiceLocator 替换代码。

        Args:
            usage: ORM 调用使用信息
            getter: ServiceLocator getter 方法名

        Returns:
            ReplacementSpec
        """
        if getter is None:
            return ReplacementSpec(
                model_name=usage.model_name,
                getter_method="",
                service_method="",
                original_code=usage.code_snippet,
                replacement_code="",
                line_number=usage.line_number,
                needs_manual_review=True,
                review_reason=(
                    f"{usage.model_name} 没有对应的 ServiceLocator getter，"
                    f"需要先在 ServiceLocator 中注册"
                ),
            )

        if usage.is_chained:
            return ReplacementSpec(
                model_name=usage.model_name,
                getter_method=getter,
                service_method="",
                original_code=usage.code_snippet,
                replacement_code="",
                line_number=usage.line_number,
                needs_manual_review=True,
                review_reason=(
                    f"{usage.model_name} 的链式 ORM 调用需要人工审查，"
                    f"查询优化应在 Service 层内部处理"
                ),
            )

        orm_method = usage.orm_method or "all"
        service_method = _build_service_method_name(usage.model_name, orm_method)

        original = f"{usage.model_name}.objects.{orm_method}(...)"
        replacement = f"ServiceLocator.{getter}().{service_method}(...)"

        return ReplacementSpec(
            model_name=usage.model_name,
            getter_method=getter,
            service_method=service_method,
            original_code=original,
            replacement_code=replacement,
            line_number=usage.line_number,
        )

    # ── 文件读取和解析 ──────────────────────────────────────

    def _read_source(self, file_path: Path) -> Optional[str]:
        """
        读取源文件内容。

        Args:
            file_path: 文件路径

        Returns:
            源代码文本，读取失败时返回 None
        """
        try:
            return file_path.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError) as exc:
            logger.warning("无法读取文件 %s: %s", file_path, exc)
            return None

    def _parse_ast(
        self,
        source: str,
        file_path: Path,
    ) -> Optional[ast.Module]:
        """
        将源代码解析为 AST。

        Args:
            source: 源代码文本
            file_path: 文件路径

        Returns:
            AST 模块节点，解析失败时返回 None
        """
        try:
            return ast.parse(source, filename=str(file_path))
        except SyntaxError as exc:
            logger.warning("语法错误 %s (行 %s): %s", file_path, exc.lineno, exc.msg)
            return None
