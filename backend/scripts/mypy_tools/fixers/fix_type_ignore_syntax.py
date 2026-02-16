#!/usr/bin/env python
"""
修复 type: ignore 注释导致的语法错误

将 `if condition  # type: ignore[...]:` 修复为 `if condition:  # type: ignore[...]`
"""

import re
from pathlib import Path


def fix_type_ignore_syntax(file_path: Path) -> int:
    """修复 type: ignore 语法错误"""
    if not file_path.exists():
        return 0

    content = file_path.read_text(encoding="utf-8")
    original = content

    # 修复 if condition  # type: ignore[...]: 的情况
    # 将 type: ignore 移到冒号后面
    content = re.sub(r"(\s+if .+?)\s+(# type: ignore\[[^\]]+\]):", r"\1:  \2", content)

    # 修复 for/while 等其他语句
    content = re.sub(r"(\s+(?:for|while) .+?)\s+(# type: ignore\[[^\]]+\]):", r"\1:  \2", content)

    if content != original:
        file_path.write_text(content, encoding="utf-8")
        return 1

    return 0


def main() -> None:
    """主函数"""
    backend_path = Path(__file__).parent.parent
    cases_path = backend_path / "apps" / "cases"

    print("开始修复 type: ignore 语法错误...")

    fixed = 0
    for py_file in cases_path.rglob("*.py"):
        if py_file.name == "__init__.py":
            continue
        fixed += fix_type_ignore_syntax(py_file)

    print(f"修复了 {fixed} 个文件")
    print("\n请运行 'python -m mypy apps/cases/ --strict' 查看剩余错误")


if __name__ == "__main__":
    main()
