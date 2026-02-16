#!/usr/bin/env python3
"""
分析 mypy 最终验证的错误分布

用法:
    mypy apps/ --strict 2>&1 | python scripts/analyze_mypy_final_errors.py
"""

import sys
import re
from collections import defaultdict, Counter
from typing import Dict, List, Tuple


def parse_mypy_output(lines: List[str]) -> List[Dict[str, str]]:
    """解析 mypy 输出，提取错误信息"""
    errors = []
    # 匹配格式: file.py:123:45: error: message  [code]
    error_pattern = re.compile(
        r'^(?P<file>[^:]+):(?P<line>\d+):(?P<col>\d+):\s+'
        r'(?P<severity>\w+):\s+(?P<message>.+?)\s+\[(?P<code>[^\]]+)\]'
    )
    
    for line in lines:
        line = line.strip()
        if not line:
            continue
        match = error_pattern.match(line)
        if match:
            errors.append(match.groupdict())
    
    return errors


def analyze_errors(errors: List[Dict[str, str]]) -> None:
    """分析错误并生成统计报告"""
    
    # 按错误代码统计
    error_codes = Counter(e['code'] for e in errors)
    
    # 按文件统计
    files = Counter(e['file'] for e in errors)
    
    # 按模块统计
    modules = defaultdict(int)
    for error in errors:
        file_path = error['file']
        if file_path.startswith('apps/'):
            parts = file_path.split('/')
            if len(parts) >= 2:
                module = parts[1]
                modules[module] += 1
    
    # 按错误代码和模块统计
    module_error_codes = defaultdict(lambda: defaultdict(int))
    for error in errors:
        file_path = error['file']
        if file_path.startswith('apps/'):
            parts = file_path.split('/')
            if len(parts) >= 2:
                module = parts[1]
                module_error_codes[module][error['code']] += 1
    
    # 打印报告
    print("=" * 80)
    print("MYPY 最终验证错误分析报告")
    print("=" * 80)
    print()
    
    print(f"总错误数: {len(errors)}")
    print(f"涉及文件数: {len(files)}")
    print()
    
    # 错误代码统计
    print("-" * 80)
    print("错误代码统计 (Top 20)")
    print("-" * 80)
    for code, count in error_codes.most_common(20):
        percentage = (count / len(errors)) * 100
        print(f"{code:30s} {count:5d} ({percentage:5.1f}%)")
    print()
    
    # 模块统计
    print("-" * 80)
    print("模块错误统计")
    print("-" * 80)
    sorted_modules = sorted(modules.items(), key=lambda x: x[1], reverse=True)
    for module, count in sorted_modules:
        percentage = (count / len(errors)) * 100
        print(f"{module:30s} {count:5d} ({percentage:5.1f}%)")
    print()
    
    # 文件统计 (Top 20)
    print("-" * 80)
    print("错误最多的文件 (Top 20)")
    print("-" * 80)
    for file_path, count in files.most_common(20):
        print(f"{file_path:70s} {count:4d}")
    print()
    
    # 每个模块的主要错误类型
    print("-" * 80)
    print("各模块主要错误类型 (Top 5)")
    print("-" * 80)
    for module in sorted(modules.keys(), key=lambda m: modules[m], reverse=True)[:10]:
        print(f"\n{module} (总计: {modules[module]} 错误)")
        print("-" * 40)
        module_codes = module_error_codes[module]
        sorted_codes = sorted(module_codes.items(), key=lambda x: x[1], reverse=True)
        for code, count in sorted_codes[:5]:
            percentage = (count / modules[module]) * 100
            print(f"  {code:28s} {count:4d} ({percentage:5.1f}%)")
    print()
    
    # 错误严重程度分析
    print("-" * 80)
    print("错误严重程度分析")
    print("-" * 80)
    
    # 定义错误严重程度
    critical_errors = ['name-defined', 'attr-defined', 'call-arg']
    high_priority = ['no-untyped-def', 'no-untyped-call', 'arg-type', 'return-value']
    medium_priority = ['type-arg', 'no-any-return', 'assignment']
    
    critical_count = sum(error_codes[code] for code in critical_errors)
    high_count = sum(error_codes[code] for code in high_priority)
    medium_count = sum(error_codes[code] for code in medium_priority)
    low_count = len(errors) - critical_count - high_count - medium_count
    
    print(f"严重错误 (Critical):  {critical_count:5d} ({(critical_count/len(errors)*100):5.1f}%)")
    print(f"  - 变量未定义、属性不存在、参数错误等")
    print()
    print(f"高优先级 (High):      {high_count:5d} ({(high_count/len(errors)*100):5.1f}%)")
    print(f"  - 缺少类型注解、参数类型错误、返回值错误等")
    print()
    print(f"中优先级 (Medium):    {medium_count:5d} ({(medium_count/len(errors)*100):5.1f}%)")
    print(f"  - 泛型参数缺失、返回Any、赋值类型不匹配等")
    print()
    print(f"低优先级 (Low):       {low_count:5d} ({(low_count/len(errors)*100):5.1f}%)")
    print(f"  - 其他类型问题")
    print()
    
    # 修复建议
    print("=" * 80)
    print("修复建议")
    print("=" * 80)
    print()
    print("1. 优先修复 automation 模块 (错误最多)")
    print("2. 批量修复 no-untyped-def 错误 (添加返回类型注解)")
    print("3. 批量修复 type-arg 错误 (添加泛型参数)")
    print("4. 为 Django Model 创建 .pyi 存根文件 (解决 attr-defined 错误)")
    print("5. 修复服务初始化参数类型 (解决 call-arg 错误)")
    print()


def main():
    """主函数"""
    if sys.stdin.isatty():
        print("用法: mypy apps/ --strict 2>&1 | python scripts/analyze_mypy_final_errors.py")
        print("或者: python scripts/analyze_mypy_final_errors.py < mypy_output.txt")
        sys.exit(1)
    
    lines = sys.stdin.readlines()
    errors = parse_mypy_output(lines)
    
    if not errors:
        print("未检测到 mypy 错误！")
        sys.exit(0)
    
    analyze_errors(errors)


if __name__ == '__main__':
    main()
