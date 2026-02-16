#!/usr/bin/env python3
"""
精确修复 mypy 错误
策略:
1. dict = None -> dict | None = None
2. Exception = None -> Exception | None = None
3. 添加缺失的返回类型 -> Any
"""

import re
import subprocess
from pathlib import Path


def get_mypy_errors():
    """获取所有 mypy 错误"""
    result = subprocess.run(
        ["python", "-m", "mypy", "--config-file", "mypy.ini", "apps/"], capture_output=True, text=True
    )

    errors = {}
    for line in result.stdout.split("\n"):
        if "error:" in line:
            match = re.match(r"(.+?):(\d+):(\d+): error: (.+)", line)
            if match:
                file_path = match.group(1)
                line_no = int(match.group(2))
                message = match.group(4)

                if file_path not in errors:
                    errors[file_path] = []
                errors[file_path].append((line_no, message))

    return errors


def fix_incompatible_default(file_path: Path, errors: list) -> int:
    """修复 Incompatible default 错误"""
    content = file_path.read_text()
    lines = content.split("\n")
    modified = False

    # 确保有 typing 导入
    has_annotations = any("from __future__ import annotations" in line for line in lines)

    if not has_annotations:
        # 在文件开头添加
        lines.insert(0, "from __future__ import annotations")
        modified = True

    for line_no, message in errors:
        if "Incompatible default" not in message:
            continue

        idx = line_no - 1
        if idx >= len(lines):
            continue

        line = lines[idx]

        # 修复 dict = None -> dict | None = None
        if "dict = None" in line and "dict | None" not in line:
            lines[idx] = line.replace("dict = None", "dict | None = None")
            modified = True

        # 修复 Exception = None -> Exception | None = None
        if "Exception = None" in line and "Exception | None" not in line:
            lines[idx] = line.replace("Exception = None", "Exception | None = None")
            modified = True

        # 修复其他类型 = None
        # 模式: name: Type = None -> name: Type | None = None
        pattern = r"(\w+): (\w+) = None"
        if re.search(pattern, line) and "|" not in line:
            lines[idx] = re.sub(pattern, r"\1: \2 | None = None", line)
            modified = True

    if modified:
        file_path.write_text("\n".join(lines))
        return 1
    return 0


def fix_missing_return_type(file_path: Path, errors: list) -> int:
    """修复缺失的返回类型"""
    content = file_path.read_text()
    lines = content.split("\n")
    modified = False

    # 确保有 typing 导入
    has_any = any("from typing import" in line and "Any" in line for line in lines)
    has_annotations = any("from __future__ import annotations" in line for line in lines)

    if not has_annotations:
        lines.insert(0, "from __future__ import annotations")
        modified = True

    if not has_any:
        # 找到导入区域
        import_idx = 0
        for i, line in enumerate(lines):
            if line.startswith("from ") or line.startswith("import "):
                import_idx = i + 1
        if import_idx > 0:
            lines.insert(import_idx, "from typing import Any")
            modified = True

    for line_no, message in errors:
        if "missing a return type" not in message and "missing a type" not in message:
            continue

        idx = line_no - 1
        if idx >= len(lines):
            continue

        line = lines[idx]

        # 检查是否是函数定义
        if "def " in line and "->" not in line:
            # 在 : 之前添加 -> Any
            if line.rstrip().endswith(":"):
                lines[idx] = line.rstrip()[:-1] + " -> Any:"
                modified = True

    if modified:
        file_path.write_text("\n".join(lines))
        return 1
    return 0


def main():
    print("🔍 获取 mypy 错误...")
    errors_by_file = get_mypy_errors()
    print(f"📊 发现 {len(errors_by_file)} 个文件有错误")

    fixed_files = 0

    for file_path_str, errors in errors_by_file.items():
        file_path = Path(file_path_str)
        if not file_path.exists():
            continue

        if fix_incompatible_default(file_path, errors):
            fixed_files += 1
            print(f"✅ {file_path}")

        if fix_missing_return_type(file_path, errors):
            if fixed_files == 0 or errors_by_file.get(file_path_str) != errors:
                fixed_files += 1
            print(f"✅ {file_path}")

    print(f"\n✅ 修复了 {fixed_files} 个文件")

    # 重新检查
    print("\n🔍 重新检查...")
    result = subprocess.run(
        ["python", "-m", "mypy", "--config-file", "mypy.ini", "apps/"], capture_output=True, text=True
    )

    for line in result.stdout.split("\n"):
        if "Found" in line and "error" in line:
            print(f"📊 {line}")


if __name__ == "__main__":
    main()
