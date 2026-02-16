#!/usr/bin/env python3
"""分析attr-defined错误"""

from __future__ import annotations

import re
from collections import defaultdict
from pathlib import Path

def main() -> None:
    """主函数"""
    errors_file = Path(__file__).parent.parent / 'attr_defined_errors.txt'
    
    with open(errors_file, 'r', encoding='utf-8') as f:
        lines = f.readlines()
    
    logger.info(f"总共 {len(lines)} 个attr-defined错误")
    
    # 按文件分组
    by_file: dict[str, list[str]] = defaultdict(list)
    # 按属性名统计
    attr_counts: dict[str, int] = defaultdict(int)
    # Django Model相关
    django_attrs = {'id', 'pk', 'objects', 'DoesNotExist', 'MultipleObjectsReturned', '_meta', '_state'}
    django_errors = []
    
    for line in lines:
        # 提取文件路径
        match = re.match(r'^([^:]+):', line)
        if match:
            file_path = match.group(1)
            by_file[file_path].append(line.strip())
        
        # 提取属性名
        attr_match = re.search(r'has no attribute "(\w+)"', line)
        if attr_match:
            attr_name = attr_match.group(1)
            attr_counts[attr_name] += 1
            
            if attr_name in django_attrs:
                django_errors.append(line.strip())
    
    # 按错误数量排序文件
    sorted_files = sorted(by_file.items(), key=lambda x: len(x[1]), reverse=True)
    
    logger.info("\n" + "=" * 80)
    logger.info(f"按文件分组 (共 {len(sorted_files)} 个文件)")
    logger.info("=" * 80 + "\n")
    
    for file_path, file_errors in sorted_files[:30]:
        logger.info(f"{file_path}: {len(file_errors)} 个错误")
    
    if len(sorted_files) > 30:
        logger.info(f"... 还有 {len(sorted_files) - 30} 个文件")
    
    # 按频率排序属性
    sorted_attrs = sorted(attr_counts.items(), key=lambda x: x[1], reverse=True)
    
    logger.info("\n" + "=" * 80)
    logger.info("最常见的缺失属性 (前30个)")
    logger.info("=" * 80 + "\n")
    
    for attr_name, count in sorted_attrs[:30]:
        is_django = " (Django)" if attr_name in django_attrs else ""
        logger.info(f"{attr_name}: {count} 次{is_django}")
    
    logger.info(f"\nDjango Model动态属性错误: {len(django_errors)} 个")
    
    # 保存详细报告
    report_path = Path(__file__).parent.parent / 'attr_defined_analysis.txt'
    with open(report_path, 'w', encoding='utf-8') as f:
        f.write("=" * 80 + "\n")
        f.write("attr-defined错误详细分析\n")
        f.write("=" * 80 + "\n\n")
        f.write(f"总错误数: {len(lines)}\n")
        f.write(f"涉及文件数: {len(sorted_files)}\n")
        f.write(f"Django Model相关: {len(django_errors)}\n\n")
        
        f.write("=" * 80 + "\n")
        f.write("按文件分组\n")
        f.write("=" * 80 + "\n\n")
        
        for file_path, file_errors in sorted_files:
            f.write(f"\n{file_path} ({len(file_errors)} 个错误):\n")
            for error in file_errors:
                f.write(f"  {error}\n")
        
        f.write("\n" + "=" * 80 + "\n")
        f.write("属性名统计\n")
        f.write("=" * 80 + "\n\n")
        
        for attr_name, count in sorted_attrs:
            is_django = " (Django)" if attr_name in django_attrs else ""
            f.write(f"{attr_name}: {count}{is_django}\n")
        
        f.write("\n" + "=" * 80 + "\n")
        f.write("Django Model动态属性错误列表\n")
        f.write("=" * 80 + "\n\n")
        
        for error in django_errors:
            f.write(f"{error}\n")
    
    logger.info(f"\n详细报告已保存到: {report_path}")


if __name__ == '__main__':
    import logging
    logging.basicConfig(level=logging.INFO, format='%(message)s')
    logger = logging.getLogger(__name__)
    main()
