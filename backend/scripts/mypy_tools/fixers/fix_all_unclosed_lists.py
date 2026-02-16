#!/usr/bin/env python3
"""修复所有未闭合的列表和字典定义"""
from __future__ import annotations

import re
from pathlib import Path


def fix_file(file_path: Path) -> bool:
    """修复文件中所有未闭合的列表和字典"""
    try:
        content = file_path.read_text(encoding="utf-8")
        original = content
        lines = content.split("\n")

        i = 0
        while i < len(lines):
            line = lines[i]

            # 查找模式: xxx: list[Any] = [ 或 xxx: dict[str, Any] = {
            # 后面紧跟着不是列表/字典元素的内容
            if ": list[Any] = [" in line and not line.rstrip().endswith("["):
                # 检查下一行
                if i + 1 < len(lines):
                    next_line = lines[i + 1].strip()
                    # 如果下一行不是列表元素（不以 ' 或 " 或数字开头，也不是 ]）
                    if next_line and not next_line.startswith(("]", "'", '"', "(", "[")) and not next_line[0].isdigit():
                        # 闭合列表
                        lines[i] = line.replace("= [", "= []")

            elif ": dict[str, Any] = {" in line and not line.rstrip().endswith("{"):
                # 检查下一行
                if i + 1 < len(lines):
                    next_line = lines[i + 1].strip()
                    # 如果下一行不是字典元素
                    if next_line and not next_line.startswith(("}", "'", '"')) and ":" not in next_line[:20]:
                        # 闭合字典
                        lines[i] = line.replace("= {", "= {}")

            i += 1

        new_content = "\n".join(lines)
        if new_content != original:
            file_path.write_text(new_content, encoding="utf-8")
            return True
        return False

    except Exception as e:
        print(f"错误处理 {file_path}: {e}")
        return False


def main() -> None:
    backend_path = Path(__file__).parent.parent
    automation_path = backend_path / "apps" / "automation"

    fixed_files = []
    for py_file in automation_path.rglob("*.py"):
        if fix_file(py_file):
            fixed_files.append(py_file.relative_to(backend_path))

    if fixed_files:
        print(f"修复了 {len(fixed_files)} 个文件:")
        for f in fixed_files:
            print(f"  ✓ {f}")
    else:
        print("没有需要修复的文件")


if __name__ == "__main__":
    main()
