#!/usr/bin/env python3
"""修复 list[Any] = [] 后面跟元素的语法错误"""

import re
from pathlib import Path


def fix_list_syntax_in_file(file_path: Path) -> bool:
    """修复单个文件中的列表语法错误"""
    content = file_path.read_text(encoding="utf-8")
    original = content

    # 匹配模式: xxx: list[Any] = []\n        'element',
    # 替换为: xxx: list[Any] = [\n        'element',
    pattern = r"(:\s*list\[Any\]\s*=\s*)\[\](\s+)'([^']+)'"
    replacement = r"\1[\2'\3'"

    content = re.sub(pattern, replacement, content)

    if content != original:
        file_path.write_text(content, encoding="utf-8")
        return True
    return False


def main() -> None:
    backend_path = Path(__file__).parent.parent
    apps_path = backend_path / "apps"

    fixed_files: list[Path] = []

    for py_file in apps_path.rglob("*.py"):
        if fix_list_syntax_in_file(py_file):
            fixed_files.append(py_file)
            print(f"Fixed: {py_file.relative_to(backend_path)}")

    print(f"\n总共修复了 {len(fixed_files)} 个文件")


if __name__ == "__main__":
    main()
