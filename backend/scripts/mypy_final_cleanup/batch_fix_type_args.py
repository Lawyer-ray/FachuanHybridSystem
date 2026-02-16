"""批量修复type-arg错误"""

from __future__ import annotations

import logging
from pathlib import Path

from .backup_manager import BackupManager
from .extract_type_arg_errors import extract_type_arg_errors
from .logger_config import setup_logger
from .type_args_fixer import TypeArgsFixer

logger = logging.getLogger(__name__)


def batch_fix_type_args(mypy_output_file: str) -> dict[str, int]:
    """
    批量修复type-arg错误

    Args:
        mypy_output_file: mypy输出文件路径

    Returns:
        字典: {文件路径: 修复数量}
    """
    # 提取错误
    errors = extract_type_arg_errors(mypy_output_file)
    logger.info(f"找到 {len(errors)} 个文件包含type-arg错误")
    logger.info(f"总错误数: {sum(len(lines) for lines in errors.values())}")

    # 初始化修复器
    backup_manager = BackupManager()
    fixer = TypeArgsFixer(backup_manager)

    # 批量修复
    results: dict[str, int] = {}
    total_fixed = 0

    for file_path in sorted(errors.keys()):
        logger.info(f"正在修复: {file_path}")
        try:
            fixed_count = fixer.fix_file(file_path)
            results[file_path] = fixed_count
            total_fixed += fixed_count

            if fixed_count > 0:
                logger.info(f"  ✓ 修复了 {fixed_count} 处")
            else:
                logger.warning(f"  ✗ 未修复任何错误")

        except Exception as e:
            logger.error(f"  ✗ 修复失败: {e}")
            results[file_path] = 0

    logger.info(f"\n修复完成!")
    logger.info(f"总共修复: {total_fixed} 处")
    logger.info(f"成功修复的文件: {sum(1 for count in results.values() if count > 0)}/{len(results)}")

    return results


if __name__ == "__main__":
    setup_logger()

    mypy_output = "/tmp/type_arg_errors_full.txt"
    results = batch_fix_type_args(mypy_output)

    print("\n修复结果:")
    for file_path, count in sorted(results.items()):
        status = "✓" if count > 0 else "✗"
        print(f"{status} {file_path}: {count}处")
