#!/usr/bin/env python3
"""分析 documents 模块的 mypy 错误"""

import re
from collections import defaultdict
from pathlib import Path


def analyze_mypy_errors(error_file: Path) -> None:
    """分析 mypy 错误文件"""

    with open(error_file, "r", encoding="utf-8") as f:
        content = f.read()

    # 提取 documents 模块的错误
    documents_errors = []
    lines = content.split("\n")
    for i, line in enumerate(lines):
        if line.startswith("apps/documents/"):
            # 合并多行错误消息
            full_error = line
            j = i + 1
            while j < len(lines) and (lines[j].startswith("    ") or lines[j].startswith("...")):
                j += 1
            documents_errors.append(full_error)

    # 按错误类型分类
    error_types = defaultdict(list)
    error_type_pattern = r"\[([a-z-]+)\]"

    for error in documents_errors:
        match = re.search(error_type_pattern, error)
        if match:
            error_type = match.group(1)
            error_types[error_type].append(error)

    # 按文件分类
    errors_by_file = defaultdict(list)
    for error in documents_errors:
        # 提取文件路径
        file_match = re.match(r"(apps/documents/[^:]+):", error)
        if file_match:
            file_path = file_match.group(1)
            errors_by_file[file_path].append(error)

    # 输出统计
    print("=" * 80)
    print("Documents 模块 Mypy 错误分析")
    print("=" * 80)
    print(f"\n总错误数: {len(documents_errors)}")

    print("\n" + "=" * 80)
    print("按错误类型分类:")
    print("=" * 80)
    for error_type, errors in sorted(error_types.items(), key=lambda x: len(x[1]), reverse=True):
        print(f"\n{error_type}: {len(errors)} 个错误")
        # 显示前 3 个示例
        for error in errors[:3]:
            print(f"  - {error[:120]}...")

    print("\n" + "=" * 80)
    print("按文件分类 (错误数 >= 5):")
    print("=" * 80)
    for file_path, errors in sorted(errors_by_file.items(), key=lambda x: len(x[1]), reverse=True):
        if len(errors) >= 5:
            print(f"\n{file_path}: {len(errors)} 个错误")

    print("\n" + "=" * 80)
    print("修复优先级建议:")
    print("=" * 80)
    print("\n1. 简单类型错误 (可批量修复):")
    simple_types = ["type-arg", "no-untyped-def", "assignment"]
    for error_type in simple_types:
        if error_type in error_types:
            print(f"   - {error_type}: {len(error_types[error_type])} 个")

    print("\n2. Django ORM 类型错误:")
    orm_types = ["attr-defined"]
    for error_type in orm_types:
        if error_type in error_types:
            print(f"   - {error_type}: {len(error_types[error_type])} 个")

    print("\n3. 复杂类型错误 (需手动修复):")
    complex_types = ["arg-type", "no-any-return", "valid-type", "no-untyped-call", "name-defined"]
    for error_type in complex_types:
        if error_type in error_types:
            print(f"   - {error_type}: {len(error_types[error_type])} 个")


if __name__ == "__main__":
    error_file = Path(__file__).parent.parent / "documents_errors.txt"
    analyze_mypy_errors(error_file)
