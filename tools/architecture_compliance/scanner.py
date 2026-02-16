"""
架构违规扫描器基类

提供基于Python AST的代码扫描基础设施，子类实现具体的违规检测逻辑。
"""

from __future__ import annotations

import ast
from abc import ABC, abstractmethod
from pathlib import Path
from typing import Optional

from .logging_config import get_logger
from .models import Violation

logger = get_logger("scanner")

# 默认排除的目录名
_DEFAULT_EXCLUDE_DIRS: frozenset[str] = frozenset(
    {
        "__pycache__",
        ".git",
        ".tox",
        ".mypy_cache",
        ".pytest_cache",
        "node_modules",
        "migrations",
        "venv",
        ".venv",
    }
)


class ViolationScanner(ABC):
    """
    架构违规扫描器基类

    使用Python AST解析源文件，遍历目录树，过滤.py文件，
    并将具体的违规检测逻辑委托给子类实现。

    子类需要实现:
        - ``_scan_file_ast`` : 对单个文件的AST执行违规检测
    """

    def __init__(
        self,
        exclude_dirs: Optional[frozenset[str]] = None,
    ) -> None:
        self._exclude_dirs = exclude_dirs if exclude_dirs is not None else _DEFAULT_EXCLUDE_DIRS

    # ── public API ──────────────────────────────────────────

    def scan_directory(self, root: Path) -> list[Violation]:
        """
        扫描目录下所有Python文件，收集违规。

        Args:
            root: 要扫描的根目录

        Returns:
            所有检测到的违规列表
        """
        root = Path(root)
        if not root.is_dir():
            logger.warning("Path is not a directory, skipping: %s", root)
            return []

        violations: list[Violation] = []
        py_files = self._collect_python_files(root)
        logger.info("Found %d Python files under %s", len(py_files), root)

        for py_file in py_files:
            file_violations = self.scan_file(py_file)
            violations.extend(file_violations)

        logger.info(
            "Scan complete: %d violation(s) in %d file(s)",
            len(violations),
            len(py_files),
        )
        return violations

    def scan_file(self, file_path: Path) -> list[Violation]:
        """
        扫描单个Python文件。

        解析AST后委托给子类的 ``_scan_file_ast`` 方法。
        解析失败时记录警告并返回空列表。

        Args:
            file_path: Python源文件路径

        Returns:
            该文件中检测到的违规列表
        """
        file_path = Path(file_path)
        source = self._read_source(file_path)
        if source is None:
            return []

        tree = self._parse_ast(source, file_path)
        if tree is None:
            return []

        return self._scan_file_ast(tree, source, file_path)

    # ── abstract / template methods ─────────────────────────

    @abstractmethod
    def _scan_file_ast(
        self,
        tree: ast.Module,
        source: str,
        file_path: Path,
    ) -> list[Violation]:
        """
        对单个文件的AST执行违规检测（子类实现）。

        Args:
            tree: 已解析的AST模块节点
            source: 原始源代码文本
            file_path: 文件路径

        Returns:
            检测到的违规列表
        """
        ...

    # ── file traversal ──────────────────────────────────────

    def _collect_python_files(self, root: Path) -> list[Path]:
        """
        递归收集目录下所有.py文件，排除指定目录。

        Args:
            root: 根目录

        Returns:
            排序后的.py文件路径列表
        """
        py_files: list[Path] = []
        for path in sorted(root.rglob("*.py")):
            if self._should_exclude(path):
                continue
            py_files.append(path)
        return py_files

    def _should_exclude(self, path: Path) -> bool:
        """
        判断路径是否应被排除。

        如果路径的任一父目录名在排除集合中，则排除该文件。

        Args:
            path: 文件路径

        Returns:
            True表示应排除
        """
        return any(part in self._exclude_dirs for part in path.parts)

    # ── AST parsing ─────────────────────────────────────────

    def _read_source(self, file_path: Path) -> Optional[str]:
        """
        读取源文件内容。

        Args:
            file_path: 文件路径

        Returns:
            源代码文本，读取失败时返回None
        """
        try:
            return file_path.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError) as exc:
            logger.warning("Cannot read file %s: %s", file_path, exc)
            return None

    def _parse_ast(self, source: str, file_path: Path) -> Optional[ast.Module]:
        """
        将源代码解析为AST。

        Args:
            source: 源代码文本
            file_path: 文件路径（用于错误消息）

        Returns:
            AST模块节点，解析失败时返回None
        """
        try:
            return ast.parse(source, filename=str(file_path))
        except SyntaxError as exc:
            logger.warning(
                "Syntax error in %s (line %s): %s",
                file_path,
                exc.lineno,
                exc.msg,
            )
            return None

    # ── source helpers ──────────────────────────────────────

    @staticmethod
    def _get_source_line(source: str, line_number: int) -> str:
        """
        从源代码中提取指定行。

        Args:
            source: 完整源代码
            line_number: 行号（1-based）

        Returns:
            该行文本（去除首尾空白），行号无效时返回空字符串
        """
        lines = source.splitlines()
        if 1 <= line_number <= len(lines):
            return lines[line_number - 1].strip()
        return ""
