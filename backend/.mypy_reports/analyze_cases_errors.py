#!/usr/bin/env python3
"""分析 cases 模块的 mypy 错误"""
import re
from collections import Counter
from pathlib import Path

# 读取错误输出
error_file = Path("cases_mypy_result.txt")
if not error_file.exists():
    print("错误文件不存在")
    exit(1)

content = error_file.read_text()

# 提取错误类型
error_pattern = r'\[([a-z-]+)\]'
errors = re.findall(error_pattern, content)

# 统计错误类型
error_counts = Counter(errors)

print("=" * 60)
print("Cases 模块 Mypy 错误统计")
print("=" * 60)
print(f"\n总错误数: {len(errors)}\n")
print("错误类型分布:")
print("-" * 60)
for error_type, count in error_counts.most_common():
    percentage = (count / len(errors)) * 100
    print(f"{error_type:30s} {count:5d} ({percentage:5.1f}%)")
