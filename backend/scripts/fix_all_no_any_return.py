#!/usr/bin/env python
"""批量修复所有no-any-return错误"""

from __future__ import annotations

import logging
from pathlib import Path

from mypy_tools.error_analyzer import ErrorAnalyzer
from mypy_tools.no_any_return_fixer import NoAnyReturnFixer
from mypy_tools.validation_system import ValidationSystem

# 配置日志
logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s")

logger = logging.getLogger(__name__)


def main() -> None:
    """主函数"""
    logger.info("=== 开始批量修复no-any-return错误 ===")

    # 初始化
    backend_path = Path(__file__).parent.parent
    analyzer = ErrorAnalyzer()
    fixer = NoAnyReturnFixer(backend_path)
    validator = ValidationSystem(backend_path)

    # 分析错误
    logger.info("步骤1: 分析no-any-return错误...")
    error_count, mypy_output = validator.run_mypy()

    if error_count < 0:
        logger.error("mypy运行失败")
        return

    logger.info(f"mypy检查完成，总错误数: {error_count}")

    # 解析错误
    all_errors = analyzer.analyze(mypy_output)
    no_any_return_errors = [e for e in all_errors if e.error_code == "no-any-return"]

    logger.info(f"no-any-return错误数: {len(no_any_return_errors)}")

    if not no_any_return_errors:
        logger.info("没有no-any-return错误需要修复")
        return

    # 按文件分组
    errors_by_file = analyzer.categorize_by_file(no_any_return_errors)

    logger.info(f"步骤2: 批量修复 {len(errors_by_file)} 个文件...")

    # 修复每个文件
    total_fixed = 0
    total_failed = 0

    for file_path, errors in errors_by_file.items():
        logger.info(f"修复文件: {file_path} ({len(errors)} 个错误)")

        result = fixer.fix_file(file_path, errors)

        if result.success:
            total_fixed += result.errors_fixed
            logger.info(f"  ✓ 成功修复 {result.errors_fixed} 个错误")
        else:
            total_failed += len(errors)
            logger.error(f"  ✗ 修复失败: {result.error_message}")

    logger.info(f"\n步骤3: 修复完成")
    logger.info(f"  成功修复: {total_fixed} 个错误")
    logger.info(f"  修复失败: {total_failed} 个错误")

    # 再次运行mypy验证
    logger.info("\n步骤4: 验证修复效果...")
    error_count_after, _ = validator.run_mypy()

    if error_count_after < 0:
        logger.error("验证失败：mypy运行失败")
        return

    logger.info(f"修复前错误数: {error_count}")
    logger.info(f"修复后错误数: {error_count_after}")
    logger.info(f"减少错误数: {error_count - error_count_after}")

    logger.info("\n=== 批量修复完成 ===")


if __name__ == "__main__":
    main()
