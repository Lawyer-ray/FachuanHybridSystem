#!/usr/bin/env python3
"""
批量修复所有常见的 mypy 错误模式
"""

from pathlib import Path
import re

def fix_file(file_path: Path) -> int:
    """修复单个文件,返回修复数量"""
    try:
        content = file_path.read_text()
        original = content
        lines = content.split('\n')
        
        # 1. 修复 path: list = [] -> path = []
        for i, line in enumerate(lines):
            if re.search(r'(\w+):\s*(list|dict|set)\s*=\s*\[\]', line):
                lines[i] = re.sub(r'(\w+):\s*(list|dict|set)\s*=\s*\[\]', r'\1 = []', line)
            elif re.search(r'(\w+):\s*(list|dict|set)\s*=\s*\{\}', line):
                lines[i] = re.sub(r'(\w+):\s*(list|dict|set)\s*=\s*\{\}', r'\1 = {}', line)
            elif re.search(r'(\w+):\s*set\s*=\s*set\(\)', line):
                lines[i] = re.sub(r'(\w+):\s*set\s*=\s*set\(\)', r'\1 = set()', line)
        
        content = '\n'.join(lines)
        
        if content != original:
            file_path.write_text(content)
            return 1
    
    except Exception as e:
        print(f"❌ {file_path}: {e}")
    
    return 0

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
