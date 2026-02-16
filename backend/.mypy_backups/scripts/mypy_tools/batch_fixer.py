"""BatchFixer - 批量修复简单重复的类型错误"""

from __future__ import annotations

import ast
import logging
import shutil
from abc import ABC, abstractmethod
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .error_analyzer import ErrorRecord
    from .validation_system import FixResult

logger = logging.getLogger(__name__)


@dataclass
class FixReport:
    """修复报告数据类"""

    total_files: int
    files_modified: list[str]
    total_errors_fixed: int
    total_lines_modified: int
    success: bool
    failed_files: list[tuple[str, str]]  # (文件路径, 错误消息)


class BatchFixer(ABC):
    """批量修复简单重复的类型错误基类"""

    def __init__(self, fix_pattern: str, backend_path: Path | None = None) -> None:
        """
        初始化BatchFixer

        Args:
            fix_pattern: 修复模式名称
            backend_path: backend目录路径，默认为当前文件的父目录的父目录
        """
        self.fix_pattern = fix_pattern

        if backend_path is None:
            # 默认路径：scripts/mypy_tools -> scripts -> backend
            self.backend_path = Path(__file__).parent.parent.parent
        else:
            self.backend_path = backend_path

        self.backup_dir = self.backend_path / ".mypy_backups"
        self.backup_dir.mkdir(exist_ok=True)

        logger.info(f"BatchFixer初始化，修复模式: {fix_pattern}")

    @abstractmethod
    def can_fix(self, error: ErrorRecord) -> bool:
        """
        判断是否可以修复此错误

        Args:
            error: 错误记录

        Returns:
            是否可以修复
        """
        pass

    @abstractmethod
    def fix_file(self, file_path: str, errors: list[ErrorRecord]) -> FixResult:
        """
        修复文件中的错误

        Args:
            file_path: 文件路径
            errors: 该文件中的错误列表

        Returns:
            修复结果
        """
        pass

    def parse_ast(self, file_path: Path) -> ast.Module | None:
        """
        解析Python代码为AST

        Args:
            file_path: 文件路径

        Returns:
            AST模块节点，解析失败返回None
        """
        try:
            source_code = file_path.read_text(encoding="utf-8")
            tree = ast.parse(source_code, filename=str(file_path))
            logger.info(f"成功解析AST: {file_path}")
            return tree
        except SyntaxError as e:
            logger.error(f"语法错误，无法解析 {file_path}: {e}")
            return None
        except Exception as e:
            logger.error(f"解析AST时发生错误 {file_path}: {e}")
            return None

    def backup_file(self, file_path: str) -> Path | None:
        """
        备份原始文件

        Args:
            file_path: 文件路径（相对于backend目录）

        Returns:
            备份文件路径，备份失败返回None
        """
        try:
            source_path = self.backend_path / file_path
            if not source_path.exists():
                logger.error(f"文件不存在，无法备份: {file_path}")
                return None

            # 创建备份路径，保持目录结构
            relative_path = source_path.relative_to(self.backend_path)
            backup_path = self.backup_dir / relative_path
            backup_path.parent.mkdir(parents=True, exist_ok=True)

            # 复制文件
            shutil.copy2(source_path, backup_path)
            logger.info(f"已备份文件: {file_path} -> {backup_path}")
            return backup_path

        except Exception as e:
            logger.error(f"备份文件失败 {file_path}: {e}")
            return None

    def restore_file(self, file_path: str) -> bool:
        """
        恢复原始文件

        Args:
            file_path: 文件路径（相对于backend目录）

        Returns:
            是否恢复成功
        """
        try:
            source_path = self.backend_path / file_path
            relative_path = source_path.relative_to(self.backend_path)
            backup_path = self.backup_dir / relative_path

            if not backup_path.exists():
                logger.error(f"备份文件不存在，无法恢复: {file_path}")
                return False

            # 恢复文件
            shutil.copy2(backup_path, source_path)
            logger.info(f"已恢复文件: {file_path}")
            return True

        except Exception as e:
            logger.error(f"恢复文件失败 {file_path}: {e}")
            return False

    def fix_with_recovery(self, file_path: str, errors: list[ErrorRecord]) -> FixResult:
        """
        修复文件，失败时自动恢复

        Args:
            file_path: 文件路径
            errors: 该文件中的错误列表

        Returns:
            修复结果
        """
        from .validation_system import FixResult

        # 备份文件
        backup_path = self.backup_file(file_path)
        if backup_path is None:
            return FixResult(
                file_path=file_path,
                errors_fixed=0,
                errors_remaining=len(errors),
                fix_pattern=self.fix_pattern,
                success=False,
                error_message="备份文件失败",
            )

        try:
            # 尝试修复
            result = self.fix_file(file_path, errors)

            # 如果修复失败，恢复文件
            if not result.success:
                logger.warning(f"修复失败，恢复文件: {file_path}")
                self.restore_file(file_path)

            return result

        except Exception as e:
            logger.error(f"修复过程中发生异常: {e}")
            # 恢复文件
            self.restore_file(file_path)
            return FixResult(
                file_path=file_path,
                errors_fixed=0,
                errors_remaining=len(errors),
                fix_pattern=self.fix_pattern,
                success=False,
                error_message=str(e),
            )

    def batch_fix(self, errors_by_file: dict[str, list[ErrorRecord]]) -> FixReport:
        """
        批量修复多个文件

        Args:
            errors_by_file: 按文件分组的错误字典

        Returns:
            修复报告
        """
        total_files = len(errors_by_file)
        files_modified: list[str] = []
        total_errors_fixed = 0
        total_lines_modified = 0
        failed_files: list[tuple[str, str]] = []

        logger.info(f"开始批量修复，共 {total_files} 个文件")

        for file_path, errors in errors_by_file.items():
            # 过滤出可以修复的错误
            fixable_errors = [e for e in errors if self.can_fix(e)]

            if not fixable_errors:
                logger.info(f"跳过文件（无可修复错误）: {file_path}")
                continue

            logger.info(f"修复文件: {file_path}，共 {len(fixable_errors)} 个错误")

            # 使用错误恢复机制修复文件
            result = self.fix_with_recovery(file_path, fixable_errors)

            if result.success:
                files_modified.append(file_path)
                total_errors_fixed += result.errors_fixed
                total_lines_modified += result.errors_fixed  # 简化：假设每个错误修复1行
            else:
                failed_files.append((file_path, result.error_message or "未知错误"))

        success = len(failed_files) == 0

        report = FixReport(
            total_files=total_files,
            files_modified=files_modified,
            total_errors_fixed=total_errors_fixed,
            total_lines_modified=total_lines_modified,
            success=success,
            failed_files=failed_files,
        )

        logger.info(
            f"批量修复完成: 修改了 {len(files_modified)}/{total_files} 个文件，" f"修复了 {total_errors_fixed} 个错误"
        )

        if failed_files:
            logger.warning(f"失败的文件数: {len(failed_files)}")
            for file_path, error_msg in failed_files[:5]:  # 只记录前5个
                logger.warning(f"  失败: {file_path} - {error_msg}")

        return report

    def generate_report(self, report: FixReport) -> str:
        """
        生成修复报告文本

        Args:
            report: 修复报告数据

        Returns:
            格式化的报告文本
        """
        lines = [
            f"修复报告 - {self.fix_pattern}",
            "=" * 60,
            f"总文件数: {report.total_files}",
            f"修改的文件数: {len(report.files_modified)}",
            f"修复的错误数: {report.total_errors_fixed}",
            f"修改的行数: {report.total_lines_modified}",
            f"修复状态: {'成功' if report.success else '部分失败'}",
            "",
        ]

        if report.files_modified:
            lines.append("修改的文件:")
            for file_path in report.files_modified[:10]:  # 最多显示10个
                lines.append(f"  - {file_path}")
            if len(report.files_modified) > 10:
                lines.append(f"  ... 还有 {len(report.files_modified) - 10} 个文件")
            lines.append("")

        if report.failed_files:
            lines.append("失败的文件:")
            for file_path, error_msg in report.failed_files[:10]:  # 最多显示10个
                lines.append(f"  - {file_path}: {error_msg}")
            if len(report.failed_files) > 10:
                lines.append(f"  ... 还有 {len(report.failed_files) - 10} 个文件")
            lines.append("")

        return "\n".join(lines)

    def write_source(self, file_path: Path, tree: ast.Module) -> bool:
        """
        将AST写回源文件

        Args:
            file_path: 文件路径
            tree: AST模块节点

        Returns:
            是否写入成功
        """
        try:
            # 使用ast.unparse生成代码（Python 3.9+）
            source_code = ast.unparse(tree)
            file_path.write_text(source_code, encoding="utf-8")
            logger.info(f"已写入修复后的代码: {file_path}")
            return True
        except Exception as e:
            logger.error(f"写入源文件失败 {file_path}: {e}")
            return False
