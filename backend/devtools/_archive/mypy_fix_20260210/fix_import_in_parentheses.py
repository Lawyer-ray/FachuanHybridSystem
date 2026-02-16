#!/usr/bin/env python3
"""
修复 'from typing import Any' 插入到 import (...) 中间的问题
"""

import re
from pathlib import Path


def fix_file(file_path: Path) -> bool:
    """修复单个文件"""
    try:
        content = file_path.read_text()

        # 检查是否有这个问题
        # 模式: from xxx import (\nfrom typing import Any\n    yyy,
        if "from typing import Any\n   " not in content and "from typing import Any\n    " not in content:
            return False

        lines = content.split("\n")
        new_lines = []
        i = 0
        removed_typing_line = None

        while i < len(lines):
            line = lines[i]

            # 检查是否在 import (...) 块中
            if line.strip() == "from typing import Any":
                # 检查上一行是否是 from xxx import (
                if i > 0 and "import (" in new_lines[-1]:
                    # 这是错误插入的,跳过这行
                    removed_typing_line = line
                    i += 1
                    continue

            new_lines.append(line)
            i += 1

        if removed_typing_line:
            # 在正确的位置添加 from typing import Any
            # 找到 from __future__ import annotations 之后
            insert_idx = 0
            for i, line in enumerate(new_lines):
                if "from __future__ import annotations" in line:
                    insert_idx = i + 1
                    break
                elif line.startswith("from ") or line.startswith("import "):
                    insert_idx = i
                    break

            # 检查是否已经有 from typing import
            has_typing = any("from typing import" in line for line in new_lines)

            if not has_typing:
                # 在合适的位置插入
                if insert_idx > 0:
                    # 跳过空行和注释
                    while insert_idx < len(new_lines) and (
                        new_lines[insert_idx].strip() == ""
                        or new_lines[insert_idx].strip().startswith("#")
                        or new_lines[insert_idx].strip().startswith('"""')
                    ):
                        insert_idx += 1
                    new_lines.insert(insert_idx, "from typing import Any")

            file_path.write_text("\n".join(new_lines))
            return True

    except Exception as e:
        print(f"❌ {file_path}: {e}")

    return False


def main():
    apps_dir = Path("apps")
    fixed = 0

    for py_file in apps_dir.rglob("*.py"):
        if fix_file(py_file):
            print(f"✅ {py_file}")
            fixed += 1

    print(f"\n修复了 {fixed} 个文件")


if __name__ == "__main__":
    main()
