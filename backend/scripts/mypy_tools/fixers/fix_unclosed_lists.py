#!/usr/bin/env python3
"""修复未闭合的列表定义"""
from __future__ import annotations

import re
from pathlib import Path


def fix_unclosed_lists(file_path: Path) -> bool:
    """修复文件中未闭合的列表"""
    content = file_path.read_text(encoding="utf-8")
    original = content

    # 查找模式: xxx: list[Any] = [ 后面紧跟着空行或注释或其他语句
    pattern = r"(\w+):\s*list\[Any\]\s*=\s*\[\s*\n\s*(?:#|def |class |\w+:)"

    def replace_func(match: re.Match[str]) -> str:
        var_name = match.group(1)
        # 获取匹配的完整文本
        matched_text = match.group(0)
        # 替换为闭合的列表
        return matched_text.replace("= [", "= []")

    content = re.sub(pattern, replace_func, content)

    if content != original:
        file_path.write_text(content, encoding="utf-8")
        return True
    return False


def main() -> None:
    backend_path = Path(__file__).parent.parent
    automation_path = backend_path / "apps" / "automation"

    fixed_files = []
    for py_file in automation_path.rglob("*.py"):
        if fix_unclosed_lists(py_file):
            fixed_files.append(py_file.relative_to(backend_path))

    if fixed_files:
        print(f"修复了 {len(fixed_files)} 个文件:")
        for f in fixed_files:
            print(f"  ✓ {f}")
    else:
        print("没有需要修复的文件")


if __name__ == "__main__":
    main()
