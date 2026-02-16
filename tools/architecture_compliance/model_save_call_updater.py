"""
Model.save() 调用点更新器

当 BusinessLogicExtractor 从 Model.save() 中提取业务逻辑后，
需要在代码库中所有调用 instance.save() 的地方插入 Service 方法调用，
确保业务逻辑仍然被正确执行。

策略：
1. 扫描代码库中所有对指定 Model 实例调用 .save() 的地方
2. 在 save() 调用之后插入 Service 方法调用
3. 添加 Service 的导入和实例化代码
4. 保持代码缩进一致

采用行级正则替换，与 CallSiteUpdater 保持一致的风格。
"""
from __future__ import annotations

import ast
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

from .logging_config import get_logger
from .models import RefactoringResult

logger = get_logger("model_save_call_updater")


# ── 数据模型 ────────────────────────────────────────────────


@dataclass
class ModelSaveCallSite:
    """单个 Model.save() 调用点信息"""

    file_path: str
    line_number: int  # 1-based
    original_code: str  # 原始行内容（strip后）
    model_name: str
    context_info: str  # 调用上下文描述（如函数名）


@dataclass
class ModelSaveCallUpdate:
    """单个调用点的更新结果"""

    call_site: ModelSaveCallSite
    new_code: str  # 插入 Service 调用后的代码
    service_method_added: str  # 插入的 Service 方法名


@dataclass
class FileModelSaveReport:
    """单个文件的 Model.save() 调用点更新报告"""

    file_path: str
    call_sites_found: int = 0
    call_sites_updated: int = 0
    service_import_added: bool = False
    changes: list[str] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)


@dataclass
class ModelSaveUpdateReport:
    """整体 Model.save() 调用点更新报告"""

    total_files_scanned: int = 0
    total_call_sites_found: int = 0
    total_call_sites_updated: int = 0
    file_reports: list[FileModelSaveReport] = field(default_factory=list)
    results: list[RefactoringResult] = field(default_factory=list)


# ── 排除目录 ────────────────────────────────────────────────

_EXCLUDE_DIRS: frozenset[str] = frozenset({
    "__pycache__", ".git", ".tox", ".mypy_cache",
    ".pytest_cache", "node_modules", "migrations",
    "venv", ".venv", "venv312",
})


# ── CamelCase → snake_case ──────────────────────────────────

_CAMEL_RE: re.Pattern[str] = re.compile(
    r"(?<=[a-z0-9])(?=[A-Z])|(?<=[A-Z])(?=[A-Z][a-z])"
)


def _to_snake_case(name: str) -> str:
    """将 CamelCase 转为 snake_case。"""
    return _CAMEL_RE.sub("_", name).lower()


# ── ModelSaveCallUpdater ────────────────────────────────────


