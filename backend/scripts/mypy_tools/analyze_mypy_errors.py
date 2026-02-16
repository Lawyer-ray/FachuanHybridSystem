#!/usr/bin/env python3
"""
分析 mypy 错误统计

按模块和错误类型统计 mypy 错误，生成详细的分析报告。

用法:
    # 从 stdin 读取 mypy 输出
    mypy apps/ --strict 2>&1 | python scripts/analyze_mypy_errors.py
    
    # 从文件读取
    python scripts/analyze_mypy_errors.py < mypy_output.txt
    
    # 直接运行（会自动执行 mypy）
    python scripts/analyze_mypy_errors.py --run
"""

import sys
import re
import subprocess
from collections import defaultdict, Counter
from pathlib import Path
from typing import Any


def run_mypy() -> str:
    """运行 mypy 并返回输出"""
    backend_path = Path(__file__).parent.parent
    result = subprocess.run(
        ['mypy', 'apps/', '--strict'],
        capture_output=True,
        text=True,
        cwd=backend_path
    )
    return result.stdout + result.stderr


def parse_mypy_output(lines: list[str]) -> list[dict[str, str]]:
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


def get_module_from_file(file_path: str) -> str:
    """从文件路径提取模块名"""
    if file_path.startswith('apps/'):
        parts = file_path.split('/')
        if len(parts) >= 2:
            return parts[1]
    return 'other'


def analyze_by_module(errors: list[dict[str, str]]) -> dict[str, int]:
    """按模块统计错误数"""
    modules: dict[str, int] = defaultdict(int)
    for error in errors:
        module = get_module_from_file(error['file'])
        modules[module] += 1
    return dict(modules)


def analyze_by_error_type(errors: list[dict[str, str]]) -> dict[str, int]:
    """按错误类型统计错误数"""
    error_types = Counter(e['code'] for e in errors)
    return dict(error_types)


def analyze_by_module_and_type(errors: list[dict[str, str]]) -> dict[str, dict[str, int]]:
    """按模块和错误类型统计"""
    module_types: dict[str, dict[str, int]] = defaultdict(lambda: defaultdict(int))
    for error in errors:
        module = get_module_from_file(error['file'])
        module_types[module][error['code']] += 1
    return {k: dict(v) for k, v in module_types.items()}


def analyze_by_file(errors: list[dict[str, str]]) -> dict[str, int]:
    """按文件统计错误数"""
    files = Counter(e['file'] for e in errors)
    return dict(files)


def print_report(errors: list[dict[str, str]]) -> None:
    """打印分析报告"""
    if not errors:
        print("✅ 未检测到 mypy 错误！")
        return
    
    total = len(errors)
    modules = analyze_by_module(errors)
    error_types = analyze_by_error_type(errors)
    module_types = analyze_by_module_and_type(errors)
    files = analyze_by_file(errors)
    
    print("=" * 80)
    print("MYPY 错误统计分析报告")
    print("=" * 80)
    print()
    print(f"总错误数: {total}")
    print(f"涉及文件数: {len(files)}")
    print(f"涉及模块数: {len(modules)}")
    print()
    
    # 按模块统计
    print("-" * 80)
    print("按模块统计错误数")
    print("-" * 80)
    sorted_modules = sorted(modules.items(), key=lambda x: x[1], reverse=True)
    for module, count in sorted_modules:
        percentage = (count / total) * 100
        bar = '█' * int(percentage / 2)
        print(f"{module:30s} {count:5d} ({percentage:5.1f}%) {bar}")
    print()
    
    # 按错误类型统计
    print("-" * 80)
    print("按错误类型统计 (Top 20)")
    print("-" * 80)
    sorted_types = sorted(error_types.items(), key=lambda x: x[1], reverse=True)[:20]
    for error_type, count in sorted_types:
        percentage = (count / total) * 100
        bar = '█' * int(percentage / 2)
        print(f"{error_type:35s} {count:5d} ({percentage:5.1f}%) {bar}")
    print()
    
    # 各模块的主要错误类型
    print("-" * 80)
    print("各模块主要错误类型 (Top 5)")
    print("-" * 80)
    for module in sorted(modules.keys(), key=lambda m: modules[m], reverse=True):
        print(f"\n{module} (总计: {modules[module]} 错误)")
        print("-" * 40)
        module_codes = module_types[module]
        sorted_codes = sorted(module_codes.items(), key=lambda x: x[1], reverse=True)[:5]
        for code, count in sorted_codes:
            percentage = (count / modules[module]) * 100
            print(f"  {code:33s} {count:4d} ({percentage:5.1f}%)")
    print()
    
    # 错误最多的文件
    print("-" * 80)
    print("错误最多的文件 (Top 20)")
    print("-" * 80)
    sorted_files = sorted(files.items(), key=lambda x: x[1], reverse=True)[:20]
    for file_path, count in sorted_files:
        print(f"{file_path:70s} {count:4d}")
    print()
    
    # 错误严重程度分析
    print("-" * 80)
    print("错误严重程度分析")
    print("-" * 80)
    
    critical_errors = ['name-defined', 'attr-defined', 'call-arg']
    high_priority = ['no-untyped-def', 'no-untyped-call', 'arg-type', 'return-value']
    medium_priority = ['type-arg', 'no-any-return', 'assignment']
    
    critical_count = sum(error_types.get(code, 0) for code in critical_errors)
    high_count = sum(error_types.get(code, 0) for code in high_priority)
    medium_count = sum(error_types.get(code, 0) for code in medium_priority)
    low_count = total - critical_count - high_count - medium_count
    
    print(f"严重错误 (Critical):  {critical_count:5d} ({(critical_count/total*100):5.1f}%)")
    print(f"  - 变量未定义、属性不存在、参数错误等")
    print()
    print(f"高优先级 (High):      {high_count:5d} ({(high_count/total*100):5.1f}%)")
    print(f"  - 缺少类型注解、参数类型错误、返回值错误等")
    print()
    print(f"中优先级 (Medium):    {medium_count:5d} ({(medium_count/total*100):5.1f}%)")
    print(f"  - 泛型参数缺失、返回Any、赋值类型不匹配等")
    print()
    print(f"低优先级 (Low):       {low_count:5d} ({(low_count/total*100):5.1f}%)")
    print(f"  - 其他类型问题")
    print()


def main() -> None:
    """主函数"""
    # 检查是否使用 --run 参数
    if len(sys.argv) > 1 and sys.argv[1] == '--run':
        print("正在运行 mypy apps/ --strict...")
        print()
        output = run_mypy()
        lines = output.split('\n')
    elif sys.stdin.isatty():
        print("用法:")
        print("  mypy apps/ --strict 2>&1 | python scripts/analyze_mypy_errors.py")
        print("  python scripts/analyze_mypy_errors.py < mypy_output.txt")
        print("  python scripts/analyze_mypy_errors.py --run")
        sys.exit(1)
    else:
        lines = sys.stdin.readlines()
    
    errors = parse_mypy_output(lines)
    print_report(errors)


if __name__ == '__main__':
    main()
