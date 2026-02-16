#!/usr/bin/env python3
"""
修复语法问题:
1. 重复的 from __future__ import annotations
2. 重复的 from typing import Any
3. 重复的类/函数定义
"""

from pathlib import Path
import re

def fix_file(file_path: Path) -> bool:
    """修复单个文件"""
    try:
        content = file_path.read_text()
        original = content
        lines = content.split('\n')
        
        # 1. 移除重复的 from __future__ import annotations
        seen_future = False
        new_lines = []
        for line in lines:
            if line.strip() == 'from __future__ import annotations':
                if not seen_future:
                    new_lines.append(line)
                    seen_future = True
                # 跳过重复的
            else:
                new_lines.append(line)
        lines = new_lines
        
        # 2. 移除重复的 from typing import
        seen_typing = {}
        new_lines = []
        for line in lines:
            if line.strip().startswith('from typing import'):
                key = line.strip()
                if key not in seen_typing:
                    new_lines.append(line)
                    seen_typing[key] = True
            else:
                new_lines.append(line)
        
        content = '\n'.join(new_lines)
        
        if content != original:
            file_path.write_text(content)
            return True
    except Exception as e:
        print(f"❌ {file_path}: {e}")
    
    return False

def main():
    apps_dir = Path('apps')
    fixed = 0
    
    for py_file in apps_dir.rglob('*.py'):
        if fix_file(py_file):
            print(f"✅ {py_file}")
            fixed += 1
    
    print(f"\n修复了 {fixed} 个文件")

if __name__ == "__main__":
    main()
