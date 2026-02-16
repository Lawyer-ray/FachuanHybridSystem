#!/usr/bin/env python3
"""修复最关键的类型错误"""
import re
from pathlib import Path

def fix_file(file_path: Path) -> int:
    """修复单个文件"""
    try:
        content = file_path.read_text()
        original = content
        
        # 1. 为简单函数添加 -> None
        # 匹配 def func(): 但不匹配已有 -> 的
        lines = content.split('\n')
        new_lines = []
        for line in lines:
            if (re.match(r'^\s*def\s+\w+\s*\([^)]*\)\s*:\s*$', line) and 
                '->' not in line and
                not re.search(r'def\s+__(init|str|repr|eq)__', line)):
                line = re.sub(r'\):\s*$', r') -> None:', line)
            new_lines.append(line)
        content = '\n'.join(new_lines)
        
        # 2. 修复常见泛型类型
        content = re.sub(r'-> dict\s*:', '-> dict[str, Any]:', content)
        content = re.sub(r'-> list\s*:', '-> list[Any]:', content)
        content = re.sub(r': dict\s*=\s*{', ': dict[str, Any] = {', content)
        content = re.sub(r': list\s*=\s*\[', ': list[Any] = [', content)
        
        # 3. 确保导入 Any
        if ('dict[str, Any]' in content or 'list[Any]' in content) and 'from typing import' in content:
            if ', Any' not in content and 'Any,' not in content and 'import Any' not in content:
                content = re.sub(
                    r'from typing import ([^\n]+)',
                    lambda m: f"from typing import {m.group(1)}, Any" if 'Any' not in m.group(1) else m.group(0),
                    content,
                    count=1
                )
        
        if content != original:
            file_path.write_text(content)
            return 1
        return 0
    except Exception as e:
        print(f"错误处理 {file_path}: {e}")
        return 0

def main():
    apps_dir = Path('apps')
    py_files = list(apps_dir.rglob('*.py'))
    
    modified = 0
    for py_file in py_files:
        if fix_file(py_file):
            modified += 1
            if modified % 10 == 0:
                print(f"已修改 {modified} 个文件...")
    
    print(f"\n完成！共修改 {modified} 个文件")

if __name__ == '__main__':
    main()
