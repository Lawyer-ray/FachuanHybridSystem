#!/usr/bin/env python3
"""
命令行入口模块

提供文档格式转换的命令行接口。
"""

import logging
import sys
from pathlib import Path

from . import convert_documents
from .converter import check_health

logger = logging.getLogger(__name__)


def main():
    """命令行入口"""
    logging.basicConfig(level=logging.INFO, format='%(message)s')

    if len(sys.argv) < 2:
        logger.error("用法: python -m 文档格式转换 <input_doc> [input_doc2 ...] [--output-dir DIR]")
        logger.error("")
        logger.error("示例:")
        logger.error("  python -m 文档格式转换 /path/to/document.doc")
        logger.error("  python -m 文档格式转换 /path/to/*.doc --output-dir /path/to/output")
        sys.exit(1)

    # 解析参数
    input_paths = []
    output_dir = None

    i = 1
    while i < len(sys.argv):
        if sys.argv[i] == '--output-dir' and i + 1 < len(sys.argv):
            output_dir = sys.argv[i + 1]
            i += 2
        else:
            input_paths.append(sys.argv[i])
            i += 1

    # 检查健康状态
    if not check_health():
        logger.error("✗ LibreOffice 不可用，请检查服务器配置")
        sys.exit(1)

    # 执行转换
    result = convert_documents(input_paths, output_dir)

    if result['success']:
        logger.info("✓ 转换成功")
        logger.info("  输入文件数: %d", result['total_files'])
        logger.info("  转换成功数: %d", result['converted_count'])
        logger.info("  输出目录: %s", result['output_dir'])
        logger.info("  ZIP 文件: %s", result['zip_path'])
        logger.info("")
        logger.info("转换后的文件:")
        for f in result['converted_files']:
            logger.info("  - %s", Path(f).name)
    else:
        logger.error("✗ 转换失败: %s", result['error'])
        sys.exit(1)


if __name__ == '__main__':
    main()