class ModelSaveCallUpdater:
    """
    Model.save() 调用点更新器

    扫描代码库中所有对指定 Model 实例调用 ``.save()`` 的地方，
    在 save() 调用之后插入 Service 方法调用，确保提取的业务逻辑
    仍然被正确执行。

    策略：
    1. 通过正则匹配 ``variable.save()`` 模式
    2. 结合 AST 分析确认变量类型是否为目标 Model
    3. 在 save() 调用行之后插入 Service 方法调用
    4. 添加 Service 导入和实例化代码
    """

    # ── 公开 API ────────────────────────────────────────────

    def scan_save_call_sites(
        self,
        root: Path,
        model_name: str,
        *,
        exclude_file: Optional[Path] = None,
    ) -> list[ModelSaveCallSite]:
        """
        扫描目录下所有文件，查找对指定 Model 实例的 .save() 调用。

        通过以下方式识别 Model 实例：
        - 变量赋值: ``obj = ModelName(...)`` 或 ``obj = ModelName.objects.get(...)``
        - 函数参数类型注解: ``def func(obj: ModelName)``
        - 常见命名模式: snake_case 版本的 Model 名称

        Args:
            root: 扫描根目录
            model_name: Model 类名（如 ``Contract``）
            exclude_file: 排除的文件（通常是 Model 定义所在文件）

        Returns:
            调用点列表
        """
        root = Path(root)
        if not root.is_dir():
            logger.warning("路径不是目录: %s", root)
            return []

        snake_name = _to_snake_case(model_name)
        call_sites: list[ModelSaveCallSite] = []
        py_files = _collect_python_files(root)

        for py_file in py_files:
            if exclude_file and py_file.resolve() == Path(exclude_file).resolve():
                continue

            source = _read_source(py_file)
            if source is None:
                continue

            # 检查文件是否导入了该 Model
            if not self._file_references_model(source, model_name):
                continue

            sites = self._scan_file_save_calls(
                py_file, source, model_name, snake_name,
            )
            call_sites.extend(sites)

        logger.info(
            "扫描到 %d 个 %s.save() 调用点",
            len(call_sites),
            model_name,
        )
        return call_sites

    def update_save_call_sites(
        self,
        root: Path,
        model_name: str,
        service_class_name: str,
        service_methods: list[str],
        *,
        exclude_file: Optional[Path] = None,
        dry_run: bool = False,
    ) -> ModelSaveUpdateReport:
        """
        扫描并更新所有 Model.save() 调用点。

        在每个 save() 调用之后插入 Service 方法调用。

        Args:
            root: 扫描根目录
            model_name: Model 类名
            service_class_name: Service 类名（如 ``ContractService``）
            service_methods: 需要在 save() 后调用的 Service 方法名列表
            exclude_file: 排除的文件
            dry_run: 为 True 时不写入文件

        Returns:
            更新报告
        """
        report = ModelSaveUpdateReport()

        call_sites = self.scan_save_call_sites(
            root, model_name, exclude_file=exclude_file,
        )
        report.total_call_sites_found = len(call_sites)

        # 按文件分组
        sites_by_file: dict[str, list[ModelSaveCallSite]] = {}
        for site in call_sites:
            sites_by_file.setdefault(site.file_path, []).append(site)

        report.total_files_scanned = len(sites_by_file)

        for file_path_str, sites in sites_by_file.items():
            file_path = Path(file_path_str)
            file_report = self._update_file_save_call_sites(
                file_path,
                sites,
                model_name,
                service_class_name,
                service_methods,
                dry_run=dry_run,
            )
            report.file_reports.append(file_report)
            report.total_call_sites_updated += file_report.call_sites_updated

            result = RefactoringResult(
                success=not file_report.errors,
                file_path=file_path_str,
                changes_made=file_report.changes,
                error_message=(
                    "; ".join(file_report.errors) if file_report.errors else None
                ),
            )
            report.results.append(result)

        logger.info(
            "Model.save() 调用点更新完成: 扫描 %d 个文件, 更新 %d/%d 个调用点",
            report.total_files_scanned,
            report.total_call_sites_updated,
            report.total_call_sites_found,
        )
        return report

    # ── 文件级扫描 ──────────────────────────────────────────

    def _file_references_model(
        self,
        source: str,
        model_name: str,
    ) -> bool:
        """
        检查文件是否引用了指定 Model。

        通过检查导入语句或类名出现来判断。

        Args:
            source: 源代码
            model_name: Model 类名

        Returns:
            True 表示文件引用了该 Model
        """
        # 检查 import 语句
        import_pattern = re.compile(
            rf"\bimport\b.*\b{re.escape(model_name)}\b"
            rf"|\bfrom\b.*\bimport\b.*\b{re.escape(model_name)}\b",
        )
        if import_pattern.search(source):
            return True

        # 检查类名直接出现（如 Model 实例化）
        usage_pattern = re.compile(
            rf"\b{re.escape(model_name)}\s*\("
            rf"|\b{re.escape(model_name)}\.objects\b",
        )
        return bool(usage_pattern.search(source))

    def _scan_file_save_calls(
        self,
        file_path: Path,
        source: str,
        model_name: str,
        snake_name: str,
    ) -> list[ModelSaveCallSite]:
        """
        扫描单个文件中对 Model 实例的 .save() 调用。

        识别策略：
        1. 查找所有 ``variable.save()`` 调用
        2. 通过 AST 分析确认变量是否为目标 Model 实例
        3. 通过命名模式匹配（snake_case 版本）

        Args:
            file_path: 文件路径
            source: 源代码
            model_name: Model 类名
            snake_name: Model 名称的 snake_case 版本

        Returns:
            调用点列表
        """
        call_sites: list[ModelSaveCallSite] = []

        # 收集已知的 Model 实例变量名
        instance_vars = self._find_model_instance_vars(
            source, model_name, snake_name,
        )

        # 匹配 variable.save() 模式
        save_pattern = re.compile(r"\b(\w+)\.save\s*\(")

        lines = source.splitlines()
        for lineno, line in enumerate(lines, start=1):
            stripped = line.strip()
            # 跳过注释
            if stripped.startswith("#"):
                continue

            match = save_pattern.search(line)
            if match is None:
                continue

            var_name = match.group(1)

            # 跳过 super().save() 调用
            if var_name == "super":
                continue
            # 跳过 self.save() — 通常是 Model 内部调用
            if var_name == "self":
                continue

            # 检查变量是否为目标 Model 实例
            if var_name not in instance_vars:
                continue

            context = self._get_context_info(source, lineno)
            call_sites.append(ModelSaveCallSite(
                file_path=str(file_path),
                line_number=lineno,
                original_code=stripped,
                model_name=model_name,
                context_info=context,
            ))

        return call_sites

    def _find_model_instance_vars(
        self,
        source: str,
        model_name: str,
        snake_name: str,
    ) -> set[str]:
        """
        查找源代码中所有已知的 Model 实例变量名。

        识别模式：
        - ``var = ModelName(...)``
        - ``var = ModelName.objects.get(...)``
        - ``var = ModelName.objects.create(...)``
        - 函数参数类型注解: ``def func(var: ModelName)``
        - 常见命名: snake_case 版本

        Args:
            source: 源代码
            model_name: Model 类名
            snake_name: snake_case 版本

        Returns:
            实例变量名集合
        """
        instance_vars: set[str] = set()

        # 模式1: var = ModelName(...) 或 var = ModelName.objects.xxx(...)
        assign_pattern = re.compile(
            rf"(\w+)\s*=\s*{re.escape(model_name)}\s*\("
            rf"|(\w+)\s*=\s*{re.escape(model_name)}\.objects\.\w+\s*\(",
        )
        for m in assign_pattern.finditer(source):
            var = m.group(1) or m.group(2)
            if var:
                instance_vars.add(var)

        # 模式2: 函数参数类型注解 def func(var: ModelName)
        param_pattern = re.compile(
            rf"(\w+)\s*:\s*{re.escape(model_name)}\b",
        )
        for m in param_pattern.finditer(source):
            instance_vars.add(m.group(1))

        # 模式3: 常见命名模式
        # 如果 snake_name 出现在赋值左侧，也认为是实例变量
        common_names = {snake_name, f"new_{snake_name}", f"the_{snake_name}"}
        for name in common_names:
            name_pattern = re.compile(
                rf"\b{re.escape(name)}\s*=\s*",
            )
            if name_pattern.search(source):
                instance_vars.add(name)

        return instance_vars

    def _get_context_info(
        self,
        source: str,
        line_number: int,
    ) -> str:
        """
        获取调用点的上下文信息（所在函数/方法名）。

        Args:
            source: 源代码
            line_number: 行号 (1-based)

        Returns:
            上下文描述字符串
        """
        tree = _parse_ast(source, Path("<context>"))
        if tree is None:
            return "unknown"

        for node in ast.walk(tree):
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                end_line = node.end_lineno or node.lineno
                if node.lineno <= line_number <= end_line:
                    # 检查是否在类内部
                    for parent in ast.walk(tree):
                        if isinstance(parent, ast.ClassDef):
                            for child in ast.iter_child_nodes(parent):
                                if child is node:
                                    return f"{parent.name}.{node.name}"
                    return node.name

        return "module-level"

    # ── 文件级更新 ──────────────────────────────────────────

    def _update_file_save_call_sites(
        self,
        file_path: Path,
        call_sites: list[ModelSaveCallSite],
        model_name: str,
        service_class_name: str,
        service_methods: list[str],
        *,
        dry_run: bool = False,
    ) -> FileModelSaveReport:
        """
        更新单个文件中的所有 Model.save() 调用点。

        在每个 save() 调用之后插入 Service 方法调用。

        Args:
            file_path: 文件路径
            call_sites: 该文件中的调用点列表
            model_name: Model 类名
            service_class_name: Service 类名
            service_methods: 需要调用的 Service 方法名列表
            dry_run: 为 True 时不写入文件

        Returns:
            文件更新报告
        """
        file_report = FileModelSaveReport(
            file_path=str(file_path),
            call_sites_found=len(call_sites),
        )

        source = _read_source(file_path)
        if source is None:
            file_report.errors.append(f"无法读取文件: {file_path}")
            return file_report

        lines = source.splitlines(keepends=True)
        snake_name = _to_snake_case(model_name)
        service_var = _to_snake_case(service_class_name)

        # 按行号倒序处理，避免插入行导致行号偏移
        sorted_sites = sorted(call_sites, key=lambda s: s.line_number, reverse=True)
        updated_count = 0

        for site in sorted_sites:
            line_idx = site.line_number - 1
            if line_idx < 0 or line_idx >= len(lines):
                file_report.errors.append(f"行号越界: {site.line_number}")
                continue

            save_line = lines[line_idx]

            # 提取 save() 调用行的缩进
            indent = self._get_indent(save_line)

            # 提取 save() 调用中的实例变量名
            save_match = re.search(r"\b(\w+)\.save\s*\(", save_line)
            if save_match is None:
                file_report.errors.append(
                    f"行 {site.line_number}: 无法匹配 .save() 模式"
                )
                continue

            instance_var = save_match.group(1)

            # 生成 Service 方法调用代码
            service_call_lines = self._build_service_call_lines(
                indent,
                service_var,
                service_methods,
                instance_var,
            )

            # 在 save() 调用之后插入 Service 方法调用
            insert_idx = line_idx + 1
            for i, call_line in enumerate(service_call_lines):
                lines.insert(insert_idx + i, call_line)

            updated_count += 1
            methods_str = ", ".join(service_methods)
            file_report.changes.append(
                f"行 {site.line_number}: 在 {instance_var}.save() 后插入 "
                f"Service 方法调用: {methods_str}"
            )

        # 添加 Service 导入和实例化
        if updated_count > 0:
            lines = self._ensure_service_import(
                lines, file_path, service_class_name,
            )
            file_report.service_import_added = True

            lines = self._ensure_service_instantiation(
                lines, service_class_name, service_var,
            )

        file_report.call_sites_updated = updated_count

        # 语法验证
        new_source = "".join(lines)
        try:
            ast.parse(new_source)
        except SyntaxError as exc:
            file_report.errors.append(
                f"更新后语法错误 (行 {exc.lineno}): {exc.msg}"
            )
            return file_report

        if not dry_run and updated_count > 0:
            file_path.write_text(new_source, encoding="utf-8")
            logger.info(
                "已更新文件: %s (%d 个 save() 调用点)",
                file_path,
                updated_count,
            )

        return file_report

    # ── Service 调用代码生成 ────────────────────────────────

    @staticmethod
    def _build_service_call_lines(
        indent: str,
        service_var: str,
        service_methods: list[str],
        instance_var: str,
    ) -> list[str]:
        """
        生成 Service 方法调用代码行。

        Args:
            indent: 缩进字符串
            service_var: Service 实例变量名
            service_methods: Service 方法名列表
            instance_var: Model 实例变量名

        Returns:
            代码行列表（含换行符）
        """
        call_lines: list[str] = []
        for method_name in service_methods:
            call_lines.append(
                f"{indent}{service_var}.{method_name}({instance_var})\n"
            )
        return call_lines

    @staticmethod
    def _get_indent(line: str) -> str:
        """
        提取行的缩进。

        Args:
            line: 代码行

        Returns:
            缩进字符串
        """
        return line[: len(line) - len(line.lstrip())]

    # ── 导入管理 ────────────────────────────────────────────

    def _ensure_service_import(
        self,
        lines: list[str],
        file_path: Path,
        service_class_name: str,
    ) -> list[str]:
        """
        确保文件中包含 Service 类的导入语句。

        如果文件中已有该导入则跳过。

        Args:
            lines: 源代码行列表
            file_path: 文件路径（用于推导导入路径）
            service_class_name: Service 类名

        Returns:
            修改后的行列表
        """
        result = list(lines)
        source = "".join(result)

        # 检查是否已有导入
        if re.search(
            rf"\bimport\b.*\b{re.escape(service_class_name)}\b",
            source,
        ):
            return result

        # 生成导入语句
        service_module = _to_snake_case(service_class_name)
        import_line = (
            f"from .services import {service_class_name}  "
            f"# noqa: E402 — auto-inserted by model_save_call_updater\n"
        )

        # 在 import 区域末尾插入
        insert_idx = _find_import_end(result)

        result.insert(insert_idx, import_line)
        logger.info(
            "在第 %d 行插入 Service 导入: %s",
            insert_idx + 1,
            service_class_name,
        )
        return result

    def _ensure_service_instantiation(
        self,
        lines: list[str],
        service_class_name: str,
        service_var: str,
    ) -> list[str]:
        """
        确保文件中包含 Service 实例化代码。

        在 import 区域之后插入模块级实例化。

        Args:
            lines: 源代码行列表
            service_class_name: Service 类名
            service_var: Service 实例变量名

        Returns:
            修改后的行列表
        """
        result = list(lines)
        source = "".join(result)

        # 检查是否已有实例化
        instantiation_pattern = f"{service_var} = {service_class_name}("
        if instantiation_pattern in source:
            return result

        # 在 import 区域之后插入
        insert_idx = _find_import_end(result)

        # 确保前面有空行
        if insert_idx > 0 and result[insert_idx - 1].strip():
            result.insert(insert_idx, "\n")
            insert_idx += 1

        instantiation_line = f"{service_var} = {service_class_name}()\n"
        result.insert(insert_idx, instantiation_line)

        logger.info(
            "在第 %d 行插入 Service 实例化: %s = %s()",
            insert_idx + 1,
            service_var,
            service_class_name,
        )
        return result


