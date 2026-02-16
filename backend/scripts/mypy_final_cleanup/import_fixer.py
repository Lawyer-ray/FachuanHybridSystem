"""ImportFixer - 自动添加缺失的导入"""

from __future__ import annotations

import ast
import logging
import re
from pathlib import Path
from typing import Any

from .backup_manager import BackupManager

logger = logging.getLogger(__name__)


class ImportFixer:
    """自动检测并添加缺失的typing模块和外部库导入"""

    # typing模块中常用的类型
    TYPING_TYPES = {
        "Any",
        "Optional",
        "Union",
        "List",
        "Dict",
        "Set",
        "Tuple",
        "Callable",
        "Iterable",
        "Iterator",
        "Sequence",
        "Mapping",
        "Type",
        "TypeVar",
        "Generic",
        "Protocol",
        "Literal",
        "Final",
        "ClassVar",
        "cast",
        "overload",
        "TYPE_CHECKING",
    }

    # collections.abc中的类型
    COLLECTIONS_ABC_TYPES = {
        "Iterable",
        "Iterator",
        "Sequence",
        "Mapping",
        "MutableMapping",
        "Set",
        "MutableSet",
        "Callable",
    }

    def __init__(self, backup_manager: BackupManager | None = None) -> None:
        """
        初始化ImportFixer

        Args:
            backup_manager: 备份管理器，如果为None则创建新实例
        """
        self.backup_manager = backup_manager or BackupManager()

    def fix_file(self, file_path: str) -> int:
        """
        修复文件中的name-defined错误

        Args:
            file_path: 文件路径（相对于backend目录）

        Returns:
            修复的错误数量
        """
        try:
            # 备份文件
            backup_path = self.backup_manager.backup_file(file_path)
            if backup_path is None:
                logger.error(f"无法备份文件: {file_path}")
                return 0

            # 读取文件内容
            full_path = self.backup_manager.backend_path / file_path
            content = full_path.read_text(encoding="utf-8")

            # 检测缺失的导入
            missing_imports = self.detect_missing_imports(content)

            if not missing_imports:
                return 0

            # 添加导入
            original_content = content
            content = self.add_imports(content, missing_imports)

            # 如果有修改，写回文件
            if content != original_content:
                full_path.write_text(content, encoding="utf-8")
                fixes_count = len(missing_imports)
                logger.info(f"已修复 {file_path}: 添加了 {fixes_count} 个导入")
                return fixes_count

            return 0

        except Exception as e:
            logger.error(f"修复文件失败 {file_path}: {e}")
            # 尝试恢复备份
            self.backup_manager.restore_file(file_path)
            return 0

    def detect_missing_imports(self, content: str) -> set[str]:
        """
        检测文件中使用但未导入的类型

        Args:
            content: 文件内容

        Returns:
            缺失的导入集合
        """
        # 获取已有的导入
        existing_imports = self._get_existing_imports(content)

        # 检测使用的类型
        used_types = self._detect_used_types(content)

        # 计算缺失的导入
        missing = set()

        for type_name in used_types:
            if type_name in self.TYPING_TYPES and type_name not in existing_imports:
                missing.add(type_name)

        return missing

    def add_imports(self, content: str, imports: set[str]) -> str:
        """
        添加缺失的导入到文件中

        Args:
            content: 文件内容
            imports: 需要添加的导入集合

        Returns:
            添加导入后的内容
        """
        if not imports:
            return content

        lines = content.split("\n")

        # 查找现有的typing导入
        typing_import_info = self._find_typing_import(lines)

        if typing_import_info is not None:
            # 更新现有的typing导入
            return self._update_existing_import(lines, typing_import_info, imports)
        else:
            # 添加新的typing导入
            return self._add_new_import(lines, imports)

    def _get_existing_imports(self, content: str) -> set[str]:
        """
        获取文件中已有的导入

        Args:
            content: 文件内容

        Returns:
            已有的导入集合
        """
        existing: set[str] = set()

        try:
            tree = ast.parse(content)

            for node in ast.walk(tree):
                # from typing import ...
                if isinstance(node, ast.ImportFrom):
                    if node.module == "typing":
                        for alias in node.names:
                            if alias.name != "*":
                                existing.add(alias.name)

                # import typing
                elif isinstance(node, ast.Import):
                    for alias in node.names:
                        if alias.name == "typing":
                            # 如果是 import typing，则认为所有typing类型都已导入
                            existing.update(self.TYPING_TYPES)

        except SyntaxError:
            # 如果AST解析失败，使用正则表达式
            logger.warning("AST解析失败，使用正则表达式检测导入")
            existing = self._get_existing_imports_regex(content)

        return existing

    def _get_existing_imports_regex(self, content: str) -> set[str]:
        """
        使用正则表达式获取已有的导入（备用方法）

        Args:
            content: 文件内容

        Returns:
            已有的导入集合
        """
        existing: set[str] = set()

        # 匹配 from typing import ...
        pattern = r"from\s+typing\s+import\s+(.+?)(?:\n|$)"
        matches = re.finditer(pattern, content, re.MULTILINE)

        for match in matches:
            import_part = match.group(1)
            # 处理括号形式的导入
            import_part = import_part.replace("(", "").replace(")", "")
            # 分割导入项
            for item in import_part.split(","):
                item = item.strip()
                if item and item != "...":
                    existing.add(item)

        return existing

    def _detect_used_types(self, content: str) -> set[str]:
        """
        检测文件中使用的类型

        Args:
            content: 文件内容

        Returns:
            使用的类型集合
        """
        used: set[str] = set()

        # 简单方法：查找所有大写字母开头的标识符，检查是否在TYPING_TYPES中
        # 匹配所有可能的类型名称
        pattern = r"\b([A-Z][a-zA-Z0-9_]*)\b"
        matches = re.finditer(pattern, content)

        for match in matches:
            type_name = match.group(1)
            if type_name in self.TYPING_TYPES:
                used.add(type_name)

        return used

    def _find_typing_import(self, lines: list[str]) -> tuple[int, int, set[str]] | None:
        """
        查找现有的typing导入

        Args:
            lines: 文件行列表

        Returns:
            (起始行索引, 结束行索引, 已有导入集合) 或 None
        """
        for idx, line in enumerate(lines):
            if line.strip().startswith("from typing import"):
                # 找到typing导入
                start_idx = idx
                end_idx = idx

                # 检查是否是多行导入
                if "(" in line:
                    while end_idx < len(lines) and ")" not in lines[end_idx]:
                        end_idx += 1

                # 提取已有的导入
                import_lines = lines[start_idx : end_idx + 1]
                import_text = " ".join(import_lines)
                import_part = import_text.split("import", 1)[1]
                import_part = import_part.replace("(", "").replace(")", "").strip()

                existing: set[str] = set()
                for item in import_part.split(","):
                    item = item.strip()
                    if item:
                        existing.add(item)

                return (start_idx, end_idx, existing)

        return None

    def _update_existing_import(
        self, lines: list[str], import_info: tuple[int, int, set[str]], new_imports: set[str]
    ) -> str:
        """
        更新现有的typing导入

        Args:
            lines: 文件行列表
            import_info: (起始行索引, 结束行索引, 已有导入集合)
            new_imports: 需要添加的导入集合

        Returns:
            更新后的文件内容
        """
        start_idx, end_idx, existing = import_info

        # 合并导入并排序
        all_imports = sorted(list(existing | new_imports))

        # 生成新的导入语句
        new_import_line = f"from typing import {', '.join(all_imports)}"

        # 替换旧的导入行
        lines[start_idx : end_idx + 1] = [new_import_line]

        return "\n".join(lines)

    def _add_new_import(self, lines: list[str], imports: set[str]) -> str:
        """
        添加新的typing导入

        Args:
            lines: 文件行列表
            imports: 需要添加的导入集合

        Returns:
            添加导入后的文件内容
        """
        # 找到合适的插入位置
        insert_idx = self._find_import_insert_position(lines)

        # 生成新的导入语句
        sorted_imports = sorted(list(imports))
        new_import_line = f"from typing import {', '.join(sorted_imports)}"

        # 插入新的导入
        lines.insert(insert_idx, new_import_line)

        return "\n".join(lines)

    def _find_import_insert_position(self, lines: list[str]) -> int:
        """
        找到导入语句的插入位置

        Args:
            lines: 文件行列表

        Returns:
            插入位置的行索引
        """
        # 在from __future__ import之后，其他导入之前
        insert_idx = 0
        found_future_import = False
        found_other_import = False

        for idx, line in enumerate(lines):
            stripped = line.strip()

            # 跳过空行和注释
            if not stripped or stripped.startswith("#"):
                continue

            # from __future__ import
            if stripped.startswith("from __future__ import"):
                found_future_import = True
                insert_idx = idx + 1
                continue

            # 其他导入语句
            if stripped.startswith("import ") or stripped.startswith("from "):
                if not found_other_import:
                    found_other_import = True
                    if not found_future_import:
                        insert_idx = idx
                        break
            else:
                # 遇到非导入语句，停止
                if found_other_import or found_future_import:
                    break

        return insert_idx
