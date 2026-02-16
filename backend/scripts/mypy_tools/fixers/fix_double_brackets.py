#!/usr/bin/env python3
"""修复双括号问题"""
from pathlib import Path

def fix_file(file_path: Path) -> bool:
    try:
        content = file_path.read_text(encoding='utf-8')
        original = content
        
        # 修复 []]
        content = content.replace('[]]', '[]')
        # 修复 {}}
        content = content.replace('{}}', '{}')
        
        if content != original:
            file_path.write_text(content, encoding='utf-8')
            return True
        return False
    except Exception as e:
        print(f"错误: {file_path}: {e}")
        return False

def main() -> None:
    backend_path = Path(__file__).parent.parent
    automation_path = backend_path / 'apps' / 'automation'
    
    fixed = 0
    for py_file in automation_path.rglob('*.py'):
        if fix_file(py_file):
            fixed += 1
    
    print(f"修复了 {fixed} 个文件")

if __name__ == '__main__':
    main()
