#!/usr/bin/env python3
"""分析当前mypy错误的脚本"""

from __future__ import annotations

import logging
import sys
from pathlib import Path

# 添加scripts目录到路径
sys.path.insert(0, str(Path(__file__).parent))

from mypy_tools import ErrorAnalyzer, ValidationSystem

# 配置日志
logging.basicConfig(
    level=logging.INFO,
    format='%(levelname)s - %(message)s'
)

logger = logging.getLogger(__name__)


def main() -> None:
    """主函数"""
    logger.info("开始分析当前mypy错误...")
    
    # 创建工具实例
    analyzer = ErrorAnalyzer()
    validation = ValidationSystem()
    
    # 运行mypy检查
    error_count, mypy_output = validation.run_mypy()
    
    if error_count < 0:
        logger.error("无法运行mypy检查")
        sys.exit(1)
    
    logger.info(f"mypy检查完成，发现 {error_count} 个错误")
    logger.info("")
    
    # 解析错误
    errors = analyzer.analyze(mypy_output)
    logger.info(f"成功解析 {len(errors)} 个错误记录")
    logger.info("")
    
    # 按类型分类并排序
    by_type = analyzer.categorize_by_type(errors)
    sorted_types = analyzer.get_sorted_by_count(by_type)
    
    logger.info("=" * 80)
    logger.info("错误类型统计 (Top 15)")
    logger.info("=" * 80)
    for error_type, count in sorted_types[:15]:
        percentage = (count / len(errors) * 100) if errors else 0
        logger.info(f"{error_type:35s} {count:5d} ({percentage:5.1f}%)")
    logger.info("")
    
    # 按模块分类并排序
    by_module = analyzer.categorize_by_module(errors)
    sorted_modules = analyzer.get_sorted_by_count(by_module)
    
    logger.info("=" * 80)
    logger.info("模块错误统计 (Top 10)")
    logger.info("=" * 80)
    for module, count in sorted_modules[:10]:
        percentage = (count / len(errors) * 100) if errors else 0
        logger.info(f"{module:30s} {count:5d} ({percentage:5.1f}%)")
    logger.info("")
    
    # 按严重程度统计
    by_severity: dict[str, int] = {}
    for error in errors:
        by_severity[error.severity] = by_severity.get(error.severity, 0) + 1
    
    logger.info("=" * 80)
    logger.info("按严重程度统计")
    logger.info("=" * 80)
    for severity in ['critical', 'high', 'medium', 'low']:
        count = by_severity.get(severity, 0)
        percentage = (count / len(errors) * 100) if errors else 0
        logger.info(f"{severity:10s} {count:5d} ({percentage:5.1f}%)")
    logger.info("")
    
    # 识别可批量修复的错误
    fixable = analyzer.identify_fixable(errors)
    logger.info("=" * 80)
    logger.info(f"可批量修复的错误: {len(fixable)} 个")
    logger.info("=" * 80)
    
    # 按修复模式分组
    by_pattern: dict[str, int] = {}
    for error in fixable:
        if error.fix_pattern:
            by_pattern[error.fix_pattern] = by_pattern.get(error.fix_pattern, 0) + 1
    
    for pattern, count in sorted(by_pattern.items(), key=lambda x: x[1], reverse=True):
        logger.info(f"{pattern:30s} {count:5d}")
    
    logger.info("")
    logger.info("=" * 80)
    logger.info("分析完成")
    logger.info("=" * 80)


if __name__ == '__main__':
    main()
