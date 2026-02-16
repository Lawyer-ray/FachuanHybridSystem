#!/usr/bin/env python3
"""修复 extra: Dict[str, Any] = {...} 语法错误"""
from pathlib import Path
import re

def fix_extra_syntax(file_path: Path) -> int:
    """修复单个文件的 extra 语法错误"""
    content = file_path.read_text(encoding='utf-8')
    original = content
    
    # 修复 extra: Dict[str, Any] = {
    # 替换为 extra={
    content = re.sub(
        r'extra: Dict\[str, Any\] = \{',
        r'extra={',
        content
    )
    
    if content != original:
        file_path.write_text(content, encoding='utf-8')
        return original.count('extra: Dict[str, Any] = {')
    
    return 0

def main() -> None:
    backend_path = Path(__file__).parent.parent
    apps_path = backend_path / 'apps'
    
    print("开始修复 extra 语法错误...")
    
    total_fixes = 0
    fixed_files = []
    
    for py_file in apps_path.rglob('*.py'):
        fixes = fix_extra_syntax(py_file)
        if fixes > 0:
            total_fixes += fixes
            fixed_files.append((py_file.relative_to(backend_path), fixes))
            print(f"✓ {py_file.relative_to(backend_path)}: {fixes} 处修复")
    
    print(f"\n总计修复 {total_fixes} 处错误，涉及 {len(fixed_files)} 个文件")

if __name__ == '__main__':
    main()
