#!/usr/bin/env python3
"""批量移除litigation_ai模块中不需要的type: ignore注释"""

import re
from pathlib import Path
from typing import Any


def remove_unused_type_ignores(file_path: Path) -> tuple[bool, int]:
    """移除文件中不需要的type: ignore注释

    Returns:
        (是否修改, 移除数量)
    """
    try:
        content = file_path.read_text(encoding="utf-8")
        original_content = content

        # 移除 # type: ignore[attr-defined] 注释
        content = re.sub(r"\s*#\s*type:\s*ignore\[attr-defined\]", "", content)

        # 移除行尾的 # type: ignore 注释
        content = re.sub(r"\s*#\s*type:\s*ignore\s*$", "", content, flags=re.MULTILINE)

        if content != original_content:
            file_path.write_text(content, encoding="utf-8")
            removed_count = original_content.count("type: ignore") - content.count("type: ignore")
            return True, removed_count

        return False, 0

    except Exception as e:
        print(f"处理文件失败 {file_path}: {e}")
        return False, 0


def main() -> None:
    """主函数"""
    base_dir = Path(__file__).parent.parent / "apps" / "litigation_ai"

    if not base_dir.exists():
        print(f"目录不存在: {base_dir}")
        return

    total_files = 0
    modified_files = 0
    total_removed = 0

    # 遍历所有Python文件
    for py_file in base_dir.rglob("*.py"):
        if py_file.name == "__init__.py":
            continue

        total_files += 1
        modified, removed = remove_unused_type_ignores(py_file)

        if modified:
            modified_files += 1
            total_removed += removed
            print(f"✓ {py_file.relative_to(base_dir.parent.parent)}: 移除 {removed} 个注释")

    print(f"\n总结:")
    print(f"  扫描文件: {total_files}")
    print(f"  修改文件: {modified_files}")
    print(f"  移除注释: {total_removed}")


if __name__ == "__main__":
    main()
