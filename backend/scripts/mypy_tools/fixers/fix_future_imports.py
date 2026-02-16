#!/usr/bin/env python3
"""修复 from __future__ import annotations 位置错误"""
from pathlib import Path
import re

def fix_future_import(file_path: Path) -> bool:
    """修复单个文件的 future import 位置"""
    content = file_path.read_text(encoding='utf-8')
    
    # 检查是否有问题
    if 'from __future__ import annotations' not in content:
        return False
    
    lines = content.split('\n')
    
    # 找到 docstring 结束位置
    docstring_end = 0
    in_docstring = False
    docstring_char = None
    
    for i, line in enumerate(lines):
        stripped = line.strip()
        
        # 检测 docstring 开始
        if not in_docstring:
            if stripped.startswith('"""') or stripped.startswith("'''"):
                docstring_char = stripped[:3]
                in_docstring = True
                # 检查是否是单行 docstring
                if stripped.count(docstring_char) >= 2:
                    docstring_end = i
                    break
        else:
            # 检测 docstring 结束
            if docstring_char in line:
                docstring_end = i
                break
    
    # 找到 from __future__ import annotations 的位置
    future_line_idx = None
    for i, line in enumerate(lines):
        if 'from __future__ import annotations' in line:
            future_line_idx = i
            break
    
    if future_line_idx is None:
        return False
    
    # 如果已经在正确位置，不需要修复
    if future_line_idx == docstring_end + 1 or (docstring_end == 0 and future_line_idx == 0):
        return False
    
    # 移除原位置的 future import
    future_line = lines[future_line_idx]
    lines.pop(future_line_idx)
    
    # 插入到正确位置（docstring 后面）
    insert_pos = docstring_end + 1
    lines.insert(insert_pos, future_line)
    
    # 写回文件
    file_path.write_text('\n'.join(lines), encoding='utf-8')
    return True

def main() -> None:
    backend_path = Path(__file__).parent.parent
    apps_path = backend_path / 'apps'
    
    print("开始修复 from __future__ import annotations 位置...")
    
    fixed_files = []
    
    for py_file in apps_path.rglob('*.py'):
        if fix_future_import(py_file):
            fixed_files.append(py_file.relative_to(backend_path))
            print(f"✓ {py_file.relative_to(backend_path)}")
    
    print(f"\n总计修复 {len(fixed_files)} 个文件")

if __name__ == '__main__':
    main()
