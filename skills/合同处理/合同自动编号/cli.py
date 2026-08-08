#!/usr/bin/env python3
"""
命令行入口模块

提供合同自动编号的命令行接口。

三种工作模式：
1. 自动模式（默认）：python -m 合同自动编号 <input.docx> [output.docx] [--format chinese|decimal]
2. 分析模式：python -m 合同自动编号 <input.docx> --analyze [--format chinese|decimal]
3. AI 映射模式：python -m 合同自动编号 <input.docx> --apply-map <map.json> [output.docx] [--format chinese|decimal]
"""

import json
import logging
import sys

from . import analyze_document, apply_numbering_map, convert_contract_numbering
from .utils import format_numbering_mapping

logger = logging.getLogger(__name__)


def main():
    """命令行入口"""
    logging.basicConfig(level=logging.INFO, format='%(message)s')

    if len(sys.argv) < 2:
        logger.error("用法:")
        logger.error("  自动模式: python -m 合同自动编号 <input_docx> [output_docx] [--format chinese|decimal]")
        logger.error("  分析模式: python -m 合同自动编号 <input_docx> --analyze [--format chinese|decimal]")
        logger.error("  映射模式: python -m 合同自动编号 <input_docx> --apply-map <map.json> [output_docx] [--format chinese|decimal]")
        sys.exit(1)

    input_path = sys.argv[1]
    output_path = None
    format_type = 'chinese'
    analyze_mode = False
    apply_map_file = None

    # 解析命令行参数
    i = 2
    while i < len(sys.argv):
        arg = sys.argv[i]
        if arg == '--analyze':
            analyze_mode = True
            i += 1
        elif arg == '--apply-map' and i + 1 < len(sys.argv):
            apply_map_file = sys.argv[i + 1]
            i += 2
        elif arg == '--format' and i + 1 < len(sys.argv):
            format_type = sys.argv[i + 1]
            i += 2
        elif output_path is None and not arg.startswith('--'):
            output_path = arg
            i += 1
        else:
            i += 1

    # 分析模式：输出段落结构 JSON
    if analyze_mode:
        result = analyze_document(input_path, format_type)
        sys.stdout.write(result)
        return

    # AI 映射模式：读取 JSON 映射，应用编号
    if apply_map_file:
        with open(apply_map_file, encoding='utf-8') as f:
            numbering_map = json.load(f)
        result = apply_numbering_map(input_path, numbering_map, output_path, format_type)
    else:
        # 自动模式
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
