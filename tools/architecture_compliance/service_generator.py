"""
Service 方法生成器

从 BusinessLogicExtractor 的 SaveMethodRefactoring 结果中，
生成或更新 Service 类文件：

1. 根据 Model 所在 app 确定目标 Service 文件路径
2. 如果 Service 文件已存在，解析 AST 并在类中追加新方法（跳过重复）
3. 如果 Service 文件不存在，生成包含完整类定义的新文件
4. 处理 Model 导入和依赖注入
5. 返回 ServiceGenerationResult 结构化结果
"""
from __future__ import annotations

import ast
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

from .business_logic_extractor import (
    ExtractedServiceMethod,
    SaveMethodRefactoring,
    format_service_method_template,
)
from .logging_config import get_logger

logger = get_logger("service_generator")


# ── CamelCase → snake_case ──────────────────────────────────

_CAMEL_RE: re.Pattern[str] = re.compile(
    r"(?<=[a-z0-9])(?=[A-Z])|(?<=[A-Z])(?=[A-Z][a-z])"
)


def _to_snake_case(name: str) -> str:
    """CamelCase → snake_case"""
    return _CAMEL_RE.sub("_", name).lower()


# ── 数据模型 ────────────────────────────────────────────────


@dataclass
class ServiceGenerationResult:
    """Service方法生成结果"""

    service_file_path: str
    service_class_name: str
    methods_added: list[str] = field(default_factory=list)
    methods_skipped: list[str] = field(default_factory=list)
    file_created: bool = False
    file_content: str = ""


# ── ServiceGenerator ────────────────────────────────────────


