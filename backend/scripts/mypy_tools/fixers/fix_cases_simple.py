#!/usr/bin/env python3
"""
批量修复cases模块的简单类型错误
"""
import re
from pathlib import Path
from typing import Set


def fix_file(file_path: Path) -> bool:
    """修复单个文件的简单类型错误"""
    try:
        content = file_path.read_text(encoding="utf-8")
        original = content

        # 1. 修复 cast 导入缺失
        if "cast(" in content and "from typing import" in content:
            # 检查是否已经导入了cast
            if not re.search(r"from typing import.*\bcast\b", content):
                # 找到typing导入行并添加cast
                content = re.sub(
                    r"(from typing import [^)]+)",
                    lambda m: m.group(1) + ", cast" if "cast" not in m.group(1) else m.group(1),
                    content,
                )

        # 2. 修复函数缺少返回类型注解 (-> None)
        # 匹配 def 函数名(参数): 但没有 -> 的情况
        content = re.sub(r"(\n    def \w+\([^)]*\)):\n", r"\1 -> None:\n", content)

        # 3. 修复 Invalid type comment (type: # 改为正确的类型注解)
        # 这个需要具体情况具体分析,先跳过

        # 4. 修复 Missing type parameters
        # 已经在之前的脚本中处理过了

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
        if py_file.name == "__init__.py":
            continue

        total_count += 1
        if fix_file(py_file):
            fixed_count += 1
            print(f"✓ 修复: {py_file}")

    print(f"\n总计: 检查了 {total_count} 个文件, 修复了 {fixed_count} 个文件")


if __name__ == "__main__":
    main()
