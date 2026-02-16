"""
Service层架构违规扫描器

检测Service层代码中的违规模式：
- 跨模块Model导入: ``from apps.<other_module>.models import ...``
- @staticmethod 装饰器滥用

仅扫描 services/ 目录下的文件。
"""
from __future__ import annotations

import ast
import re
from pathlib import Path
from typing import Optional

from .logging_config import get_logger
from .models import ServiceViolation, Violation
from .scanner import ViolationScanner

logger = get_logger("service_scanner")

# 匹配 from apps.<module>.models import ... 的正则
_CROSS_MODULE_IMPORT_RE: re.Pattern[str] = re.compile(
    r"^apps\.([a-zA-Z_][a-zA-Z0-9_]*)\.models"
)

# 工具类名称后缀，这些类中使用 @staticmethod 是合理的
_UTILITY_CLASS_SUFFIXES: tuple[str, ...] = (
    "Utils",
    "Util",
    "Helper",
    "Helpers",
    "Tool",
    "Tools",
    "Mixin",
    "Detection",
)


class ServiceLayerScanner(ViolationScanner):
    """
    Service层架构违规扫描器

    扫描 services/ 目录下的Python文件，检测：
    1. 跨模块Model导入 — ``from apps.<other_module>.models import ...``
       同模块导入（如 contracts/services 导入 contracts/models）不算违规。
    2. @staticmethod 装饰器 — Service类中的静态方法应转为实例方法。
    """

    # ── public API override ─────────────────────────────────

    def scan_directory(self, root: Path) -> list[Violation]:
        """
        扫描目录，仅处理 services/ 子目录下的文件。

        Args:
            root: 要扫描的根目录

        Returns:
            Service层违规列表
        """
        root = Path(root)
        if not root.is_dir():
            logger.warning("Path is not a directory, skipping: %s", root)
            return []

        violations: list[Violation] = []
        py_files = self._collect_python_files(root)
        service_files = [f for f in py_files if self._is_service_file(f)]
        logger.info(
            "Found %d Service layer Python files (out of %d total) under %s",
            len(service_files),
            len(py_files),
            root,
        )

        for py_file in service_files:
            file_violations = self.scan_file(py_file)
            violations.extend(file_violations)

        logger.info(
            "Service layer scan complete: %d violation(s) in %d file(s)",
            len(violations),
            len(service_files),
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
        对单个文件的AST执行Service层违规检测。

        检测模式：
        1. 跨模块Model导入 (``from apps.<other>.models import ...``)
        2. @staticmethod 装饰器

        Args:
            tree: 已解析的AST模块节点
            source: 原始源代码文本
            file_path: 文件路径

        Returns:
            检测到的ServiceViolation列表
        """
        violations: list[Violation] = []
        current_module = self._extract_module_name(file_path)

        # 检测跨模块Model导入
        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom):
                violation = self._check_cross_module_import(
                    node, source, file_path, current_module,
                )
                if violation is not None:
                    violations.append(violation)

        # 检测 @staticmethod 装饰器
        for node in ast.walk(tree):
            if isinstance(node, ast.ClassDef):
                class_violations = self._check_static_methods(
                    node, source, file_path,
                )
                violations.extend(class_violations)

        if violations:
            logger.info(
                "Found %d Service violation(s) in %s",
                len(violations),
                file_path,
            )
        return violations

    # ── cross-module import detection ───────────────────────

    def _check_cross_module_import(
        self,
        node: ast.ImportFrom,
        source: str,
        file_path: Path,
        current_module: Optional[str],
    ) -> Optional[ServiceViolation]:
        """
        检查 ImportFrom 节点是否为跨模块Model导入。

        匹配 ``from apps.<module>.models import ...`` 模式，
        当 ``<module>`` 与当前文件所属模块不同时视为违规。

        Args:
            node: ast.ImportFrom 节点
            source: 源代码文本
            file_path: 文件路径
            current_module: 当前文件所属的apps子模块名

        Returns:
            ServiceViolation 或 None
        """
        if node.module is None:
            return None

        match = _CROSS_MODULE_IMPORT_RE.match(node.module)
        if match is None:
            return None

        imported_app_module: str = match.group(1)

        # 同模块导入不算违规
        if current_module is not None and imported_app_module == current_module:
            return None

        # 收集导入的名称
        imported_names = ", ".join(
            alias.name for alias in (node.names or [])
        )
        line_number: int = node.lineno
        code_snippet = self._get_source_line(source, line_number)

        return ServiceViolation(
            file_path=str(file_path),
            line_number=line_number,
            code_snippet=code_snippet,
            violation_type="service_cross_module_import",
            severity="high",
            description=(
                f"Service层跨模块Model导入: "
                f"from {node.module} import {imported_names}"
            ),
            violation_subtype="cross_module_import",
            imported_model=imported_names if imported_names else None,
        )

    # ── staticmethod detection ──────────────────────────────

    def _check_static_methods(
        self,
        class_node: ast.ClassDef,
        source: str,
        file_path: Path,
    ) -> list[ServiceViolation]:
        """
        检查类中的 @staticmethod 装饰器。

        遍历类体中的函数定义，检查是否有 ``@staticmethod`` 装饰器。
        跳过工具类（类名以 Utils, Helper, Tool 等结尾），
        这些类中使用 @staticmethod 是合理的。

        Args:
            class_node: ast.ClassDef 节点
            source: 源代码文本
            file_path: 文件路径

        Returns:
            检测到的ServiceViolation列表
        """
        violations: list[ServiceViolation] = []

        # 跳过工具类
        if class_node.name.endswith(_UTILITY_CLASS_SUFFIXES):
            return violations

        for node in class_node.body:
            if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                continue

            if not self._has_staticmethod_decorator(node):
                continue

            line_number: int = node.lineno
            code_snippet = self._get_source_line(source, line_number)

            violation = ServiceViolation(
                file_path=str(file_path),
                line_number=line_number,
                code_snippet=code_snippet,
                violation_type="service_static_method_abuse",
                severity="medium",
                description=(
                    f"Service类 {class_node.name} 中使用@staticmethod: "
                    f"{node.name}()"
                ),
                violation_subtype="static_method_abuse",
                method_name=node.name,
            )
            violations.append(violation)

        return violations

    @staticmethod
    def _has_staticmethod_decorator(
        func_node: ast.FunctionDef | ast.AsyncFunctionDef,
    ) -> bool:
        """
        判断函数是否有 @staticmethod 装饰器。

        Args:
            func_node: 函数定义节点

        Returns:
            True 表示有 @staticmethod 装饰器
        """
        for decorator in func_node.decorator_list:
            if isinstance(decorator, ast.Name) and decorator.id == "staticmethod":
                return True
        return False

    # ── module extraction ───────────────────────────────────

    @staticmethod
    def _extract_module_name(file_path: Path) -> Optional[str]:
        """
        从文件路径中提取所属的apps子模块名。

        在路径中查找 ``apps`` 目录，返回其下一级目录名。
        例如: ``backend/apps/contracts/services/foo.py`` → ``"contracts"``

        Args:
            file_path: 文件路径

        Returns:
            模块名，无法确定时返回None
        """
        parts = file_path.parts
        for i, part in enumerate(parts):
            if part == "apps" and i + 1 < len(parts):
                return parts[i + 1]
        return None

    # ── path filtering ──────────────────────────────────────

    @staticmethod
    def _is_service_file(file_path: Path) -> bool:
        """
        判断文件是否位于 services/ 目录下。

        Args:
            file_path: 文件路径

        Returns:
            True 表示该文件在 services/ 目录中
        """
        return "services" in file_path.parts
