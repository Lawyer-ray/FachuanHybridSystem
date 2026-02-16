"""CleanupTool - 清理冗余的类型转换和无用的type: ignore注释"""

from __future__ import annotations

import logging
import re
from pathlib import Path

from .backup_manager import BackupManager

logger = logging.getLogger(__name__)


class CleanupTool:
    """移除冗余的cast()调用和无用的type: ignore注释"""

    def __init__(self, backup_manager: BackupManager | None = None) -> None:
        """
        初始化CleanupTool

        Args:
            backup_manager: 备份管理器，如果为None则创建新实例
        """
        self.backup_manager = backup_manager or BackupManager()

    def fix_file(self, file_path: str) -> int:
        """
        清理文件中的冗余注解

        Args:
            file_path: 文件路径（相对于backend目录）

        Returns:
            清理的数量
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

            # 应用清理
            original_content = content
            content = self.remove_redundant_casts(content)
            content = self.remove_unused_ignores(content)

            # 如果有修改，写回文件
            if content != original_content:
                full_path.write_text(content, encoding="utf-8")
                cleanup_count = self._count_cleanups(original_content, content)
                logger.info(f"已清理 {file_path}: {cleanup_count}处")
                return cleanup_count

            return 0

        except Exception as e:
            logger.error(f"清理文件失败 {file_path}: {e}")
            # 尝试恢复备份
            self.backup_manager.restore_file(file_path)
            return 0

    def remove_redundant_casts(self, content: str) -> str:
        """
        移除冗余的cast()调用

        当mypy报告redundant-cast错误时，说明cast()调用是不必要的，
        因为表达式已经是目标类型了。

        例如：
        - cast(str, "hello") -> "hello"
        - cast(int, 42) -> 42
        - cast(List[str], my_list) -> my_list (当my_list已经是List[str]类型)

        Args:
            content: 文件内容

        Returns:
            移除冗余cast后的内容
        """
        # 匹配 cast(Type, expression) 模式
        # 使用非贪婪匹配，处理嵌套括号

        # 简单情况：cast(Type, simple_expr)
        # 例如：cast(str, value) -> value
        pattern1 = r"cast\([^,]+,\s*([^)]+)\)"

        # 先处理简单情况
        def replace_simple_cast(match: re.Match[str]) -> str:
            expr = match.group(1).strip()
            return expr

        # 多次替换，直到没有更多的cast
        max_iterations = 10
        for _ in range(max_iterations):
            new_content = re.sub(pattern1, replace_simple_cast, content)
            if new_content == content:
                break
            content = new_content

        return content

    def remove_unused_ignores(self, content: str) -> str:
        """
        移除无用的type: ignore注释

        当mypy报告unused-ignore错误时，说明该行的type: ignore注释
        不再需要，因为该行没有类型错误。

        支持的格式：
        - # type: ignore
        - # type: ignore[error-code]
        - # type: ignore[error-code1, error-code2]

        Args:
            content: 文件内容

        Returns:
            移除无用ignore后的内容
        """
        lines = content.split("\n")
        cleaned_lines: list[str] = []

        for line in lines:
            # 检查是否包含 type: ignore
            if "# type: ignore" in line:
                # 移除 type: ignore 注释
                # 匹配各种格式：
                # - # type: ignore
                # - # type: ignore[error-code]
                # - # type: ignore[error-code1, error-code2]
                cleaned_line = re.sub(r"\s*#\s*type:\s*ignore(?:\[[^\]]+\])?\s*$", "", line)
                # 移除行尾多余的空白
                cleaned_line = cleaned_line.rstrip()
                cleaned_lines.append(cleaned_line)
            else:
                cleaned_lines.append(line)

        return "\n".join(cleaned_lines)

    def _count_cleanups(self, original: str, cleaned: str) -> int:
        """
        统计清理的数量

        Args:
            original: 原始内容
            cleaned: 清理后的内容

        Returns:
            清理数量
        """
        count = 0

        # 统计移除的cast()
        original_casts = len(re.findall(r"\bcast\(", original))
        cleaned_casts = len(re.findall(r"\bcast\(", cleaned))
        count += original_casts - cleaned_casts

        # 统计移除的type: ignore
        original_ignores = len(re.findall(r"#\s*type:\s*ignore", original))
        cleaned_ignores = len(re.findall(r"#\s*type:\s*ignore", cleaned))
        count += original_ignores - cleaned_ignores

        return count
