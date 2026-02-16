#!/usr/bin/env python3
"""
批量修复 services 层的简单类型注解错误

策略：
1. 修复 any -> Any
2. 修复 __init__ 缺少 -> None
3. 修复空列表/字典的类型注解
"""

import re
from pathlib import Path
from typing import List


def fix_any_to_Any(file_path: Path) -> int:
    """修复 any -> Any"""
    content = file_path.read_text()
    original = content
    
    # 检查是否需要修复
    if ': any' not in content and ', any' not in content:
        return 0
    
    # 确保导入了 Any
    has_any_import = 'from typing import' in content and 'Any' in content
    
    if not has_any_import:
        # 在第一个 import 后添加 Any 导入
        lines = content.split('\n')
        for i, line in enumerate(lines):
            if line.startswith('from typing import'):
                # 已有 typing 导入，添加 Any
                if 'Any' not in line:
                    lines[i] = line.rstrip() + ', Any'
                break
            elif line.startswith('from ') or line.startswith('import '):
                # 在第一个 import 前插入
                lines.insert(i, 'from typing import Any')
                break
        content = '\n'.join(lines)
    
    # 替换 any 为 Any
    content = re.sub(r'\b: any\b', ': Any', content)
    content = re.sub(r'\b, any\b', ', Any', content)
    
    if content != original:
        file_path.write_text(content)
        return 1
    return 0


def fix_init_return_type(file_path: Path) -> int:
    """修复 __init__ 缺少 -> None"""
    content = file_path.read_text()
    original = content
    
    # 修复 def __init__(...): 为 def __init__(...) -> None:
    # 但不修复已经有 -> 的
    pattern = r'def __init__\(([^)]*)\):'
    
    def replace_init(match):
        params = match.group(1)
        # 检查是否已经有返回类型
        full_match = match.group(0)
        if '->' in full_match:
            return full_match
        return f'def __init__({params}) -> None:'
    
    content = re.sub(pattern, replace_init, content)
    
    if content != original:
        file_path.write_text(content)
        return 1
    return 0


def fix_empty_collections(file_path: Path) -> int:
    """修复空列表和空字典的类型注解"""
    content = file_path.read_text()
    original = content
    lines = content.split('\n')
    modified = False
    
    for i, line in enumerate(lines):
        # 跳过注释和字符串
        if line.strip().startswith('#') or line.strip().startswith('"""') or line.strip().startswith("'''"):
            continue
        
        # 修复 var = []
        if ' = []' in line and ':' not in line.split('=')[0]:
            # 提取变量名和缩进
            match = re.search(r'^(\s*)([a-zA-Z_][a-zA-Z0-9_]*)\s*=\s*\[\]', line)
            if match:
                indent, var_name = match.groups()
                lines[i] = f'{indent}{var_name}: list = []'
                modified = True
        
        # 修复 var = {}
        if ' = {}' in line and ':' not in line.split('=')[0]:
            match = re.search(r'^(\s*)([a-zA-Z_][a-zA-Z0-9_]*)\s*=\s*\{\}', line)
            if match:
                indent, var_name = match.groups()
                lines[i] = f'{indent}{var_name}: dict = {{}}'
                modified = True
    
    if modified:
        file_path.write_text('\n'.join(lines))
        return 1
    return 0


def main():
    """主函数"""
    service_dirs = [
        Path('apps/automation/services'),
        Path('apps/cases/services'),
        Path('apps/client/services'),
        Path('apps/contracts/services'),
        Path('apps/documents/services'),
    ]
    
    all_files: List[Path] = []
    for service_dir in service_dirs:
        if service_dir.exists():
            all_files.extend(service_dir.rglob('*.py'))
    
    print(f"找到 {len(all_files)} 个 Python 文件")
    
    # 修复 any -> Any
    print("\n1. 修复 any -> Any...")
    fixed_any = 0
    for file_path in all_files:
        if fix_any_to_Any(file_path):
            fixed_any += 1
            print(f"  ✓ {file_path}")
    print(f"修复了 {fixed_any} 个文件")
    
    # 修复 __init__ 返回类型
    print("\n2. 修复 __init__ 缺少 -> None...")
    fixed_init = 0
    for file_path in all_files:
        if fix_init_return_type(file_path):
            fixed_init += 1
            print(f"  ✓ {file_path}")
    print(f"修复了 {fixed_init} 个文件")
    
    # 修复空集合
    print("\n3. 修复空列表和空字典的类型注解...")
    fixed_collections = 0
    for file_path in all_files:
        if fix_empty_collections(file_path):
            fixed_collections += 1
            print(f"  ✓ {file_path}")
    print(f"修复了 {fixed_collections} 个文件")
    
    print(f"\n总计修复了 {fixed_any + fixed_init + fixed_collections} 个文件")


if __name__ == '__main__':
    main()
