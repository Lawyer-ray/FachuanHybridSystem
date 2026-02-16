#!/usr/bin/env python3
"""修复name-defined错误"""
import re
import subprocess
from collections import Counter, defaultdict
from pathlib import Path


def get_mypy_errors():
    """获取mypy错误"""
    result = subprocess.run(
        ["python", "-m", "mypy", "apps/", "--strict", "--no-error-summary"], capture_output=True, text=True, cwd="."
    )
    return result.stdout + result.stderr


def parse_name_defined_errors(output: str):
    """解析name-defined错误"""
    # 将输出按行分割，但保留连续的行
    lines = output.split("\n")
    errors = []

    i = 0
    while i < len(lines):
        line = lines[i]
        # 匹配错误行
        match = re.match(r"(.+?):(\d+):(\d+): error:", line)
        if match:
            file_path, line_no, col = match.groups()
            # 检查是否是name-defined错误
            full_line = line
            # 可能错误信息在下一行
            if i + 1 < len(lines) and not lines[i + 1].startswith("apps/"):
                full_line += " " + lines[i + 1].strip()

            if "[name-defined]" in full_line:
                # 提取未定义的名称
                name_match = re.search(r'Name "([^"]+)" is not defined', full_line)
                if name_match:
                    name = name_match.group(1)
                    errors.append({"file": file_path, "line": int(line_no), "col": int(col), "name": name})
        i += 1

    return errors


def analyze_errors(errors):
    """分析错误"""
    print(f"总共找到 {len(errors)} 个name-defined错误\n")

    # 统计未定义的名称
    name_counter = Counter(e["name"] for e in errors)
    print("未定义的名称统计（前30个）：")
    for name, count in name_counter.most_common(30):
        print(f"  {name}: {count}次")

    # 按文件分组
    file_errors = defaultdict(list)
    for error in errors:
        file_errors[error["file"]].append(error)

    print(f"\n按文件分组（前15个）：")
    file_counter = Counter(e["file"] for e in errors)
    for file_path, count in file_counter.most_common(15):
        print(f"  {file_path}: {count}个错误")
        # 显示该文件中的未定义名称
        names = [e["name"] for e in file_errors[file_path]]
        name_counts = Counter(names)
        for name, cnt in name_counts.most_common(5):
            print(f"    - {name}: {cnt}次")

    return errors, name_counter, file_errors


# 常见的缺失导入映射
COMMON_IMPORTS = {
    "Any": "from typing import Any",
    "Optional": "from typing import Optional",
    "List": "from typing import List",
    "Dict": "from typing import Dict",
    "Set": "from typing import Set",
    "Tuple": "from typing import Tuple",
    "Union": "from typing import Union",
    "Callable": "from typing import Callable",
    "Type": "from typing import Type",
    "TypeVar": "from typing import TypeVar",
    "Generic": "from typing import Generic",
    "Protocol": "from typing import Protocol",
    "Literal": "from typing import Literal",
    "logger": "import logging\nlogger = logging.getLogger(__name__)",
}


def fix_missing_imports(errors, name_counter):
    """修复缺失的导入"""
    print("\n\n=== 开始修复缺失的导入 ===\n")

    # 按文件分组
    file_errors = defaultdict(list)
    for error in errors:
        file_errors[error["file"]].append(error)

    fixed_count = 0

    for file_path, file_errs in file_errors.items():
        # 获取该文件中所有未定义的名称
        undefined_names = set(e["name"] for e in file_errs)

        # 找出可以自动修复的名称
        fixable_names = undefined_names & COMMON_IMPORTS.keys()

        if not fixable_names:
            continue

        print(f"修复文件: {file_path}")
        print(f"  未定义的名称: {', '.join(fixable_names)}")

        # 读取文件内容
        try:
            with open(file_path, "r", encoding="utf-8") as f:
                content = f.read()
                lines = content.split("\n")
        except Exception as e:
            print(f"  错误: 无法读取文件 - {e}")
            continue

        # 检查哪些导入已经存在
        existing_imports = set()
        for line in lines[:50]:  # 只检查前50行
            for name in fixable_names:
                if name in line and "import" in line:
                    existing_imports.add(name)

        # 需要添加的导入
        names_to_add = fixable_names - existing_imports

        if not names_to_add:
            print(f"  跳过: 所有导入已存在")
            continue

        # 找到插入导入的位置（在第一个import之后，或在文件开头）
        insert_pos = 0
        last_import_line = -1

        for i, line in enumerate(lines):
            if line.startswith("from ") or line.startswith("import "):
                last_import_line = i
            elif last_import_line >= 0 and line.strip() and not line.startswith("#"):
                # 找到第一个非导入、非空、非注释的行
                insert_pos = last_import_line + 1
                break

        if last_import_line == -1:
            # 没有找到任何导入，插入到文件开头（跳过shebang和编码声明）
            for i, line in enumerate(lines):
                if not line.startswith("#"):
                    insert_pos = i
                    break

        # 生成要添加的导入语句
        imports_to_add = []
        for name in sorted(names_to_add):
            import_stmt = COMMON_IMPORTS[name]
            imports_to_add.append(import_stmt)

        # 插入导入
        new_lines = lines[:insert_pos] + imports_to_add + [""] + lines[insert_pos:]
        new_content = "\n".join(new_lines)

        # 写回文件
        try:
            with open(file_path, "w", encoding="utf-8") as f:
                f.write(new_content)
            print(f"  ✓ 已添加导入: {', '.join(names_to_add)}")
            fixed_count += len(names_to_add)
        except Exception as e:
            print(f"  错误: 无法写入文件 - {e}")

    print(f"\n总共修复了 {fixed_count} 个缺失导入")
    return fixed_count


if __name__ == "__main__":
    print("正在运行mypy检查...")
    output = get_mypy_errors()

    print("正在解析错误...")
    errors = parse_name_defined_errors(output)

    errors, name_counter, file_errors = analyze_errors(errors)

    # 修复缺失的导入
    if errors:
        fix_missing_imports(errors, name_counter)

        # 再次检查
        print("\n\n=== 再次运行mypy检查 ===")
        output = get_mypy_errors()
        new_errors = parse_name_defined_errors(output)
        print(f"\n修复后剩余 {len(new_errors)} 个name-defined错误")
        print(f"减少了 {len(errors) - len(new_errors)} 个错误")
