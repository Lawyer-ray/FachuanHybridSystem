#!/usr/bin/env python3
"""修复 logging import 缩进错误的脚本"""

import re
from pathlib import Path


def fix_logging_indentation(file_path: Path) -> bool:
    """修复单个文件中的 logging import 缩进错误"""
    try:
        content = file_path.read_text(encoding="utf-8")
        original_content = content

        # 模式1: try 块后面紧跟错误缩进的 import logging
        pattern1 = r"(try:\s*\n\s+[^\n]+\n)import logging\n\n\nlogger = logging\.getLogger\(__name__\)\n\n\n(\s+)"
        replacement1 = r"\1    import logging\n\n    logger = logging.getLogger(__name__)\n\n\2"
        content = re.sub(pattern1, replacement1, content)

        # 模式2: 函数定义后面紧跟错误缩进的 import logging
        pattern2 = r'(def [^:]+:\s*\n\s*"""[^"]*"""\s*\n\s+from [^\n]+\n)import logging\n\n\nlogger = logging\.getLogger\(__name__\)\n\n\n(\s+)'
        replacement2 = r"\1    import logging\n\n    logger = logging.getLogger(__name__)\n\n\2"
        content = re.sub(pattern2, replacement2, content)

        # 模式3: 类方法中错误缩进的 import logging
        pattern3 = r'(    def [^:]+:\s*\n\s*"""[^"]*"""\s*\n)import logging\n\n\nlogger = logging\.getLogger\(__name__\)\n\n\n(\s+)'
        replacement3 = r"\1        import logging\n\n        logger = logging.getLogger(__name__)\n\n\2"
        content = re.sub(pattern3, replacement3, content)

        if content != original_content:
            file_path.write_text(content, encoding="utf-8")
            print(f"✓ 修复: {file_path}")
            return True
        return False

    except Exception as e:
        print(f"✗ 错误 {file_path}: {e}")
        return False


def main():
    """主函数"""
    backend_dir = Path(__file__).parent
    apps_dir = backend_dir / "apps"

    fixed_count = 0
    for py_file in apps_dir.rglob("*.py"):
        if fix_logging_indentation(py_file):
            fixed_count += 1

    print(f"\n总计修复 {fixed_count} 个文件")


if __name__ == "__main__":
    main()
