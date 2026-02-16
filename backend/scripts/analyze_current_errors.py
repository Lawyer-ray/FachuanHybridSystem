#!/usr/bin/env python3
"""分析当前mypy错误分布"""

import subprocess
import re
from collections import Counter

def analyze_mypy_errors():
    """运行mypy并分析错误"""
    result = subprocess.run(
        ["python", "-m", "mypy", "apps/", "--strict"],
        capture_output=True,
        text=True,
        cwd="."
    )
    
    output = result.stdout + result.stderr
    
    # 解析错误
    error_pattern = re.compile(r'error: .+ \[([a-z-]+)\]')
    errors = error_pattern.findall(output)
    
    # 统计
    counter = Counter(errors)
    
    print(f"总错误数: {len(errors)}")
    print(f"\n错误类型分布（前20）:")
    print("-" * 50)
    for error_type, count in counter.most_common(20):
        print(f"{error_type:30s} {count:5d}")
    
    return counter

if __name__ == "__main__":
    analyze_mypy_errors()
