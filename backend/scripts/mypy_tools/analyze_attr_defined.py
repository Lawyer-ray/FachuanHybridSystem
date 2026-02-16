#!/usr/bin/env python3
"""分析attr-defined错误并生成修复计划"""

from __future__ import annotations

import logging
import sys
from pathlib import Path

# 添加backend目录到Python路径
backend_path = Path(__file__).parent.parent
sys.path.insert(0, str(backend_path))

from scripts.mypy_tools.error_analyzer import ErrorAnalyzer
from scripts.mypy_tools.validation_system import ValidationSystem

# 配置日志
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


def main() -> None:
    """主函数"""
    logger.info("=" * 80)
    logger.info("开始分析attr-defined错误")
    logger.info("=" * 80)
    
    # 运行mypy检查
    validation_system = ValidationSystem(backend_path)
    error_count, mypy_output = validation_system.run_mypy()
    
    if error_count < 0:
        logger.error("mypy检查失败")
        return
    
    logger.info(f"mypy检查完成，共发现 {error_count} 个错误")
    
    # 分析错误
    analyzer = ErrorAnalyzer()
    errors = analyzer.analyze(mypy_output)
    
    logger.info(f"成功解析 {len(errors)} 个错误")
    
    # 按类型分类
    by_type = analyzer.categorize_by_type(errors)
    
    # 获取attr-defined错误
    attr_defined_errors = by_type.get('attr-defined', [])
    
    logger.info("=" * 80)
    logger.info(f"attr-defined错误统计: {len(attr_defined_errors)} 个")
    logger.info("=" * 80)
    
    if not attr_defined_errors:
        logger.info("没有发现attr-defined错误")
        return
    
    # 按文件分组
    by_file: dict[str, list] = {}
    for error in attr_defined_errors:
        if error.file_path not in by_file:
            by_file[error.file_path] = []
        by_file[error.file_path].append(error)
    
    # 按错误数量排序
    sorted_files = sorted(by_file.items(), key=lambda x: len(x[1]), reverse=True)
    
    logger.info(f"\n按文件分组 (共 {len(sorted_files)} 个文件):\n")
    
    for file_path, file_errors in sorted_files[:20]:  # 只显示前20个
        logger.info(f"  {file_path}: {len(file_errors)} 个错误")
        for error in file_errors[:3]:  # 每个文件只显示前3个错误
            logger.info(f"    行 {error.line}: {error.message}")
    
    if len(sorted_files) > 20:
        logger.info(f"  ... 还有 {len(sorted_files) - 20} 个文件")
    
    # 分析错误模式
    logger.info("\n" + "=" * 80)
    logger.info("错误模式分析")
    logger.info("=" * 80)
    
    # 统计常见的属性名
    attr_names: dict[str, int] = {}
    for error in attr_defined_errors:
        # 提取属性名
        import re
        match = re.search(r'has no attribute "(\w+)"', error.message)
        if match:
            attr_name = match.group(1)
            attr_names[attr_name] = attr_names.get(attr_name, 0) + 1
    
    # 按频率排序
    sorted_attrs = sorted(attr_names.items(), key=lambda x: x[1], reverse=True)
    
    logger.info(f"\n最常见的缺失属性 (前20个):\n")
    for attr_name, count in sorted_attrs[:20]:
        logger.info(f"  {attr_name}: {count} 次")
    
    # 统计Django Model相关错误
    django_model_attrs = {'id', 'pk', 'objects', 'DoesNotExist', 'MultipleObjectsReturned'}
    django_errors = [
        e for e in attr_defined_errors
        if any(attr in e.message for attr in django_model_attrs)
    ]
    
    logger.info(f"\nDjango Model动态属性错误: {len(django_errors)} 个")
    
    # 保存详细报告到文件
    report_path = backend_path / 'attr_defined_analysis.txt'
    with open(report_path, 'w', encoding='utf-8') as f:
        f.write("=" * 80 + "\n")
        f.write(f"attr-defined错误详细报告\n")
        f.write("=" * 80 + "\n\n")
        f.write(f"总错误数: {len(attr_defined_errors)}\n")
        f.write(f"涉及文件数: {len(sorted_files)}\n")
        f.write(f"Django Model相关: {len(django_errors)}\n\n")
        
        f.write("=" * 80 + "\n")
        f.write("按文件分组\n")
        f.write("=" * 80 + "\n\n")
        
        for file_path, file_errors in sorted_files:
            f.write(f"\n{file_path} ({len(file_errors)} 个错误):\n")
            for error in file_errors:
                f.write(f"  行 {error.line}:{error.column} - {error.message}\n")
        
        f.write("\n" + "=" * 80 + "\n")
        f.write("属性名统计\n")
        f.write("=" * 80 + "\n\n")
        
        for attr_name, count in sorted_attrs:
            f.write(f"{attr_name}: {count}\n")
    
    logger.info(f"\n详细报告已保存到: {report_path}")
    
    logger.info("\n" + "=" * 80)
    logger.info("分析完成")
    logger.info("=" * 80)


if __name__ == '__main__':
    main()
