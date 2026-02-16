#!/usr/bin/env python3
"""修复typing导入中的语法错误"""

import re
from pathlib import Path


def fix_typing_imports(content: str) -> str:
    """修复typing导入中的dict[str, Any]语法错误"""
    # 从typing导入中移除dict[str, Any]
    content = re.sub(
        r'from typing import ([^;\n]*?)dict\[str, Any\],?\s*',
        r'from typing import \1',
        content
    )
    content = re.sub(
        r'from typing import ([^;\n]*?),\s*dict\[str, Any\]',
        r'from typing import \1',
        content
    )
    
    # 修复typing导入中混入了其他导入语句的情况
    # from typing import ..., from .xxx import -> from typing import ...\nfrom .xxx import
    content = re.sub(
        r'from typing import ([^;\n]*?),\s*from\s+',
        r'from typing import \1\nfrom ',
        content
    )
    
    # 修复typing导入中混入了logger定义的情况
    # from typing import ..., logger = -> from typing import ...\nlogger =
    content = re.sub(
        r'from typing import ([^;\n]*?),\s*logger\s*=',
        r'from typing import \1\n\nlogger =',
        content
    )
    
    # 清理多余的逗号和空格
    content = re.sub(r'from typing import\s*,\s*', 'from typing import ', content)
    content = re.sub(r'from typing import ([^;\n]*?),\s*,', r'from typing import \1,', content)
    content = re.sub(r'from typing import ([^;\n]*?),\s*\n', r'from typing import \1\n', content)
    
    return content


def process_file(file_path: Path) -> bool:
    """处理单个文件"""
    try:
        content = file_path.read_text(encoding='utf-8')
        original = content
        
        content = fix_typing_imports(content)
        
        if content != original:
            file_path.write_text(content, encoding='utf-8')
            print(f"✓ 修复: {file_path}")
            return True
        return False
    except Exception as e:
        print(f"✗ 错误 {file_path}: {e}")
        return False


def main() -> None:
    """主函数"""
    base_dir = Path(__file__).parent.parent / "apps"
    
    fixed_count = 0
    for py_file in base_dir.rglob("*.py"):
        if "__pycache__" in str(py_file):
            continue
        if process_file(py_file):
            fixed_count += 1
    
    print(f"\n完成! 修复了 {fixed_count} 个文件")


if __name__ == "__main__":
    main()
