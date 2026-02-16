#!/usr/bin/env python3
"""分析 core/config 模块的 mypy 错误"""
import re
from collections import defaultdict
from pathlib import Path

def analyze_errors(error_file: str) -> None:
    """分析错误文件并生成统计报告"""
    
    # 读取错误文件
    with open(error_file, 'r', encoding='utf-8') as f:
        content = f.read()
    
    # 统计错误类型
    error_types: dict[str, int] = defaultdict(int)
    file_errors: dict[str, int] = defaultdict(int)
    
    # 解析错误 - 匹配多行错误格式
    error_pattern = r'apps/core/config/([^:]+):(\d+):(\d+): error: .+?\[([^\]]+)\]'
    matches = re.findall(error_pattern, content, re.MULTILINE)
    
    for file_path, line, col, error_type in matches:
        error_types[error_type] += 1
        file_errors[file_path] += 1
    
    # 输出统计
    print("=" * 80)
    print("core/config 模块 Mypy 错误分析")
    print("=" * 80)
    print(f"\n总错误数: {len(matches)}")
    print(f"涉及文件数: {len(file_errors)}")
    
    # 按错误类型排序
    print("\n" + "=" * 80)
    print("错误类型分布 (按数量排序)")
    print("=" * 80)
    sorted_types = sorted(error_types.items(), key=lambda x: x[1], reverse=True)
    for error_type, count in sorted_types:
        print(f"{error_type:30s} : {count:4d}")
    
    # 按文件错误数排序
    print("\n" + "=" * 80)
    print("文件错误分布 (Top 15)")
    print("=" * 80)
    sorted_files = sorted(file_errors.items(), key=lambda x: x[1], reverse=True)[:15]
    for file_path, count in sorted_files:
        print(f"{file_path:50s} : {count:4d}")
    
    # 识别高优先级错误
    print("\n" + "=" * 80)
    print("高优先级错误类型")
    print("=" * 80)
    
    high_priority = {
        'assignment': '类型赋值不兼容',
        'attr-defined': '属性不存在',
        'call-arg': '函数调用参数错误',
        'no-untyped-def': '函数缺少类型注解',
        'var-annotated': '变量缺少类型注解',
        'union-attr': 'Union类型属性访问',
        'no-any-return': '返回Any类型',
    }
    
    for error_type, description in high_priority.items():
        if error_type in error_types:
            print(f"  {error_type:20s} ({description:20s}): {error_types[error_type]:4d}")
    
    # 简单错误（可批量修复）
    print("\n" + "=" * 80)
    print("简单错误（可批量修复）")
    print("=" * 80)
    
    simple_errors = {
        'type-arg': '泛型类型参数缺失',
        'no-untyped-def': '函数缺少类型注解',
        'var-annotated': '变量缺少类型注解',
    }
    
    simple_count = 0
    for error_type, description in simple_errors.items():
        if error_type in error_types:
            count = error_types[error_type]
            simple_count += count
            print(f"  {error_type:20s} ({description:20s}): {count:4d}")
    
    print(f"\n简单错误总数: {simple_count} ({simple_count/len(matches)*100:.1f}%)" if matches else "\n简单错误总数: 0")
    
    # 复杂错误
    print("\n" + "=" * 80)
    print("复杂错误（需手动修复）")
    print("=" * 80)
    
    complex_errors = {
        'assignment': '类型赋值不兼容',
        'attr-defined': '属性不存在',
        'call-arg': '函数调用参数错误',
        'union-attr': 'Union类型属性访问',
        'no-any-return': '返回Any类型',
        'arg-type': '参数类型不匹配',
        'return-value': '返回值类型不匹配',
    }
    
    complex_count = 0
    for error_type, description in complex_errors.items():
        if error_type in error_types:
            count = error_types[error_type]
            complex_count += count
            print(f"  {error_type:20s} ({description:20s}): {count:4d}")
    
    print(f"\n复杂错误总数: {complex_count} ({complex_count/len(matches)*100:.1f}%)" if matches else "\n复杂错误总数: 0")

if __name__ == '__main__':
    analyze_errors('core_config_errors.txt')
