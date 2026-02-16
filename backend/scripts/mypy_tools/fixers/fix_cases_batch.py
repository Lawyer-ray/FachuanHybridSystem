#!/usr/bin/env python3
"""
批量修复cases模块的简单类型错误
"""
import ast
import re
from pathlib import Path
from typing import Set


def add_cast_import(content: str) -> str:
    """添加cast导入"""
    if "cast(" in content and "from typing import" in content:
        # 检查是否已经导入了cast
        if not re.search(r"from typing import.*\bcast\b", content):
            # 找到第一个from typing import行
            match = re.search(r"from typing import ([^\n]+)", content)
            if match:
                imports = match.group(1)
                # 如果导入在括号中
                if "(" in imports:
                    # 在括号内添加cast
                    content = re.sub(
                        r"(from typing import \([^)]+)", lambda m: m.group(1).rstrip() + ", cast", content, count=1
                    )
                else:
                    # 直接添加cast
                    content = re.sub(
                        r"(from typing import [^\n]+)", lambda m: m.group(1).rstrip() + ", cast", content, count=1
                    )
    return content


def fix_invalid_type_comments(content: str) -> str:
    """修复无效的类型注释"""
    # 修复 type: # 这种格式
    content = re.sub(r"(\w+)\s*:\s*#\s*type:\s*([^\n]+)", r"\1: \2  #", content)
    return content


def fix_queryset_type_params(content: str) -> str:
    """修复QuerySet缺少类型参数"""
    # QuerySet[Model] 需要两个参数,第二个是Row类型
    # 但在Django中通常只需要一个,所以我们添加Any作为第二个参数
    if "QuerySet[" in content and "from typing import" in content:
        # 确保导入了Any
        if not re.search(r"from typing import.*\bAny\b", content):
            content = re.sub(r"(from typing import [^\n]+)", lambda m: m.group(1).rstrip() + ", Any", content, count=1)
    return content


def fix_file(file_path: Path) -> tuple[bool, list[str]]:
    """修复单个文件的简单类型错误"""
    changes = []
    try:
        content = file_path.read_text(encoding="utf-8")
        original = content

        # 1. 添加cast导入
        new_content = add_cast_import(content)
        if new_content != content:
            changes.append("添加cast导入")
            content = new_content

        # 2. 修复无效的类型注释
        new_content = fix_invalid_type_comments(content)
        if new_content != content:
            changes.append("修复无效类型注释")
            content = new_content

        # 3. 修复QuerySet类型参数
        new_content = fix_queryset_type_params(content)
        if new_content != content:
            changes.append("修复QuerySet类型参数")
            content = new_content

        if content != original:
            file_path.write_text(content, encoding="utf-8")
            return True, changes
        return False, []
    except Exception as e:
        print(f"处理文件 {file_path} 时出错: {e}")
        return False, []


def main() -> None:
    """主函数"""
    cases_dir = Path("apps/cases")
    if not cases_dir.exists():
        print(f"目录不存在: {cases_dir}")
        return

    fixed_count = 0
    total_count = 0

    # 遍历所有Python文件
    for py_file in cases_dir.rglob("*.py"):
        if py_file.name == "__init__.py":
            continue

        total_count += 1
        fixed, changes = fix_file(py_file)
        if fixed:
            fixed_count += 1
            print(f"✓ 修复: {py_file}")
            for change in changes:
                print(f"  - {change}")

    print(f"\n总计: 检查了 {total_count} 个文件, 修复了 {fixed_count} 个文件")


if __name__ == "__main__":
    main()
