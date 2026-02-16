#!/usr/bin/env python3
"""批量修复所有 list[Any] = [] 和 dict[str, Any] = {} 后跟元素的语法错误"""

import re
from pathlib import Path


def fix_list_dict_syntax(content: str) -> str:
    """修复列表和字典的语法错误"""
    lines = content.split('\n')
    fixed_lines: list[str] = []
    i = 0
    
    while i < len(lines):
        line = lines[i]
        
        # 检查是否是 list[Any] = [] 或 dict[str, Any] = {}
        list_match = re.match(r'^(\s+)(\w+):\s*list\[Any\]\s*=\s*\[\]\s*$', line)
        dict_match = re.match(r'^(\s+)(\w+):\s*dict\[str,\s*Any\]\s*=\s*\{\}\s*$', line)
        
        if list_match and i + 1 < len(lines):
            indent = list_match.group(1)
            var_name = list_match.group(2)
            next_line = lines[i + 1]
            
            # 检查下一行是否是元素（缩进更多）
            if next_line.strip() and len(next_line) - len(next_line.lstrip()) > len(indent):
                # 修复：将 [] 改为 [
                fixed_lines.append(f'{indent}{var_name}: list[Any] = [')
                i += 1
                continue
        
        elif dict_match and i + 1 < len(lines):
            indent = dict_match.group(1)
            var_name = dict_match.group(2)
            next_line = lines[i + 1]
            
            # 检查下一行是否是元素（缩进更多）
            if next_line.strip() and len(next_line) - len(next_line.lstrip()) > len(indent):
                # 修复：将 {} 改为 {
                fixed_lines.append(f'{indent}{var_name}: dict[str, Any] = {{')
                i += 1
                continue
        
        fixed_lines.append(line)
        i += 1
    
    return '\n'.join(fixed_lines)


def main() -> None:
    backend_path = Path(__file__).parent.parent
    apps_path = backend_path / 'apps'
    
    fixed_count = 0
    
    for py_file in apps_path.rglob('*.py'):
        try:
            content = py_file.read_text(encoding='utf-8')
            fixed_content = fix_list_dict_syntax(content)
            
            if content != fixed_content:
                py_file.write_text(fixed_content, encoding='utf-8')
                fixed_count += 1
                print(f"Fixed: {py_file.relative_to(backend_path)}")
        except Exception as e:
            print(f"Error processing {py_file}: {e}")
    
    print(f"\n总共修复了 {fixed_count} 个文件")


if __name__ == '__main__':
    main()
