#!/usr/bin/env python3
"""批量修复name-defined错误"""
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


def fix_indentation_issues():
    """修复缩进问题导致的name-defined错误"""
    print("=== 检查缩进问题 ===\n")

    # 查找有大量name-defined错误的文件（可能是缩进问题）
    errors = parse_name_defined_errors(get_mypy_errors())
    file_errors = defaultdict(list)
    for error in errors:
        file_errors[error["file"]].append(error)

    # 重点检查错误数量>5的文件
    for file_path, errs in file_errors.items():
        if len(errs) < 5:
            continue

        print(f"检查文件: {file_path} ({len(errs)}个错误)")

        try:
            with open(file_path, "r", encoding="utf-8") as f:
                content = f.read()

            # 尝试解析AST，如果失败说明有语法错误
            try:
                ast.parse(content)
                print(f"  ✓ AST解析成功，不是缩进问题")
            except SyntaxError as e:
                print(f"  ✗ 语法错误: {e}")
                print(f"    需要手动修复")
        except Exception as e:
            print(f"  错误: {e}")


def fix_forward_references():
    """修复前向引用问题"""
    print("\n=== 修复前向引用 ===\n")

    errors = parse_name_defined_errors(get_mypy_errors())
    file_errors = defaultdict(list)
    for error in errors:
        file_errors[error["file"]].append(error)

    fixed_count = 0

    for file_path, errs in file_errors.items():
        # 检查是否有类名的前向引用
        undefined_names = set(e["name"] for e in errs)

        try:
            with open(file_path, "r", encoding="utf-8") as f:
                content = f.read()
                lines = content.split("\n")

            # 查找文件中定义的类名
            defined_classes = set()
            for line in lines:
                match = re.match(r"^class\s+(\w+)", line)
                if match:
                    defined_classes.add(match.group(1))

            # 找出需要加引号的前向引用
            forward_refs = undefined_names & defined_classes

            if not forward_refs:
                continue

            print(f"修复文件: {file_path}")
            print(f"  前向引用: {', '.join(forward_refs)}")

            # 这些通常已经在字符串中了，检查是否缺少__future__ import
            if "from __future__ import annotations" not in content:
                # 添加future annotations
                insert_pos = 0
                for i, line in enumerate(lines):
                    if line.startswith('"""') or line.startswith("'''"):
                        # 跳过docstring
                        if i + 1 < len(lines):
                            for j in range(i + 1, len(lines)):
                                if lines[j].endswith('"""') or lines[j].endswith("'''"):
                                    insert_pos = j + 1
                                    break
                        break
                    elif line.startswith("from ") or line.startswith("import "):
                        insert_pos = i
                        break
                    elif line.strip() and not line.startswith("#"):
                        insert_pos = i
                        break

                lines.insert(insert_pos, "from __future__ import annotations")
                lines.insert(insert_pos + 1, "")

                new_content = "\n".join(lines)
                with open(file_path, "w", encoding="utf-8") as f:
                    f.write(new_content)

                print(f"  ✓ 已添加 from __future__ import annotations")
                fixed_count += 1

        except Exception as e:
            print(f"  错误: {e}")

    print(f"\n修复了 {fixed_count} 个文件的前向引用问题")
    return fixed_count


def list_remaining_errors():
    """列出剩余的name-defined错误"""
    print("\n=== 剩余的name-defined错误 ===\n")

    errors = parse_name_defined_errors(get_mypy_errors())
    file_errors = defaultdict(list)
    for error in errors:
        file_errors[error["file"]].append(error)

    print(f"总共 {len(errors)} 个错误，分布在 {len(file_errors)} 个文件中\n")

    # 按文件分组显示
    for file_path in sorted(file_errors.keys(), key=lambda x: len(file_errors[x]), reverse=True)[:10]:
        errs = file_errors[file_path]
        print(f"{file_path}: {len(errs)}个错误")
        names = set(e["name"] for e in errs)
        print(f"  未定义: {', '.join(sorted(names))}")


if __name__ == "__main__":
    print("正在分析name-defined错误...\n")

    # 1. 检查缩进问题
    fix_indentation_issues()

    # 2. 修复前向引用
    fix_forward_references()

    # 3. 列出剩余错误
    list_remaining_errors()

    # 4. 统计
    print("\n=== 最终统计 ===")
    errors = parse_name_defined_errors(get_mypy_errors())
    print(f"剩余name-defined错误: {len(errors)}个")
