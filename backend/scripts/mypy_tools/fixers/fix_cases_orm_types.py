#!/usr/bin/env python
"""
批量修复 cases 模块的 Django ORM 类型错误

修复内容：
1. QuerySet[Model, Model] -> QuerySet[Model]
2. 使用 cast() 处理 Model.objects.first() 等返回 Any 的情况
3. 为 values_list 添加类型注解
"""

import re
from pathlib import Path


def fix_queryset_double_generic(file_path: Path) -> int:
    """修复 QuerySet[Model, Model] -> QuerySet[Model]"""
    if not file_path.exists():
        return 0

    content = file_path.read_text(encoding="utf-8")
    original = content

    # 修复 QuerySet[Model, Model] -> QuerySet[Model]
    content = re.sub(r"QuerySet\[(\w+),\s*\1\]", r"QuerySet[\1]", content)

    if content != original:
        file_path.write_text(content, encoding="utf-8")
        return 1

    return 0


def fix_values_list_type(file_path: Path) -> int:
    """为 values_list 添加类型注解"""
    if not file_path.exists():
        return 0

    content = file_path.read_text(encoding="utf-8")
    lines = content.split("\n")
    fixed = 0

    for i, line in enumerate(lines):
        # 查找 existing_statuses = list( 模式
        if "existing_statuses = list(" in line or "existing_" in line and "= list(" in line:
            # 检查下一行是否有 values_list
            if i + 3 < len(lines):
                next_lines = "\n".join(lines[i : i + 4])
                if "values_list(" in next_lines and ": list[" not in line:
                    # 添加类型注解
                    lines[i] = line.replace("existing_statuses = list(", "existing_statuses: list[str] = list(")
                    lines[i] = lines[i].replace("existing_ids = list(", "existing_ids: list[int] = list(")
                    fixed += 1

    if fixed > 0:
        file_path.write_text("\n".join(lines), encoding="utf-8")

    return fixed


def fix_model_first_return(file_path: Path) -> int:
    """修复 Model.objects.first() 返回类型"""
    if not file_path.exists():
        return 0

    content = file_path.read_text(encoding="utf-8")
    original = content

    # 不自动修复，因为需要根据上下文判断
    # 这里只是标记需要手动修复的地方

    return 0


def main() -> None:
    """主函数"""
    backend_path = Path(__file__).parent.parent
    cases_path = backend_path / "apps" / "cases"

    print("开始修复 cases 模块 Django ORM 类型错误...")

    # 1. 修复 QuerySet[Model, Model]
    print("\n1. 修复 QuerySet[Model, Model]...")
    fixed_qs = 0
    for py_file in cases_path.rglob("*.py"):
        if py_file.name == "__init__.py":
            continue
        fixed_qs += fix_queryset_double_generic(py_file)
    print(f"   修复了 {fixed_qs} 个文件")

    # 2. 修复 values_list 类型注解
    print("\n2. 修复 values_list 类型注解...")
    fixed_vl = 0
    for py_file in cases_path.rglob("*.py"):
        if py_file.name == "__init__.py":
            continue
        fixed_vl += fix_values_list_type(py_file)
    print(f"   修复了 {fixed_vl} 个文件")

    print("\n修复完成！")
    print("请运行 'python -m mypy apps/cases/ --strict' 查看剩余错误")


if __name__ == "__main__":
    main()
