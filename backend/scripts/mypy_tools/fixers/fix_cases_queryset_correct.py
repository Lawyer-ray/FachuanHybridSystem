#!/usr/bin/env python
"""
正确修复 cases 模块的 QuerySet 类型

Django 6.0 的 QuerySet 需要两个类型参数：QuerySet[Model, Model]
"""

import re
from pathlib import Path


def fix_queryset_single_to_double(file_path: Path) -> int:
    """修复 QuerySet[Model] -> QuerySet[Model, Model]"""
    if not file_path.exists():
        return 0

    content = file_path.read_text(encoding="utf-8")
    original = content

    # 修复 QuerySet[Model] -> QuerySet[Model, Model]
    # 但要避免已经是 QuerySet[Model, Model] 的情况
    content = re.sub(
        r"QuerySet\[(\w+)\](?!\[)", r"QuerySet[\1, \1]", content  # 匹配 QuerySet[Model] 但不匹配 QuerySet[Model, Model]
    )

    if content != original:
        file_path.write_text(content, encoding="utf-8")
        return 1

    return 0


def main() -> None:
    """主函数"""
    backend_path = Path(__file__).parent.parent
    cases_path = backend_path / "apps" / "cases"

    print("开始修复 cases 模块 QuerySet 类型...")

    fixed = 0
    for py_file in cases_path.rglob("*.py"):
        if py_file.name == "__init__.py":
            continue
        fixed += fix_queryset_single_to_double(py_file)

    print(f"修复了 {fixed} 个文件")
    print("\n请运行 'python -m mypy apps/cases/ --strict' 查看剩余错误")


if __name__ == "__main__":
    main()
