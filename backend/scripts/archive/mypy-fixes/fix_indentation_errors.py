#!/usr/bin/env python3
"""自动检测和修复缩进导致的name-defined错误"""
import ast
import re
import subprocess
from collections import defaultdict
from pathlib import Path
from typing import Any


def get_mypy_errors():
    """获取mypy错误"""
    result = subprocess.run(
        ["python", "-m", "mypy", "apps/", "--strict", "--no-error-summary"], capture_output=True, text=True, cwd="."
    )
    return result.stdout + result.stderr


def parse_name_defined_errors(output: str):
    """解析name-defined错误"""
    lines = output.split("\n")
    errors = []

    i = 0
    while i < len(lines):
        line = lines[i]
        match = re.match(r"(.+?):(\d+):(\d+): error:", line)
        if match:
            file_path, line_no, col = match.groups()
            full_line = line
            if i + 1 < len(lines) and not lines[i + 1].startswith("apps/"):
                full_line += " " + lines[i + 1].strip()

            if "[name-defined]" in full_line:
                name_match = re.search(r'Name "([^"]+)" is not defined', full_line)
                if name_match:
                    name = name_match.group(1)
                    errors.append({"file": file_path, "line": int(line_no), "col": int(col), "name": name})
        i += 1

    return errors


def check_indentation_pattern(file_path: str, errors: list) -> bool:
    """检查是否是缩进问题的模式"""
    # 如果一个文件有多个简单变量名未定义（如is_our, base, index等），
    # 很可能是缩进问题导致这些变量在错误的作用域

    undefined_names = [e["name"] for e in errors]

    # 简单变量名（不是类名或服务名）
    simple_names = [n for n in undefined_names if n.islower() or "_" in n]

    # 如果有3个以上简单变量名未定义，可能是缩进问题
    return len(simple_names) >= 3


def analyze_indentation_issues(file_path: str, errors: list):
    """分析文件的缩进问题"""
    print(f"\n分析文件: {file_path}")
    print(f"  未定义变量: {', '.join(set(e['name'] for e in errors))}")

    try:
        with open(file_path, "r", encoding="utf-8") as f:
            content = f.read()
            lines = content.split("\n")

        # 检查每个错误行的上下文
        for error in errors:
            line_no = error["line"] - 1  # 转为0-based
            name = error["name"]

            if line_no >= len(lines):
                continue

            error_line = lines[line_no]

            # 检查这个变量是否在附近被赋值
            search_start = max(0, line_no - 20)
            search_end = min(len(lines), line_no + 5)

            for i in range(search_start, search_end):
                if i == line_no:
                    continue
                line = lines[i]
                # 检查是否有赋值语句
                if re.match(rf"\s*{re.escape(name)}\s*=", line):
                    indent_assign = len(line) - len(line.lstrip())
                    indent_use = len(error_line) - len(error_line.lstrip())

                    if indent_assign > indent_use:
                        print(f"  ⚠️  第{error['line']}行: '{name}' 在第{i+1}行被赋值，但缩进更深")
                        print(f"      赋值行缩进: {indent_assign}, 使用行缩进: {indent_use}")
                        print(f"      可能是方法定义缩进错误")
                        return True

        # 检查是否有def语句缩进异常
        for i, line in enumerate(lines):
            if re.match(r"\s+def\s+\w+", line):
                indent = len(line) - len(line.lstrip())
                # 检查前一个def的缩进
                for j in range(i - 1, max(0, i - 10), -1):
                    if re.match(r"\s+def\s+\w+", lines[j]):
                        prev_indent = len(lines[j]) - len(lines[j].lstrip())
                        if indent > prev_indent + 8:  # 缩进差异过大
                            print(f"  ⚠️  第{i+1}行: 方法定义缩进异常 (当前:{indent}, 前一个:{prev_indent})")
                            return True
                        break

    except Exception as e:
        print(f"  错误: {e}")

    return False


def main():
    print("=== 检测缩进导致的name-defined错误 ===\n")

    errors = parse_name_defined_errors(get_mypy_errors())
    file_errors = defaultdict(list)
    for error in errors:
        file_errors[error["file"]].append(error)

    print(f"总共 {len(errors)} 个name-defined错误，分布在 {len(file_errors)} 个文件中\n")

    indentation_issues = []

    for file_path, errs in file_errors.items():
        if check_indentation_pattern(file_path, errs):
            if analyze_indentation_issues(file_path, errs):
                indentation_issues.append(file_path)

    if indentation_issues:
        print(f"\n\n=== 发现 {len(indentation_issues)} 个文件可能有缩进问题 ===")
        for file_path in indentation_issues:
            print(f"  - {file_path}")
        print("\n建议手动检查这些文件的方法定义缩进")
    else:
        print("\n未发现明显的缩进问题")


if __name__ == "__main__":
    main()