# ── 模块级辅助函数 ──────────────────────────────────────────


def _find_import_end(lines: list[str]) -> int:
    """
    查找 import 区域的结束位置。

    Args:
        lines: 源代码行列表

    Returns:
        import 区域之后的行索引 (0-based)，无 import 时返回 0
    """
    last_import_idx = -1
    in_import_block = False

    for i, line in enumerate(lines):
        stripped = line.strip()
        if stripped.startswith(("import ", "from ")):
            last_import_idx = i
            in_import_block = True
        elif in_import_block and not stripped:
            # import 块后的空行
            continue
        elif in_import_block and stripped and not stripped.startswith("#"):
            # import 块结束
            break

    return last_import_idx + 1


def _collect_python_files(root: Path) -> list[Path]:
    """
    收集目录下所有 Python 文件。

    排除 __pycache__、migrations、venv 等目录。

    Args:
        root: 根目录

    Returns:
        排序后的文件路径列表
    """
    py_files: list[Path] = []
    for path in sorted(root.rglob("*.py")):
        if any(part in _EXCLUDE_DIRS for part in path.parts):
            continue
        py_files.append(path)
    return py_files


def _read_source(file_path: Path) -> Optional[str]:
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


def _parse_ast(source: str, file_path: Path) -> Optional[ast.Module]:
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
        logger.warning(
            "语法错误 %s (行 %s): %s",
            file_path,
            exc.lineno,
            exc.msg,
        )
        return None
