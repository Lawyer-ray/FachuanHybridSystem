#!/usr/bin/env python3
"""修复缺少 import logging 的文件"""
import os
import re
import sys

def fix_file(filepath):
    """修复单个文件"""
    try:
        with open(filepath, 'r', encoding='utf-8') as f:
            content = f.read()
        
        # 检查是否有 logger = logging.getLogger
        if 'logger = logging.getLogger' not in content:
            return False
        
        # 检查是否已经有 import logging
        if re.search(r'^import logging', content, re.MULTILINE):
            return False
        if re.search(r'^from.*import.*logging', content, re.MULTILINE):
            return False
        
        # 找到第一个 import 语句的位置
        lines = content.split('\n')
        insert_pos = -1
        
        # 跳过文档字符串和注释
        in_docstring = False
        docstring_char = None
        
        for i, line in enumerate(lines):
            stripped = line.strip()
            
            # 处理文档字符串
            if stripped.startswith('"""') or stripped.startswith("'''"):
                if not in_docstring:
                    docstring_char = stripped[:3]
                    in_docstring = True
                    if stripped.endswith(docstring_char) and len(stripped) > 6:
                        in_docstring = False
                elif stripped.endswith(docstring_char):
                    in_docstring = False
                continue
            
            if in_docstring:
                continue
            
            # 找到第一个 import 语句
            if stripped.startswith('import ') or stripped.startswith('from '):
                insert_pos = i
                break
        
        if insert_pos == -1:
            print(f"跳过 {filepath}: 找不到 import 语句位置")
            return False
        
        # 插入 import logging
        lines.insert(insert_pos, 'import logging')
        new_content = '\n'.join(lines)
        
        # 写回文件
        with open(filepath, 'w', encoding='utf-8') as f:
            f.write(new_content)
        
        print(f"✓ 修复 {filepath}")
        return True
        
    except Exception as e:
        print(f"✗ 错误 {filepath}: {e}")
        return False

def main():
    """主函数"""
    # 查找所有需要修复的文件
    import subprocess
    
    result = subprocess.run(
        ['find', 'apps/', '-name', '*.py', '-type', 'f'],
        capture_output=True,
        text=True
    )
    
    files_to_check = result.stdout.strip().split('\n')
    fixed_count = 0
    
    for filepath in files_to_check:
        if not filepath:
            continue
        
        try:
            with open(filepath, 'r', encoding='utf-8') as f:
                content = f.read()
            
            # 检查是否需要修复
            if 'logger = logging.getLogger' in content:
                if not re.search(r'^import logging', content, re.MULTILINE):
                    if fix_file(filepath):
                        fixed_count += 1
        except Exception:
            continue
    
    print(f"\n总共修复了 {fixed_count} 个文件")

if __name__ == '__main__':
    main()
