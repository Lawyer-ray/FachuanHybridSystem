#!/usr/bin/env python3
"""修复 SMS 模块的导入错误。"""

import re
from pathlib import Path


def fix_imports(file_path: Path) -> bool:
    """修复文件中的导入错误。"""
    content = file_path.read_text(encoding="utf-8")
    original = content

    # 修复 from typing import Optional, list[Any], ...
    content = re.sub(r"from typing import ([^)]*?)Optional,\s*list\[Any\],\s*", r"from typing import \1", content)

    # 修复 logger = logging.getLogger("...", Any)
    content = re.sub(r'logger = logging\.getLogger\("([^"]+)",\s*Any\)', r'logger = logging.getLogger("\1")', content)

    # 修复 , Any) 在导入语句中
    content = re.sub(r",\s*Any\)\s*\n(\s*)from ", r")\n\1from ", content)

    if content != original:
        file_path.write_text(content, encoding="utf-8")
        return True
    return False


def main() -> None:
    """主函数。"""
    sms_path = Path(__file__).parent.parent / "apps" / "automation" / "services" / "sms"

    fixed_count = 0
    for py_file in sms_path.rglob("*.py"):
        if fix_imports(py_file):
            fixed_count += 1
            print(f"修复: {py_file.relative_to(sms_path)}")

    print(f"\n总计修复 {fixed_count} 个文件")


if __name__ == "__main__":
    main()
