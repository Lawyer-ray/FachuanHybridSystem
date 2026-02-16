"""批量清理redundant-cast和unused-ignore错误"""

from __future__ import annotations

import logging
from pathlib import Path

from .backup_manager import BackupManager
from .cleanup_tool import CleanupTool
from .extract_cleanup_errors import extract_cleanup_errors, group_errors_by_file
from .logger_config import setup_logger

logger = setup_logger(__name__)


def batch_cleanup() -> None:
    """批量清理冗余注解"""
    logger.info("=" * 60)
    logger.info("开始批量清理冗余注解")
    logger.info("=" * 60)

    # 1. 提取错误
    errors = extract_cleanup_errors()
    if not errors:
        logger.info("没有发现需要清理的错误")
        return

    grouped = group_errors_by_file(errors)
    logger.info(f"需要处理 {len(grouped)} 个文件")

    # 2. 初始化工具
    backup_manager = BackupManager()
    cleanup_tool = CleanupTool(backup_manager)

    # 3. 批量修复
    total_cleaned = 0
    success_count = 0
    failed_files: list[str] = []

    for file_path, file_errors in sorted(grouped.items()):
        logger.info(f"\n处理文件: {file_path} ({len(file_errors)} 个错误)")

        try:
            cleaned = cleanup_tool.fix_file(file_path)
            if cleaned > 0:
                total_cleaned += cleaned
                success_count += 1
                logger.info(f"  ✓ 清理了 {cleaned} 处")
            else:
                logger.warning(f"  - 没有清理任何内容")
        except Exception as e:
            logger.error(f"  ✗ 处理失败: {e}")
            failed_files.append(file_path)

    # 4. 输出统计
    logger.info("\n" + "=" * 60)
    logger.info("清理完成")
    logger.info("=" * 60)
    logger.info(f"总计清理: {total_cleaned} 处")
    logger.info(f"成功文件: {success_count}/{len(grouped)}")

    if failed_files:
        logger.warning(f"\n失败文件 ({len(failed_files)}):")
        for file_path in failed_files:
            logger.warning(f"  - {file_path}")

    logger.info("\n建议运行 mypy 验证修复结果:")
    logger.info("  mypy apps/ --strict | grep -E '(redundant-cast|unused-ignore)'")


if __name__ == "__main__":
    batch_cleanup()
