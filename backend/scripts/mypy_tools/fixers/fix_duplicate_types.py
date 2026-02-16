#!/usr/bin/env python3
"""修复重复的类型注解"""
import re
from pathlib import Path

def fix_duplicate_types(file_path: Path) -> int:
    """修复重复的类型注解，如 dict[str, Any][str, Any] -> dict[str, Any]"""
    try:
        content = file_path.read_text()
        original = content
        
        # 修复重复的泛型类型
        patterns = [
            (r'dict\[str, Any\]\[str, Any\]', 'dict[str, Any]'),
            (r'list\[Any\]\[Any\]', 'list[Any]'),
            (r'list\[Any\]\[Path\]', 'list[Path]'),
            (r'set\[Any\]\[Any\]', 'set[Any]'),
            (r'tuple\[Any, \.\.\.\]\[Any, \.\.\.\]', 'tuple[Any, ...]'),
        ]
        
        for pattern, replacement in patterns:
            content = re.sub(pattern, replacement, content)
        
        if content != original:
            file_path.write_text(content)
            return 1
        return 0
    except Exception as e:
        print(f"错误: {file_path}: {e}")
        return 0

def main():
    apps_dir = Path('apps')
    py_files = list(apps_dir.rglob('*.py'))
    
    modified = 0
    for py_file in py_files:
        if fix_duplicate_types(py_file):
            modified += 1
            print(f"✓ {py_file}")
    
    print(f"\n完成！共修改 {modified} 个文件")

if __name__ == '__main__':
    main()
