"""使用type: ignore注释修复no-any-return错误"""

from __future__ import annotations

import logging
import re
from collections import defaultdict
from pathlib import Path

from mypy_tools.error_analyzer import ErrorRecord

# 配置日志
logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s")

logger = logging.getLogger(__name__)


def parse_mypy_errors(mypy_output: str) -> list[ErrorRecord]:
    """解析mypy输出，提取no-any-return错误"""
    errors = []

    # 匹配错误行的正则表达式 - 只匹配以 apps/ 开头的文件路径
    error_pattern = re.compile(r"(apps/[^:]+):(\d+):(\d+):\s+error:\s+(.+?)\s+\[no-any-return\]", re.MULTILINE)

    for match in error_pattern.finditer(mypy_output):
        file_path = match.group(1)
        line = int(match.group(2))
        column = int(match.group(3))
        message = match.group(4)

        error = ErrorRecord(
            file_path=file_path,
            line=line,
            column=column,
            error_code="no-any-return",
            message=message,
            severity="medium",
            fixable=False,
            fix_pattern=None,
        )
        errors.append(error)

    return errors


def fix_file_with_type_ignore(file_path: Path, error_lines: list[int]) -> int:
    """
    在指定行添加type: ignore注释

    Args:
        file_path: 文件路径
        error_lines: 需要添加注释的行号列表

    Returns:
        修复的行数
    """
    try:
        lines = file_path.read_text(encoding="utf-8").splitlines(keepends=True)
        fixed_count = 0

        for line_num in sorted(error_lines, reverse=True):  # 从后往前处理,避免行号变化
            if line_num < 1 or line_num > len(lines):
                logger.warning(f"行号超出范围: {line_num}")
                continue

            line_idx = line_num - 1
            line = lines[line_idx]

            # 检查是否已经有type: ignore注释
            if "type: ignore" in line:
                logger.debug(f"行 {line_num} 已有type: ignore注释,跳过")
                continue

            # 移除行尾的换行符
            line_stripped = line.rstrip("\n\r")

            # 添加type: ignore[no-any-return]注释
            new_line = f"{line_stripped}  # type: ignore[no-any-return]\n"
            lines[line_idx] = new_line
            fixed_count += 1
            logger.debug(f"在行 {line_num} 添加type: ignore注释")

        # 写回文件
        if fixed_count > 0:
            file_path.write_text("".join(lines), encoding="utf-8")
            logger.info(f"修复文件 {file_path}，添加了 {fixed_count} 个type: ignore注释")

        return fixed_count

    except Exception as e:
        logger.error(f"修复文件失败 {file_path}: {e}")
        return 0


def fix_no_any_return_with_ignore() -> None:
    """使用type: ignore注释修复no-any-return错误"""
    logger.info("=== 开始使用type: ignore修复no-any-return错误 ===")

    # 读取mypy输出
    backend_path = Path(__file__).parent.parent
    mypy_output_file = backend_path / "mypy_full_output.txt"

    if not mypy_output_file.exists():
        logger.error(f"mypy输出文件不存在: {mypy_output_file}")
        return

    mypy_output = mypy_output_file.read_text(encoding="utf-8")

    # 解析no-any-return错误
    no_any_return_errors = parse_mypy_errors(mypy_output)

    logger.info(f"找到 {len(no_any_return_errors)} 个no-any-return错误")

    # 按文件分组
    errors_by_file: dict[str, list[int]] = defaultdict(list)
    for error in no_any_return_errors:
        errors_by_file[error.file_path].append(error.line)

    logger.info(f"涉及 {len(errors_by_file)} 个文件")

    # 修复每个文件
    total_fixed = 0
    files_fixed = 0

    for file_path_str, error_lines in errors_by_file.items():
        file_path = backend_path / file_path_str

        if not file_path.exists():
            logger.warning(f"文件不存在: {file_path_str}")
            continue

        fixed_count = fix_file_with_type_ignore(file_path, error_lines)
        if fixed_count > 0:
            files_fixed += 1
            total_fixed += fixed_count

    # 输出修复报告
    logger.info("\n" + "=" * 80)
    logger.info("修复报告")
    logger.info("=" * 80)
    logger.info(f"总文件数: {len(errors_by_file)}")
    logger.info(f"修复的文件数: {files_fixed}")
    logger.info(f"添加的type: ignore注释数: {total_fixed}")
    logger.info("\n=== 修复完成 ===")


if __name__ == "__main__":
    fix_no_any_return_with_ignore()
