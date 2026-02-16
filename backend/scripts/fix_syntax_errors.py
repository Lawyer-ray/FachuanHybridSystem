#!/usr/bin/env python3
"""修复由自动修复引入的语法错误"""
import re
from pathlib import Path

def fix_file(file_path: Path) -> bool:
    """修复文件中的语法错误"""
    try:
        content = file_path.read_text()
        original = content
        
        # 修复 try: var | None = None 模式
        content = re.sub(
            r'try:\s+(\w+)\s+\|\s+None\s+=\s+None',
            r'try:\n                    \1: Any | None = None',
            content
        )
        
        # 修复 else: var | None = None 模式
        content = re.sub(
            r'else:\s+(\w+)\s+\|\s+None\s+=\s+None',
            r'else:\n                    \1: Any | None = None',
            content
        )
        
        # 修复其他 statement: var | None = None 模式
        content = re.sub(
            r'(\w+):\s+(\w+)\s+\|\s+None\s+=\s+None',
            lambda m: f'{m.group(1)}:\n                    {m.group(2)}: Any | None = None' if m.group(1) in ['try', 'else', 'except', 'finally'] else m.group(0),
            content
        )
        
        if content != original:
            file_path.write_text(content)
            return True
    except Exception as e:
        print(f"  错误 {file_path}: {e}")
    return False

def main():
    print("修复语法错误...")
    
    py_files = list(Path('apps').rglob('*.py'))
    fixed_count = 0
    
    for py_file in py_files:
        if fix_file(py_file):
            fixed_count += 1
            print(f"✓ {py_file}")
    
    print(f"\n修复了 {fixed_count} 个文件")

if __name__ == "__main__":
    main()
