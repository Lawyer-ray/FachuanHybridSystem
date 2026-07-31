#!/usr/bin/env python3
"""
命令行入口模块

提供合同自动编号的命令行接口。
"""

import logging
import sys

from . import convert_contract_numbering
from .utils import format_numbering_mapping

logger = logging.getLogger(__name__)


def main():
    """命令行入口"""
    logging.basicConfig(level=logging.INFO, format='%(message)s')

    if len(sys.argv) < 2:
        logger.error("用法: python -m 合同自动编号 <input_docx> [output_docx] [--format chinese|decimal]")
        sys.exit(1)

    input_path = sys.argv[1]
    output_path = None
    format_type = None

    # 解析命令行参数
    i = 2
    while i < len(sys.argv):
        if sys.argv[i] == '--format' and i + 1 < len(sys.argv):
            format_type = sys.argv[i + 1]
            i += 2
        elif output_path is None:
            output_path = sys.argv[i]
            i += 1
        else:
            i += 1

    # 执行转换
    result = convert_contract_numbering(input_path, output_path, format_type)

    if result['success']:
        logger.info("✓ 转换成功")
        logger.info("  输入: %s", result['input_path'])
        logger.info("  输出: %s", result['output_path'])
        logger.info("  格式: %s", result['format_name'])
        logger.info("  总段落数: %d", result['total_paragraphs'])
        logger.info("  一级标题数: %d", result['level0_count'])

        # 显示转换映射
        logger.info("\n=== 转换映射 ===\n")
        logger.info(format_numbering_mapping(result['numbered_paras']))
    else:
        logger.error("✗ 转换失败: %s", result['error'])
        sys.exit(1)


if __name__ == '__main__':
    main()
