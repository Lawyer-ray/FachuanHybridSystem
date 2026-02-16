#!/usr/bin/env python3
"""
批量修复剩余的 mypy 类型错误
优先修复：unused-ignore, no-untyped-def, type-arg
"""
import re
import sys
from pathlib import Path
from typing import Set

def remove_unused_ignores(file_path: Path) -> int:
    """删除不需要的 type: ignore 注释"""
    content = file_path.read_text()
    original = content
    
    # 删除单独一行的 # type: ignore
    content = re.sub(r'^\s*# type: ignore.*\n', '', content, flags=re.MULTILINE)
    
    # 删除行尾多余的 type: ignore（保留有具体错误码的）
    # 只删除通用的 # type: ignore，保留 # type: ignore[error-code]
    content = re.sub(r'(\S)\s+# type: ignore\s*$', r'\1', content, flags=re.MULTILINE)
    
    if content != original:
        file_path.write_text(content)
        return 1
    return 0

def add_function_return_types(file_path: Path) -> int:
    """为缺少返回类型的函数添加 -> None"""
    content = file_path.read_text()
    original = content
    changes = 0
    
    lines = content.split('\n')
    new_lines = []
    
    for i, line in enumerate(lines):
        # 匹配函数定义：def func(...): 但没有 ->
        if re.match(r'^\s*def\s+\w+\s*\([^)]*\)\s*:', line) and '->' not in line:
            # 不是 __init__, __str__, __repr__ 等特殊方法
            if not re.search(r'def\s+__(init|str|repr|eq|hash|bool)__', line):
                # 在 ): 之前插入 -> None
                line = re.sub(r'\):', r') -> None:', line)
                changes += 1
        
        new_lines.append(line)
    
    if changes > 0:
        content = '\n'.join(new_lines)
        file_path.write_text(content)
    
    return changes

def fix_generic_types(file_path: Path) -> int:
    """修复泛型类型参数缺失"""
    content = file_path.read_text()
    original = content
    changes = 0
    
    # 确保导入 Any
    if 'from typing import' in content and 'Any' not in content:
        content = re.sub(
            r'from typing import ([^\n]+)',
            r'from typing import \1, Any',
            content,
            count=1
        )
        changes += 1
    elif 'from typing import' not in content and ('dict[' in content or 'list[' in content):
        # 在第一个 import 后添加
        content = re.sub(
            r'(^import [^\n]+\n)',
            r'\1from typing import Any\n',
            content,
            count=1,
            flags=re.MULTILINE
        )
        changes += 1
    
    # 修复返回类型中的泛型
    replacements = [
        (r'-> dict\b', '-> dict[str, Any]'),
        (r'-> list\b', '-> list[Any]'),
        (r'-> set\b', '-> set[Any]'),
        (r'-> tuple\b', '-> tuple[Any, ...]'),
    ]
    
    for pattern, replacement in replacements:
        new_content = re.sub(pattern, replacement, content)
        if new_content != content:
            changes += 1
            content = new_content
    
    # 修复参数类型中的泛型
    replacements = [
        (r': dict\s*=', ': dict[str, Any] ='),
        (r': list\s*=', ': list[Any] ='),
        (r': set\s*=', ': set[Any] ='),
    ]
    
    for pattern, replacement in replacements:
        new_content = re.sub(pattern, replacement, content)
        if new_content != content:
            changes += 1
            content = new_content
    
    if content != original:
        file_path.write_text(content)
    
    return changes

def add_attr_defined_ignores(file_path: Path) -> int:
    """为 Django ORM 动态属性添加 type: ignore[attr-defined]"""
    content = file_path.read_text()
    original = content
    changes = 0
    
    # 常见的 Django ORM 动态属性
    orm_attrs = ['id', 'pk', 'objects', 'DoesNotExist', 'MultipleObjectsReturned']
    
    lines = content.split('\n')
    new_lines = []
    
    for line in lines:
        modified = False
        # 检查是否访问了 ORM 动态属性且没有 type: ignore
        for attr in orm_attrs:
            pattern = rf'\.{attr}\b'
            if re.search(pattern, line) and 'type: ignore' not in line:
                # 在行尾添加 # type: ignore[attr-defined]
                line = line.rstrip() + '  # type: ignore[attr-defined]'
                changes += 1
                modified = True
                break
        
        new_lines.append(line)
    
    if changes > 0:
        content = '\n'.join(new_lines)
        file_path.write_text(content)
    
    return changes

def main():
    apps_dir = Path('apps')
    if not apps_dir.exists():
        print("错误：apps 目录不存在")
        sys.exit(1)
    
    # 获取所有 Python 文件
    py_files = list(apps_dir.rglob('*.py'))
    
    print(f"找到 {len(py_files)} 个 Python 文件")
    
    stats = {
        'unused_ignores': 0,
        'return_types': 0,
        'generic_types': 0,
        'attr_defined': 0,
        'files_modified': 0
    }
    
    for py_file in py_files:
        file_changes = 0
        
        # 1. 删除不需要的 type: ignore
        file_changes += remove_unused_ignores(py_file)
        
        # 2. 添加函数返回类型
        changes = add_function_return_types(py_file)
        stats['return_types'] += changes
        file_changes += changes
        
        # 3. 修复泛型类型
        changes = fix_generic_types(py_file)
        stats['generic_types'] += changes
        file_changes += changes
        
        # 4. 添加 attr-defined ignores
        changes = add_attr_defined_ignores(py_file)
        stats['attr_defined'] += changes
        file_changes += changes
        
        if file_changes > 0:
            stats['files_modified'] += 1
            print(f"✓ {py_file}")
    
    print("\n修复统计：")
    print(f"  删除 unused-ignore: {stats['unused_ignores']} 处")
    print(f"  添加返回类型: {stats['return_types']} 处")
    print(f"  修复泛型类型: {stats['generic_types']} 处")
    print(f"  添加 attr-defined ignore: {stats['attr_defined']} 处")
    print(f"  修改文件数: {stats['files_modified']} 个")

if __name__ == '__main__':
    main()
