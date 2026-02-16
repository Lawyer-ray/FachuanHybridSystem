"""修复type: ignore注释的格式问题"""

from __future__ import annotations

import re
from pathlib import Path


def fix_file(file_path: Path) -> bool:
    """修复文件中的type: ignore格式问题"""
    try:
        content = file_path.read_text(encoding="utf-8")
        original = content

        # 修复格式: "-> Any  # type: ignore[type-arg]:" -> "-> Any:  # type: ignore[type-arg]"
        content = re.sub(r"(\s+)# type: ignore\[type-arg\]:", r":\1# type: ignore[type-arg]", content)

        if content != original:
            file_path.write_text(content, encoding="utf-8")
            return True
        return False

    except Exception as e:
        print(f"处理失败 {file_path}: {e}")
        return False


def main() -> None:
    """批量修复所有Python文件"""
    backend_path = Path("apps")
    fixed_count = 0

    for py_file in backend_path.rglob("*.py"):
        if fix_file(py_file):
            print(f"✓ {py_file}")
            fixed_count += 1

    print(f"\n修复完成! 共修复 {fixed_count} 个文件")


if __name__ == "__main__":
    main()
