#!/usr/bin/env python3
"""分析name-defined错误"""
import re
import subprocess
from collections import Counter


def analyze_name_defined_errors():
    """分析name-defined错误"""
    result = subprocess.run(["python", "-m", "mypy", "apps/", "--strict"], capture_output=True, text=True, cwd=".")

    output = result.stdout + result.stderr

    # 合并多行输出
    lines = output.replace("\n", " ").split("  ")

    # 解析name-defined错误
    pattern = r'(.+?):(\d+):(\d+): error: Name "([^"]+)" is not defined.*?\[name-defined\]'
    errors = []

    for line in lines:
        match = re.search(pattern, line)
        if match:
            file_path, line_no, col, name = match.groups()
            errors.append({"file": file_path, "line": int(line_no), "col": int(col), "name": name})

    print(f"总共找到 {len(errors)} 个name-defined错误\n")

    # 统计未定义的名称
    name_counter = Counter(e["name"] for e in errors)
    print("未定义的名称统计（前20个）：")
    for name, count in name_counter.most_common(20):
        print(f"  {name}: {count}次")

    # 按文件分组
    file_counter = Counter(e["file"] for e in errors)
    print(f"\n按文件分组（前10个）：")
    for file_path, count in file_counter.most_common(10):
        print(f"  {file_path}: {count}个错误")

    return errors


if __name__ == "__main__":
    errors = analyze_name_defined_errors()