class ServiceGenerator:
    """
    Service 方法生成器

    接收 SaveMethodRefactoring 结果，生成或更新 Service 类文件。

    路径推导规则：
    - Model 位于 ``backend/apps/{app}/models/*.py``
      → Service 位于 ``backend/apps/{app}/services/{model_snake}_service.py``

    生成的 Service 类遵循项目约定::

        class ContractService:
            def __init__(self) -> None:
                pass

            def create_finance_log(self, contract: Contract) -> None:
                \"\"\"创建财务记录\"\"\"
                ContractFinanceLog.objects.create(
                    contract=contract, amount=contract.fixed_amount
                )
    """

    # ── 公开 API ────────────────────────────────────────────

    def generate(
        self,
        refactoring: SaveMethodRefactoring,
        *,
        project_root: Optional[Path] = None,
        target_service_path: Optional[Path] = None,
    ) -> ServiceGenerationResult:
        """
        根据 SaveMethodRefactoring 生成或更新 Service 文件。

        Args:
            refactoring: BusinessLogicExtractor 的提取结果
            project_root: 项目根目录（用于推导 Service 文件路径）
            target_service_path: 显式指定目标 Service 文件路径（优先级高于推导）

        Returns:
            ServiceGenerationResult 包含生成结果详情
        """
        model_name = refactoring.model_name
        service_class_name = f"{model_name}Service"

        # 确定目标文件路径
        service_path = self._resolve_service_path(
            refactoring, project_root, target_service_path,
        )

        if not refactoring.service_methods:
            logger.info("%s: 无 Service 方法需要生成", model_name)
            return ServiceGenerationResult(
                service_file_path=str(service_path),
                service_class_name=service_class_name,
                file_created=False,
                file_content="",
            )

        if service_path.exists():
            result = self._update_existing_file(
                service_path, service_class_name, refactoring,
            )
        else:
            result = self._create_new_file(
                service_path, service_class_name, refactoring,
            )

        logger.info(
            "%s: 添加 %d 个方法, 跳过 %d 个, 文件%s",
            service_class_name,
            len(result.methods_added),
            len(result.methods_skipped),
            "新建" if result.file_created else "更新",
        )

        return result

    def generate_batch(
        self,
        refactorings: list[SaveMethodRefactoring],
        *,
        project_root: Optional[Path] = None,
    ) -> list[ServiceGenerationResult]:
        """
        批量生成 Service 方法。

        Args:
            refactorings: 多个 Model 的提取结果
            project_root: 项目根目录

        Returns:
            每个 Model 对应一个 ServiceGenerationResult
        """
        results: list[ServiceGenerationResult] = []
        for refactoring in refactorings:
            result = self.generate(refactoring, project_root=project_root)
            results.append(result)
        return results

    # ── 路径推导 ────────────────────────────────────────────

    def _resolve_service_path(
        self,
        refactoring: SaveMethodRefactoring,
        project_root: Optional[Path],
        target_service_path: Optional[Path],
    ) -> Path:
        """
        确定目标 Service 文件路径。

        优先级：
        1. 显式指定的 target_service_path
        2. 从 Model 文件路径推导

        推导规则：
        ``backend/apps/{app}/models/*.py``
        → ``backend/apps/{app}/services/{model_snake}_service.py``

        Args:
            refactoring: 提取结果
            project_root: 项目根目录
            target_service_path: 显式指定路径

        Returns:
            Service 文件的 Path
        """
        if target_service_path is not None:
            return Path(target_service_path)

        model_file = Path(refactoring.file_path)
        model_snake = _to_snake_case(refactoring.model_name)

        # 尝试从路径中提取 app 目录
        # 模式: .../apps/{app}/models/...
        parts = model_file.parts
        app_dir = self._extract_app_dir(parts)

        if app_dir is not None:
            service_file = app_dir / "services" / f"{model_snake}_service.py"
            if project_root is not None:
                service_file = project_root / service_file
            return service_file

        # 回退：在 Model 文件同级的 services 目录下
        parent = model_file.parent
        if parent.name == "models":
            parent = parent.parent
        service_dir = parent / "services"
        return service_dir / f"{model_snake}_service.py"

    @staticmethod
    def _extract_app_dir(parts: tuple[str, ...]) -> Optional[Path]:
        """
        从文件路径的 parts 中提取 app 目录路径。

        查找 ``apps/{app_name}/models`` 模式，返回 ``apps/{app_name}``。

        Args:
            parts: Path.parts 元组

        Returns:
            app 目录的相对 Path，未找到时返回 None
        """
        for i, part in enumerate(parts):
            if part == "apps" and i + 2 < len(parts):
                # 检查后续是否有 models 目录
                app_name = parts[i + 1]
                if "models" in parts[i + 2:]:
                    return Path("apps") / app_name
        return None

    # ── 更新已有文件 ────────────────────────────────────────

    def _update_existing_file(
        self,
        service_path: Path,
        service_class_name: str,
        refactoring: SaveMethodRefactoring,
    ) -> ServiceGenerationResult:
        """
        更新已有的 Service 文件，追加新方法。

        步骤：
        1. 解析现有文件 AST
        2. 查找 Service 类
        3. 获取已有方法名集合
        4. 追加不重复的新方法
        5. 更新导入语句

        Args:
            service_path: Service 文件路径
            service_class_name: 期望的 Service 类名
            refactoring: 提取结果

        Returns:
            ServiceGenerationResult
        """
        source = service_path.read_text(encoding="utf-8")

        try:
            tree = ast.parse(source)
        except SyntaxError as exc:
            logger.warning(
                "Service 文件解析失败: %s - %s", service_path, exc,
            )
            return ServiceGenerationResult(
                service_file_path=str(service_path),
                service_class_name=service_class_name,
                file_created=False,
                file_content=source,
            )

        # 查找 Service 类
        class_node = self._find_service_class(tree, service_class_name)
        actual_class_name = service_class_name
        if class_node is None:
            # 尝试查找任何以 Service 结尾的类
            class_node = self._find_any_service_class(tree)
            if class_node is not None:
                actual_class_name = class_node.name

        if class_node is None:
            logger.warning(
                "未找到 Service 类 %s，将在文件末尾追加新类",
                service_class_name,
            )
            return self._append_class_to_file(
                service_path, source, service_class_name, refactoring,
            )

        # 获取已有方法名
        existing_methods = self._get_existing_methods(class_node)

        # 分类：需要添加 vs 跳过
        methods_added: list[str] = []
        methods_skipped: list[str] = []
        methods_to_add: list[ExtractedServiceMethod] = []

        for method in refactoring.service_methods:
            if method.method_name in existing_methods:
                methods_skipped.append(method.method_name)
                logger.info(
                    "方法 %s 已存在于 %s，跳过",
                    method.method_name, actual_class_name,
                )
            else:
                methods_to_add.append(method)
                methods_added.append(method.method_name)

        if not methods_to_add:
            return ServiceGenerationResult(
                service_file_path=str(service_path),
                service_class_name=actual_class_name,
                methods_added=methods_added,
                methods_skipped=methods_skipped,
                file_created=False,
                file_content=source,
            )

        # 在类末尾插入新方法
        updated_source = self._insert_methods_into_class(
            source, class_node, methods_to_add,
        )

        # 更新导入
        updated_source = self._ensure_model_import(
            updated_source, refactoring.model_name, refactoring.file_path,
        )

        # 语法验证
        try:
            ast.parse(updated_source)
        except SyntaxError as exc:
            logger.warning("更新后代码语法错误: %s", exc)
            return ServiceGenerationResult(
                service_file_path=str(service_path),
                service_class_name=actual_class_name,
                file_created=False,
                file_content=source,
            )

        return ServiceGenerationResult(
            service_file_path=str(service_path),
            service_class_name=actual_class_name,
            methods_added=methods_added,
            methods_skipped=methods_skipped,
            file_created=False,
            file_content=updated_source,
        )

    # ── 创建新文件 ──────────────────────────────────────────

    def _create_new_file(
        self,
        service_path: Path,
        service_class_name: str,
        refactoring: SaveMethodRefactoring,
    ) -> ServiceGenerationResult:
        """
        创建新的 Service 文件。

        生成包含完整类定义、导入语句和所有方法的文件。

        Args:
            service_path: 目标文件路径
            service_class_name: Service 类名
            refactoring: 提取结果

        Returns:
            ServiceGenerationResult
        """
        model_name = refactoring.model_name
        model_import = self._build_model_import(model_name, refactoring.file_path)

        # 收集额外需要的导入（从方法体中分析）
        extra_imports = self._collect_extra_imports(refactoring.service_methods)

        # 构建文件内容
        lines: list[str] = []

        # 文件头
        lines.append('"""')
        lines.append(f"{service_class_name}")
        lines.append("")
        model_snake = _to_snake_case(model_name)
        lines.append(f"从 {model_name}.save() 提取的业务逻辑。")
        lines.append('"""')
        lines.append("from __future__ import annotations")
        lines.append("")

        # 导入
        if model_import:
            lines.append(model_import)
        for imp in sorted(extra_imports):
            lines.append(imp)
        if model_import or extra_imports:
            lines.append("")
            lines.append("")

        # 类定义
        lines.append(f"class {service_class_name}:")
        lines.append("")
        lines.append("    def __init__(self) -> None:")
        lines.append("        pass")

        # 方法
        methods_added: list[str] = []
        for method in refactoring.service_methods:
            lines.append("")
            method_code = format_service_method_template(method, indent="    ")
            lines.append(method_code)
            methods_added.append(method.method_name)

        lines.append("")  # 文件末尾空行

        file_content = "\n".join(lines)

        # 语法验证
        try:
            ast.parse(file_content)
        except SyntaxError as exc:
            logger.warning("生成的代码语法错误: %s", exc)
            # 仍然返回结果，让调用方决定如何处理
            return ServiceGenerationResult(
                service_file_path=str(service_path),
                service_class_name=service_class_name,
                methods_added=methods_added,
                file_created=True,
                file_content=file_content,
            )

        return ServiceGenerationResult(
            service_file_path=str(service_path),
            service_class_name=service_class_name,
            methods_added=methods_added,
            file_created=True,
            file_content=file_content,
        )

    # ── AST 辅助方法 ───────────────────────────────────────

    @staticmethod
    def _find_service_class(
        tree: ast.Module,
        class_name: str,
    ) -> Optional[ast.ClassDef]:
        """按名称查找 Service 类节点。"""
        for node in ast.iter_child_nodes(tree):
            if isinstance(node, ast.ClassDef) and node.name == class_name:
                return node
        return None

    @staticmethod
    def _find_any_service_class(
        tree: ast.Module,
    ) -> Optional[ast.ClassDef]:
        """查找任何以 Service 结尾的类节点。"""
        for node in ast.iter_child_nodes(tree):
            if isinstance(node, ast.ClassDef) and node.name.endswith("Service"):
                return node
        return None

    @staticmethod
    def _get_existing_methods(class_node: ast.ClassDef) -> set[str]:
        """获取类中已有的方法名集合。"""
        methods: set[str] = set()
        for node in class_node.body:
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                methods.add(node.name)
        return methods

    def _insert_methods_into_class(
        self,
        source: str,
        class_node: ast.ClassDef,
        methods: list[ExtractedServiceMethod],
    ) -> str:
        """
        在类定义末尾插入新方法。

        通过定位类的最后一行，在其后插入方法代码。

        Args:
            source: 原始源代码
            class_node: 类的 AST 节点
            methods: 要插入的方法列表

        Returns:
            更新后的源代码
        """
        lines = source.splitlines(keepends=True)

        # 确定类的最后一行
        class_end_line = getattr(class_node, "end_lineno", None)
        if class_end_line is None:
            # 回退：使用类体最后一个节点的行号
            class_end_line = self._estimate_class_end(class_node, lines)

        # 生成方法代码
        method_blocks: list[str] = []
        for method in methods:
            method_code = format_service_method_template(method, indent="    ")
            method_blocks.append(method_code)

        insert_text = "\n" + "\n\n".join(method_blocks) + "\n"

        # 在类末尾插入
        idx = class_end_line  # end_lineno 是 1-based，作为 insert 位置刚好
        before = lines[:idx]
        after = lines[idx:]

        return "".join(before) + insert_text + "".join(after)

    @staticmethod
    def _estimate_class_end(
        class_node: ast.ClassDef,
        lines: list[str],
    ) -> int:
        """
        估算类定义的结束行号（1-based）。

        遍历类体中所有节点，取最大的 end_lineno。

        Args:
            class_node: 类的 AST 节点
            lines: 源代码行列表

        Returns:
            估算的结束行号（1-based）
        """
        max_line = class_node.lineno
        for node in ast.walk(class_node):
            end = getattr(node, "end_lineno", None)
            if end is not None and end > max_line:
                max_line = end
        return max_line

    def _append_class_to_file(
        self,
        service_path: Path,
        source: str,
        service_class_name: str,
        refactoring: SaveMethodRefactoring,
    ) -> ServiceGenerationResult:
        """
        在文件末尾追加新的 Service 类。

        当文件存在但不包含目标 Service 类时使用。

        Args:
            service_path: 文件路径
            source: 现有源代码
            service_class_name: 类名
            refactoring: 提取结果

        Returns:
            ServiceGenerationResult
        """
        lines: list[str] = ["\n\n"]
        lines.append(f"class {service_class_name}:\n")
        lines.append("\n")
        lines.append("    def __init__(self) -> None:\n")
        lines.append("        pass\n")

        methods_added: list[str] = []
        for method in refactoring.service_methods:
            lines.append("\n")
            method_code = format_service_method_template(method, indent="    ")
            lines.append(method_code + "\n")
            methods_added.append(method.method_name)

        updated_source = source.rstrip("\n") + "".join(lines)

        # 确保导入
        updated_source = self._ensure_model_import(
            updated_source, refactoring.model_name, refactoring.file_path,
        )

        return ServiceGenerationResult(
            service_file_path=str(service_path),
            service_class_name=service_class_name,
            methods_added=methods_added,
            file_created=False,
            file_content=updated_source,
        )

    # ── 导入管理 ────────────────────────────────────────────

    def _build_model_import(
        self,
        model_name: str,
        model_file_path: str,
    ) -> str:
        """
        根据 Model 文件路径构建导入语句。

        从路径中提取 app 名称，生成::

            from apps.{app}.models import {ModelName}

        如果无法推导 app，使用相对导入::

            from ..models import {ModelName}

        Args:
            model_name: Model 类名
            model_file_path: Model 文件路径

        Returns:
            导入语句字符串
        """
        parts = Path(model_file_path).parts
        app_name = self._extract_app_name(parts)

        if app_name:
            return f"from apps.{app_name}.models import {model_name}"

        return f"from ..models import {model_name}"

    @staticmethod
    def _extract_app_name(parts: tuple[str, ...]) -> Optional[str]:
        """
        从路径 parts 中提取 app 名称。

        查找 ``apps/{app_name}`` 模式。

        Args:
            parts: Path.parts 元组

        Returns:
            app 名称，未找到时返回 None
        """
        for i, part in enumerate(parts):
            if part == "apps" and i + 1 < len(parts):
                return parts[i + 1]
        return None

    def _ensure_model_import(
        self,
        source: str,
        model_name: str,
        model_file_path: str,
    ) -> str:
        """
        确保源代码中包含 Model 的导入语句。

        如果已存在则不重复添加。

        Args:
            source: 源代码
            model_name: Model 类名
            model_file_path: Model 文件路径

        Returns:
            可能更新了导入的源代码
        """
        if self._has_import(source, model_name):
            return source

        import_line = self._build_model_import(model_name, model_file_path)
        return self._add_import_line(source, import_line)

    @staticmethod
    def _has_import(source: str, name: str) -> bool:
        """
        检查源代码中是否已导入指定名称。

        Args:
            source: 源代码
            name: 要检查的名称

        Returns:
            True 如果已导入
        """
        try:
            tree = ast.parse(source)
        except SyntaxError:
            return False

        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom):
                for alias in node.names:
                    actual_name = alias.asname if alias.asname else alias.name
                    if actual_name == name:
                        return True
            elif isinstance(node, ast.Import):
                for alias in node.names:
                    actual_name = alias.asname if alias.asname else alias.name
                    if actual_name == name:
                        return True
        return False

    @staticmethod
    def _add_import_line(source: str, import_line: str) -> str:
        """
        在导入区域末尾添加新的导入行。

        查找最后一个 import/from 语句，在其后插入。

        Args:
            source: 源代码
            import_line: 要添加的导入语句

        Returns:
            更新后的源代码
        """
        lines = source.splitlines(keepends=True)

        last_import_idx = -1
        for i, line in enumerate(lines):
            stripped = line.strip()
            if stripped.startswith(("import ", "from ")):
                last_import_idx = i
                # 处理多行导入
                if "(" in stripped and ")" not in stripped:
                    j = i + 1
                    while j < len(lines) and ")" not in lines[j]:
                        j += 1
                    last_import_idx = j

        insert_idx = last_import_idx + 1 if last_import_idx >= 0 else 0
        lines.insert(insert_idx, import_line + "\n")

        return "".join(lines)

    def _collect_extra_imports(
        self,
        methods: list[ExtractedServiceMethod],
    ) -> list[str]:
        """
        从方法体中分析需要的额外导入。

        扫描方法体代码，查找 ``OtherModel.objects`` 模式，
        收集需要导入的 Model 名称。

        注意：这里只收集明显的 Model 引用，
        复杂场景需要人工审查。

        Args:
            methods: 提取的 Service 方法列表

        Returns:
            额外导入语句列表
        """
        # 当前实现不自动添加额外导入，
        # 因为方法体中引用的 Model 可能来自同一 app（已有导入）
        # 或需要通过 ServiceLocator 访问（跨模块）。
        # 这些情况需要后续的跨模块依赖分析来处理。
        return []
