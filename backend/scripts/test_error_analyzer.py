#!/usr/bin/env python3
"""测试ErrorAnalyzer和ValidationSystem的功能"""

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
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)

logger = logging.getLogger(__name__)


def test_error_analyzer() -> None:
    """测试ErrorAnalyzer功能"""
    logger.info("=" * 80)
    logger.info("测试 ErrorAnalyzer")
    logger.info("=" * 80)
    
    # 创建分析器
    analyzer = ErrorAnalyzer()
    
    # 运行mypy并获取输出
    validation = ValidationSystem()
    error_count, mypy_output = validation.run_mypy()
    
    if error_count < 0:
        logger.error("无法运行mypy检查")
        return
    
    logger.info(f"mypy检查完成，发现 {error_count} 个错误")
    
    # 解析错误
    errors = analyzer.analyze(mypy_output)
    logger.info(f"成功解析 {len(errors)} 个错误记录")
    
    # 按类型分类
    by_type = analyzer.categorize_by_type(errors)
    logger.info(f"按类型分类: {len(by_type)} 种错误类型")
    
    # 按数量排序
    sorted_types = analyzer.get_sorted_by_count(by_type)
    logger.info("\n错误类型统计 (Top 10):")
    for error_type, count in sorted_types[:10]:
        logger.info(f"  {error_type:30s} {count:5d}")
    
    # 按模块分类
    by_module = analyzer.categorize_by_module(errors)
    logger.info(f"\n按模块分类: {len(by_module)} 个模块")
    
    sorted_modules = analyzer.get_sorted_by_count(by_module)
    logger.info("\n模块错误统计 (Top 10):")
    for module, count in sorted_modules[:10]:
        logger.info(f"  {module:30s} {count:5d}")
    
    # 识别可批量修复的错误
    fixable = analyzer.identify_fixable(errors)
    logger.info(f"\n可批量修复的错误: {len(fixable)} 个")
    
    # 按严重程度统计
    by_severity: dict[str, int] = {}
    for error in errors:
        by_severity[error.severity] = by_severity.get(error.severity, 0) + 1
    
    logger.info("\n按严重程度统计:")
    for severity in ['critical', 'high', 'medium', 'low']:
        count = by_severity.get(severity, 0)
        percentage = (count / len(errors) * 100) if errors else 0
        logger.info(f"  {severity:10s} {count:5d} ({percentage:5.1f}%)")


def test_validation_system() -> None:
    """测试ValidationSystem功能"""
    logger.info("\n" + "=" * 80)
    logger.info("测试 ValidationSystem")
    logger.info("=" * 80)
    
    validation = ValidationSystem()
    
    # 测试mypy运行
    error_count, output = validation.run_mypy()
    logger.info(f"mypy检查结果: {error_count} 个错误")
    
    # 解析错误用于对比测试
    analyzer = ErrorAnalyzer()
    errors = analyzer.analyze(output)
    
    # 模拟修复前后对比（这里用相同的错误列表模拟）
    report = validation.compare_errors(errors, errors)
    logger.info(f"\n对比报告:")
    logger.info(f"  修复前错误数: {report.total_errors_before}")
    logger.info(f"  修复后错误数: {report.total_errors_after}")
    logger.info(f"  修复的错误数: {report.errors_fixed}")
    logger.info(f"  新增的错误数: {report.new_errors}")
    logger.info(f"  检测到回归: {report.regression_detected}")
    
    # 测试回归检测
    new_errors = validation.detect_regression(errors, errors)
    logger.info(f"\n回归检测: 发现 {len(new_errors)} 个新错误")


def main() -> None:
    """主函数"""
    logger.info("开始测试 ErrorAnalyzer 和 ValidationSystem")
    logger.info("")
    
    try:
        test_error_analyzer()
        test_validation_system()
        
        logger.info("\n" + "=" * 80)
        logger.info("✅ 所有测试完成")
        logger.info("=" * 80)
        
    except Exception as e:
        logger.error(f"测试过程中发生错误: {e}", exc_info=True)
        sys.exit(1)


if __name__ == '__main__':
    main()
