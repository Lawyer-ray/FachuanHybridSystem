#!/usr/bin/env python3
"""
批量修复cases模块中的set[Any]()错误用法
"""
import re
from pathlib import Path


def fix_file(file_path: Path) -> bool:
    """修复单个文件"""
    try:
        content = file_path.read_text(encoding="utf-8")
        original = content

        # 修复 set[Any]() -> set()
        content = re.sub(r"set\[Any\]\(", "set(", content)

        # 修复 list[Any]() -> list()
        content = re.sub(r"list\[Any\]\(", "list(", content)

        # 修复返回类型 -> set[Any][int] 改为 -> set[int]
        content = re.sub(r"-> set\[Any\]\[(\w+)\]", r"-> set[\1]", content)

        # 修复返回类型 -> list[Any][int] 改为 -> list[int]
        content = re.sub(r"-> list\[Any\]\[(\w+)\]", r"-> list[\1]", content)

        # 修复 .set[Any]( 方法调用 -> .set(
        content = re.sub(r"\.set\[Any\]\(", ".set(", content)

        if content != original:
            file_path.write_text(content, encoding="utf-8")
            return True
        return False
    except Exception as e:
        print(f"处理文件 {file_path} 时出错: {e}")
        return False


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
        total_count += 1
        if fix_file(py_file):
            fixed_count += 1
            print(f"✓ 修复: {py_file}")

    print(f"\n总计: 检查了 {total_count} 个文件, 修复了 {fixed_count} 个文件")


if __name__ == "__main__":
    main()
