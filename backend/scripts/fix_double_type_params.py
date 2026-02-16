#!/usr/bin/env python3
"""修复重复的类型参数"""

import re
from pathlib import Path

def fix_file(file_path: Path) -> int:
    """修复单个文件中的重复类型参数"""
    try:
        content = file_path.read_text(encoding='utf-8')
        original = content
        
        # 修复 dict[str, Any][X, Y] -> dict[X, Y]
        content = re.sub(r'dict\[str,\s*Any\]\[([^\]]+)\]', r'dict[\1]', content)
        
        # 修复 list[Any][X] -> list[X]
        content = re.sub(r'list\[Any\]\[([^\]]+)\]', r'list[\1]', content)
        
        # 修复 set[Any][X] -> set[X]
        content = re.sub(r'set\[Any\]\[([^\]]+)\]', r'set[\1]', content)
        
        if content != original:
            file_path.write_text(content, encoding='utf-8')
            return 1
        
        return 0
    except Exception as e:
        print(f"错误 {file_path}: {e}")
        return 0

def main() -> None:
    """主函数"""
    apps_dir = Path("apps")
    fixed_count = 0
    
    for py_file in apps_dir.rglob("*.py"):
        if fix_file(py_file):
            print(f"✓ {py_file}")
            fixed_count += 1
    
    print(f"\n修复了 {fixed_count} 个文件")

if __name__ == "__main__":
    main()
