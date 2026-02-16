#!/usr/bin/env python3
"""
修复自动添加类型注解时产生的重复定义问题
"""

from pathlib import Path
import re

def fix_duplicate_class_def(content: str) -> str:
    """修复重复的类定义"""
    # 模式: class Name(Base[Type]):\nclass Name(Base):
    pattern = r'class (\w+)\([^)]+\[([^\]]+)\]\):\s*\nclass \1\([^)]+\):'
    
    def replace_func(match):
        class_name = match.group(1)
        # 保留第二个定义(没有泛型的)
        return f'class {class_name}({match.group(0).split("class " + class_name)[2].split(":")[0]}):'
    
    content = re.sub(pattern, replace_func, content)
    
    # 更简单的模式: 连续两行相同的 class 定义
    lines = content.split('\n')
    new_lines = []
    i = 0
    while i < len(lines):
        line = lines[i]
        if line.strip().startswith('class ') and i + 1 < len(lines):
            next_line = lines[i + 1]
            if next_line.strip().startswith('class '):
                # 检查是否是同一个类
                class_name1 = re.search(r'class (\w+)', line)
                class_name2 = re.search(r'class (\w+)', next_line)
                if class_name1 and class_name2 and class_name1.group(1) == class_name2.group(1):
                    # 跳过第一个定义,保留第二个
                    i += 1
                    continue
        new_lines.append(line)
        i += 1
    
    return '\n'.join(new_lines)

def fix_duplicate_func_def(content: str) -> str:
    """修复重复的函数定义"""
    lines = content.split('\n')
    new_lines = []
    i = 0
    while i < len(lines):
        line = lines[i]
        if line.strip().startswith('def ') and i + 1 < len(lines):
            next_line = lines[i + 1]
            if next_line.strip().startswith('def '):
                # 检查是否是同一个函数
                func_name1 = re.search(r'def (\w+)', line)
                func_name2 = re.search(r'def (\w+)', next_line)
                if func_name1 and func_name2 and func_name1.group(1) == func_name2.group(1):
                    # 如果第一个有类型注解,保留第一个;否则保留第二个
                    if '->' in line or ': ' in line:
                        # 保留第一个,跳过第二个
                        new_lines.append(line)
                        i += 2
                        continue
                    else:
                        # 跳过第一个,保留第二个
                        i += 1
                        continue
        new_lines.append(line)
        i += 1
    
    return '\n'.join(new_lines)

def fix_file(file_path: Path) -> bool:
    """修复单个文件"""
    try:
        content = file_path.read_text()
        original = content
        
        content = fix_duplicate_class_def(content)
        content = fix_duplicate_func_def(content)
        
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
