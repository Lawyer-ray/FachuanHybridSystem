"""
静态方法调用点更新器

当 StaticMethodConverter 将静态方法转换为实例方法后，
需要更新代码库中所有调用该方法的地方：

- ``ClassName.method(args)`` → ``instance.method(args)``
- 如果调用点所在作用域没有可用实例，则插入实例化代码

采用行级正则替换，与 StaticMethodConverter 保持一致。
"""
from __future__ import annotations

import ast
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

from .logging_config import get_logger
from .models import RefactoringResult
from .static_method_analyzer import StaticMethodInfo

logger = get_logger("call_site_updater")


# ── 数据模型 ────────────────────────────────────────────────


@dataclass
class CallSite:
    """单个调用点信息"""

    file_path: str
    line_number: int  # 1-based
    original_code: str  # 原始行内容（strip后）
    class_name: str
    method_name: str


@dataclass
class CallSiteUpdate:
    """单个调用点的更新结果"""

    call_site: CallSite
    new_code: str  # 替换后的行内容
    instance_var: str  # 使用的实例变量名
    needs_instantiation: bool  # 是否需要插入实例化代码


@dataclass
class FileCallSiteReport:
    """单个文件的调用点更新报告"""

    file_path: str
    call_sites_found: int = 0
    call_sites_updated: int = 0
    instantiation_added: bool = False
    changes: list[str] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)


@dataclass
class CallSiteUpdateReport:
    """整体调用点更新报告"""

    total_files_scanned: int = 0
    total_call_sites_found: int = 0
    total_call_sites_updated: int = 0
    file_reports: list[FileCallSiteReport] = field(default_factory=list)
    results: list[RefactoringResult] = field(default_factory=list)


# ── 排除目录 ────────────────────────────────────────────────

_EXCLUDE_DIRS: frozenset[str] = frozenset({
    "__pycache__", ".git", ".tox", ".mypy_cache",
    ".pytest_cache", "node_modules", "migrations",
    "venv", ".venv", "venv312",
})


# ── CallSiteUpdater ─────────────────────────────────────────


