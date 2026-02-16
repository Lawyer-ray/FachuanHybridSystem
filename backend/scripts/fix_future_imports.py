#!/usr/bin/env python3
"""修复 from __future__ import annotations 的位置"""

import re
from pathlib import Path


def fix_future_import(file_path: Path) -> bool:
    """修复单个文件的 future import 位置"""
    try:
        content = file_path.read_text(encoding='utf-8')
        
        # 检查是否有 from __future__ import
        if 'from __future__ import' not in content:
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
                        in_docstring = False
                        docstring_end = i + 1
            # 检测 docstring 结束
            elif docstring_char in stripped:
                in_docstring = False
                docstring_end = i + 1
                break
        
        # 找到所有 from __future__ import 行
        future_lines = []
        other_lines = []
        
        for i, line in enumerate(lines):
            if i < docstring_end:
                continue
            if line.strip().startswith('from __future__ import'):
                future_lines.append(line)
            else:
                other_lines.append((i, line))
        
        if not future_lines:
            return False
        
        # 重建文件：docstring + future imports + 其他内容
        new_lines = lines[:docstring_end]
        
        # 添加 future imports
        for future_line in future_lines:
            new_lines.append(future_line)
        
        # 添加空行（如果需要）
        if future_lines and other_lines:
            new_lines.append('')
        
        # 添加其他内容（跳过原来的 future import 行）
        future_line_indices = set()
        for i, line in enumerate(lines):
            if i >= docstring_end and line.strip().startswith('from __future__ import'):
                future_line_indices.add(i)
        
        for i, line in enumerate(lines[docstring_end:], docstring_end):
            if i not in future_line_indices:
                new_lines.append(line)
        
        new_content = '\n'.join(new_lines)
        
        # 只有内容改变时才写入
        if new_content != content:
            file_path.write_text(new_content, encoding='utf-8')
            return True
        
        return False
        
    except Exception as e:
        print(f"Error processing {file_path}: {e}")
        return False


def main():
    """主函数"""
    backend_dir = Path(__file__).parent.parent
    apps_dir = backend_dir / 'apps'
    
    fixed_count = 0
    
    for py_file in apps_dir.rglob('*.py'):
        if fix_future_import(py_file):
            print(f"Fixed: {py_file.relative_to(backend_dir)}")
            fixed_count += 1
    
    print(f"\nTotal fixed: {fixed_count} files")


if __name__ == '__main__':
    main()
