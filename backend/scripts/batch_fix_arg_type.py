#!/usr/bin/env python3
"""批量修复 arg-type 错误"""

from __future__ import annotations

import logging
import sys
from pathlib import Path

# 添加项目根目录到 Python 路径
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from scripts.mypy_tools.arg_type_fixer import ArgTypeFixer

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)


def main() -> None:
    """主函数"""
    logger.info("开始批量修复 arg-type 错误...")

    fixer = ArgTypeFixer()

    # 读取错误报告
    report_file = project_root / "arg_type_errors_report.txt"
    if not report_file.exists():
        logger.error(f"错误报告文件不存在: {report_file}")
        logger.info("请先运行 analyze_arg_type.py 生成错误报告")
        return

    # 执行批量修复
    result = fixer.batch_fix_from_report(report_file)

    # 输出结果
    logger.info(f"\n修复完成:")
    logger.info(f"  成功修复: {result['fixed_count']} 个")
    logger.info(f"  跳过: {result['skipped_count']} 个")
    logger.info(f"  失败: {result['failed_count']} 个")

    if result["failed_errors"]:
        logger.warning(f"\n以下错误修复失败:")
        for error in result["failed_errors"]:
            logger.warning(f"  {error}")


if __name__ == "__main__":
    main()