class CallSiteUpdater:
    """
    静态方法调用点更新器

    扫描代码库中所有对已转换静态方法的调用，
    将 ``ClassName.method(args)`` 替换为 ``instance.method(args)``。

    策略：
    1. 如果调用点在同一个类内部 → 替换为 ``self.method(args)``
    2. 如果调用点所在作用域已有该类的实例变量 → 使用现有实例
    3. 否则 → 插入实例化代码并使用新变量
    """

    # ── 公开 API ────────────────────────────────────────────

    def scan_call_sites(
        self,
        root: Path,
        class_name: str,
        method_name: str,
        *,
        exclude_file: Optional[Path] = None,
    ) -> list[CallSite]:
        """
        扫描目录下所有文件，查找对指定静态方法的调用。

        Args:
            root: 扫描根目录
            class_name: 类名
            method_name: 方法名
            exclude_file: 排除的文件（通常是方法定义所在文件）

        Returns:
            调用点列表
        """
        root = Path(root)
        if not root.is_dir():
            logger.warning("路径不是目录: %s", root)
            return []

        pattern = re.compile(
            rf"\b{re.escape(class_name)}\.{re.escape(method_name)}\s*\(",
        )

        call_sites: list[CallSite] = []
        py_files = self._collect_python_files(root)

        for py_file in py_files:
            if exclude_file and py_file.resolve() == Path(exclude_file).resolve():
                continue

            source = self._read_source(py_file)
            if source is None:
                continue

            for lineno, line in enumerate(source.splitlines(), start=1):
                stripped = line.strip()
                # 跳过注释和字符串
                if stripped.startswith("#"):
                    continue
                if pattern.search(line):
                    call_sites.append(CallSite(
                        file_path=str(py_file),
                        line_number=lineno,
                        original_code=stripped,
                        class_name=class_name,
                        method_name=method_name,
                    ))

        logger.info(
            "扫描到 %d 个 %s.%s() 调用点",
            len(call_sites),
            class_name,
            method_name,
        )
        return call_sites

    def update_call_sites(
        self,
        root: Path,
        class_name: str,
        method_name: str,
        *,
        exclude_file: Optional[Path] = None,
        dry_run: bool = False,
    ) -> CallSiteUpdateReport:
        """
        扫描并更新所有调用点。

        Args:
            root: 扫描根目录
            class_name: 类名
            method_name: 方法名
            exclude_file: 排除的文件
            dry_run: 为 True 时不写入文件

        Returns:
            更新报告
        """
        report = CallSiteUpdateReport()

        call_sites = self.scan_call_sites(
            root, class_name, method_name,
            exclude_file=exclude_file,
        )
        report.total_call_sites_found = len(call_sites)

        # 按文件分组
        sites_by_file: dict[str, list[CallSite]] = {}
        for site in call_sites:
            sites_by_file.setdefault(site.file_path, []).append(site)

        report.total_files_scanned = len(sites_by_file)

        for file_path_str, sites in sites_by_file.items():
            file_path = Path(file_path_str)
            file_report = self._update_file_call_sites(
                file_path, sites, class_name, method_name,
                dry_run=dry_run,
            )
            report.file_reports.append(file_report)
            report.total_call_sites_updated += file_report.call_sites_updated

            result = RefactoringResult(
                success=not file_report.errors,
                file_path=file_path_str,
                changes_made=file_report.changes,
                error_message="; ".join(file_report.errors) if file_report.errors else None,
            )
            report.results.append(result)

        logger.info(
            "调用点更新完成: 扫描 %d 个文件, 更新 %d/%d 个调用点",
            report.total_files_scanned,
            report.total_call_sites_updated,
            report.total_call_sites_found,
        )
        return report

    def update_call_sites_for_methods(
        self,
        root: Path,
        methods: list[StaticMethodInfo],
        *,
        exclude_file: Optional[Path] = None,
        dry_run: bool = False,
    ) -> CallSiteUpdateReport:
        """
        批量更新多个已转换方法的调用点。

        Args:
            root: 扫描根目录
            methods: 已转换的静态方法列表
            exclude_file: 排除的文件
            dry_run: 为 True 时不写入文件

        Returns:
            汇总更新报告
        """
        combined_report = CallSiteUpdateReport()

        for method_info in methods:
            sub_report = self.update_call_sites(
                root,
                method_info.class_name,
                method_info.method_name,
                exclude_file=exclude_file or Path(method_info.file_path),
                dry_run=dry_run,
            )
            combined_report.total_files_scanned += sub_report.total_files_scanned
            combined_report.total_call_sites_found += sub_report.total_call_sites_found
            combined_report.total_call_sites_updated += sub_report.total_call_sites_updated
            combined_report.file_reports.extend(sub_report.file_reports)
            combined_report.results.extend(sub_report.results)

        return combined_report

    # ── 文件级更新 ──────────────────────────────────────────

    def _update_file_call_sites(
        self,
        file_path: Path,
        call_sites: list[CallSite],
        class_name: str,
        method_name: str,
        *,
        dry_run: bool = False,
    ) -> FileCallSiteReport:
        """
        更新单个文件中的所有调用点。

        Args:
            file_path: 文件路径
            call_sites: 该文件中的调用点列表
            class_name: 类名
            method_name: 方法名
            dry_run: 为 True 时不写入文件

        Returns:
            文件更新报告
        """
        file_report = FileCallSiteReport(
            file_path=str(file_path),
            call_sites_found=len(call_sites),
        )

        source = self._read_source(file_path)
        if source is None:
            file_report.errors.append(f"无法读取文件: {file_path}")
            return file_report

        lines = source.splitlines(keepends=True)
        tree = self._parse_ast(source, file_path)

        # 确定调用点的上下文（是否在同类内部、是否已有实例）
        call_pattern = re.compile(
            rf"\b{re.escape(class_name)}\.{re.escape(method_name)}\s*\(",
        )

        instance_var = self._to_snake_case(class_name)
        needs_instantiation = False
        updated_count = 0

        # 检查文件中是否已有该类的实例
        has_existing_instance = self._find_existing_instance(
            source, class_name, instance_var,
        )

        # 检查调用点是否在同类内部
        class_line_ranges = self._get_class_line_ranges(tree, class_name)

        for site in call_sites:
            line_idx = site.line_number - 1
            if line_idx < 0 or line_idx >= len(lines):
                file_report.errors.append(
                    f"行号越界: {site.line_number}"
                )
                continue

            line = lines[line_idx]

            # 判断是否在同类内部
            in_same_class = self._is_in_class(
                site.line_number, class_line_ranges,
            )

            if in_same_class:
                # 同类内部 → self.method(...)
                replacement = "self."
            elif has_existing_instance:
                # 已有实例 → instance_var.method(...)
                replacement = f"{instance_var}."
            else:
                # 需要新建实例
                replacement = f"{instance_var}."
                needs_instantiation = True

            new_line = call_pattern.sub(
                f"{replacement}{method_name}(",
                line,
            )

            if new_line != line:
                lines[line_idx] = new_line
                updated_count += 1
                file_report.changes.append(
                    f"行 {site.line_number}: "
                    f"{class_name}.{method_name}() → "
                    f"{replacement}{method_name}()"
                )

        # 如果需要实例化且文件中没有现有实例，插入实例化代码
        if needs_instantiation and not has_existing_instance:
            lines = self._insert_instantiation(
                lines, tree, class_name, instance_var,
            )
            file_report.instantiation_added = True
            file_report.changes.append(
                f"插入实例化代码: {instance_var} = {class_name}()"
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
            logger.info("已更新文件: %s (%d 个调用点)", file_path, updated_count)

        return file_report

    # ── 上下文分析 ──────────────────────────────────────────

    def _find_existing_instance(
        self,
        source: str,
        class_name: str,
        instance_var: str,
    ) -> bool:
        """
        检查源代码中是否已有该类的实例变量。

        匹配模式：
        - ``xxx = ClassName(...)``
        - ``self.xxx = ClassName(...)``
        - 已有同名变量赋值

        Args:
            source: 源代码
            class_name: 类名
            instance_var: 期望的实例变量名

        Returns:
            True 表示已有实例
        """
        # 模式1: var = ClassName(...)
        pattern1 = re.compile(
            rf"\b\w+\s*=\s*{re.escape(class_name)}\s*\(",
        )
        # 模式2: 已有同名变量
        pattern2 = re.compile(
            rf"\b{re.escape(instance_var)}\s*=\s*",
        )

        return bool(pattern1.search(source) or pattern2.search(source))

    def _get_class_line_ranges(
        self,
        tree: Optional[ast.Module],
        class_name: str,
    ) -> list[tuple[int, int]]:
        """
        获取指定类在文件中的行范围。

        Args:
            tree: AST 树
            class_name: 类名

        Returns:
            (start_line, end_line) 列表，1-based
        """
        if tree is None:
            return []

        ranges: list[tuple[int, int]] = []
        for node in ast.walk(tree):
            if isinstance(node, ast.ClassDef) and node.name == class_name:
                end_line = node.end_lineno or node.lineno
                ranges.append((node.lineno, end_line))
        return ranges

    @staticmethod
    def _is_in_class(
        line_number: int,
        class_ranges: list[tuple[int, int]],
    ) -> bool:
        """
        判断行号是否在类的范围内。

        Args:
            line_number: 行号 (1-based)
            class_ranges: 类的行范围列表

        Returns:
            True 表示在类内部
        """
        return any(
            start <= line_number <= end
            for start, end in class_ranges
        )

    # ── 实例化代码插入 ──────────────────────────────────────

    def _insert_instantiation(
        self,
        lines: list[str],
        tree: Optional[ast.Module],
        class_name: str,
        instance_var: str,
    ) -> list[str]:
        """
        在文件中插入实例化代码。

        策略：
        1. 查找调用点所在的函数/方法体
        2. 在函数体开头插入 ``instance_var = class_name()``
        3. 如果不在函数内，在模块级别插入

        简化实现：在文件的 import 区域之后插入模块级实例化。

        Args:
            lines: 源代码行列表
            tree: AST 树
            class_name: 类名
            instance_var: 实例变量名

        Returns:
            修改后的行列表
        """
        result = list(lines)

        # 查找 import 区域结束位置
        insert_idx = self._find_import_end(result)

        # 检查是否已有实例化代码
        existing_source = "".join(result)
        instantiation_pattern = f"{instance_var} = {class_name}("
        if instantiation_pattern in existing_source:
            return result

        # 插入实例化代码
        indent = ""  # 模块级别无缩进
        instantiation_line = f"{indent}{instance_var} = {class_name}()\n"

        # 确保前面有空行
        if insert_idx > 0 and result[insert_idx - 1].strip():
            result.insert(insert_idx, "\n")
            insert_idx += 1

        result.insert(insert_idx, instantiation_line)

        logger.info(
            "在第 %d 行插入实例化代码: %s = %s()",
            insert_idx + 1,
            instance_var,
            class_name,
        )
        return result

    @staticmethod
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

    # ── 辅助方法 ────────────────────────────────────────────

    @staticmethod
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

    @staticmethod
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

    @staticmethod
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

    @staticmethod
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
