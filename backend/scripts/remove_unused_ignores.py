#!/usr/bin/env python3
"""移除所有unused type: ignore注释"""

import re
from pathlib import Path


def remove_unused_ignores(content: str) -> str:
    """移除unused type: ignore注释"""
    # 移除 # type: ignore[xxx]
    content = re.sub(r'\s*#\s*type:\s*ignore\[[^\]]+\]', '', content)
    return content


def process_file(file_path: Path) -> bool:
    """处理单个文件"""
    try:
        content = file_path.read_text(encoding='utf-8')
        original = content
        
        content = remove_unused_ignores(content)
        
        if content != original:
            file_path.write_text(content, encoding='utf-8')
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
    
    print(f"完成! 修复了 {fixed_count} 个文件")


if __name__ == "__main__":
    main()
