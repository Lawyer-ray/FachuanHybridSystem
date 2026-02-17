#!/usr/bin/env python3
"""综合批量修复脚本 - 一次性处理多种错误类型"""
import re
import subprocess
from pathlib import Path
from typing import Dict, List, Tuple, Set
from collections import defaultdict


def run_mypy() -> str:
    """运行mypy并返回输出"""
    result = subprocess.run(
        [".venv/bin/python", "-m", "mypy", "--strict", "apps/"],
        capture_output=True,
        text=True,
        cwd=Path(__file__).parent.parent.parent
    )
    return result.stderr


def parse_errors(output: str) -> Dict[str, List[Tuple[str, int, str]]]:
    """解析mypy输出，按错误类型分组"""
    errors = defaultdict(list)
    
    for line in output.split('\n'):
        if ': error:' in line:
            # 解析: apps/path/file.py:123: error: Message [error-code]
            match = re.match(r'(apps/[^:]+):(\d+):\s*error:\s*(.+?)(?:\s*\[([a-z-]+)\])?$', line)
            if match:
                file_path = match.group(1)
                line_num = int(match.group(2))
                message = match.group(3).strip()
                error_code = match.group(4) if match.group(4) else 'unknown'
                errors[error_code].append((file_path, line_num, message))
    
    return errors


def fix_unused_ignore(file_path: str, line_numbers: List[int]) -> int:
    """移除unused type: ignore注释"""
    full_path = Path(__file__).parent.parent.parent / file_path
    
    with open(full_path, 'r', encoding='utf-8') as f:
        lines = f.readlines()
    
    line_nums_set = set(line_numbers)
    fixed = 0
    
    for i, line in enumerate(lines, 1):
        if i in line_nums_set and 'type: ignore' in line:
            # 移除 # type: ignore[...] 或 # type: ignore
            new_line = re.sub(r'\s*#\s*type:\s*ignore(?:\[[^\]]+\])?\s*$', '\n', line)
            if new_line != line:
                lines[i-1] = new_line
                fixed += 1
    
    if fixed > 0:
        with open(full_path, 'w', encoding='utf-8') as f:
            f.writelines(lines)
    
    return fixed


def fix_init_return_type(file_path: str, line_numbers: List[int]) -> int:
    """为__init__方法添加-> None"""
    full_path = Path(__file__).parent.parent.parent / file_path
    
    with open(full_path, 'r', encoding='utf-8') as f:
        lines = f.readlines()
    
    line_nums_set = set(line_numbers)
    fixed = 0
    
    for i, line in enumerate(lines, 1):
        if i in line_nums_set and 'def __init__' in line and '->' not in line:
            match = re.match(r'(\s*def __init__\([^)]*\))(\s*:.*)' , line)
            if match:
                lines[i-1] = f"{match.group(1)} -> None{match.group(2)}"
                fixed += 1
    
    if fixed > 0:
        with open(full_path, 'w', encoding='utf-8') as f:
            f.writelines(lines)
    
    return fixed


def fix_method_return_type(file_path: str, line_numbers: List[int]) -> int:
    """为其他方法添加-> None（保守策略）"""
    full_path = Path(__file__).parent.parent.parent / file_path
    
    with open(full_path, 'r', encoding='utf-8') as f:
        lines = f.readlines()
    
    line_nums_set = set(line_numbers)
    fixed = 0
    
    for i, line in enumerate(lines, 1):
        if i not in line_nums_set:
            continue
            
        # 跳过已有返回类型的
        if '->' in line:
            continue
            
        # 跳过非def开头的
        if not line.strip().startswith('def '):
            continue
            
        # 检查前面是否有装饰器（property, staticmethod, classmethod）
        skip = False
        for j in range(max(0, i-4), i):
            prev_line = lines[j].strip()
            if prev_line.startswith('@property') or prev_line.startswith('@staticmethod') or prev_line.startswith('@classmethod'):
                skip = True
                break
        
        if skip:
            continue
        
        # 添加-> None
        match = re.match(r'(\s*def\s+\w+\([^)]*\))(\s*:.*)' , line)
        if match:
            lines[i-1] = f"{match.group(1)} -> None{match.group(2)}"
            fixed += 1
    
    if fixed > 0:
        with open(full_path, 'w', encoding='utf-8') as f:
            f.writelines(lines)
    
    return fixed


def add_missing_any_import(file_path: str) -> bool:
    """添加缺失的Any导入"""
    full_path = Path(__file__).parent.parent.parent / file_path
    
    with open(full_path, 'r', encoding='utf-8') as f:
        content = f.read()
    
    # 检查是否使用了Any但没有导入
    if 'Any' not in content:
        return False
    
    # 检查是否已经导入
    if re.search(r'from typing import.*\bAny\b', content):
        return False
    if re.search(r'import typing', content):
        return False
    
    # 查找现有的typing导入
    typing_import_match = re.search(r'(from typing import [^\n]+)', content)
    
    if typing_import_match:
        # 添加Any到现有导入
        old_import = typing_import_match.group(1)
        if old_import.endswith(')'):
            # 多行导入
            new_import = old_import.replace(')', ', Any)')
        else:
            # 单行导入
            new_import = old_import + ', Any'
        
        content = content.replace(old_import, new_import)
    else:
        # 添加新的导入行（在第一个import之后）
        import_match = re.search(r'(^import [^\n]+\n)', content, re.MULTILINE)
        if import_match:
            insert_pos = import_match.end()
            content = content[:insert_pos] + 'from typing import Any\n' + content[insert_pos:]
        else:
            # 在文件开头添加
            content = 'from typing import Any\n\n' + content
    
    with open(full_path, 'w', encoding='utf-8') as f:
        f.write(content)
    
    return True


def main():
    print("运行mypy分析错误...")
    output = run_mypy()
    errors = parse_errors(output)
    
    total_errors = sum(len(v) for v in errors.values())
    print(f"\n总共 {total_errors} 个错误")
    print("\n错误分布:")
    for error_type, error_list in sorted(errors.items(), key=lambda x: len(x[1]), reverse=True)[:10]:
        print(f"  {error_type}: {len(error_list)}")
    
    total_fixed = 0
    
    # 1. 修复unused-ignore
    if 'unused-ignore' in errors:
        print(f"\n修复unused-ignore错误 ({len(errors['unused-ignore'])}个)...")
        by_file = defaultdict(list)
        for file_path, line_num, _ in errors['unused-ignore']:
            by_file[file_path].append(line_num)
        
        for file_path, line_numbers in by_file.items():
            fixed = fix_unused_ignore(file_path, line_numbers)
            if fixed > 0:
                total_fixed += fixed
                print(f"  {file_path}: 修复{fixed}个")
    
    # 2. 修复no-untyped-def（__init__方法）
    if 'no-untyped-def' in errors:
        init_errors = [(f, l, m) for f, l, m in errors['no-untyped-def'] 
                       if '__init__' in m.lower() or 'missing a return type' in m.lower()]
        
        if init_errors:
            print(f"\n修复__init__方法的no-untyped-def错误 ({len(init_errors)}个)...")
            by_file = defaultdict(list)
            for file_path, line_num, _ in init_errors:
                by_file[file_path].append(line_num)
            
            for file_path, line_numbers in by_file.items():
                fixed = fix_init_return_type(file_path, line_numbers)
                if fixed > 0:
                    total_fixed += fixed
                    print(f"  {file_path}: 修复{fixed}个")
    
    # 3. 修复no-untyped-def（其他方法，限制数量）
    if 'no-untyped-def' in errors:
        other_errors = [(f, l, m) for f, l, m in errors['no-untyped-def'] 
                        if '__init__' not in m.lower() and 'missing a return type' in m.lower()]
        
        if other_errors:
            # 限制一次处理50个文件
            by_file = defaultdict(list)
            for file_path, line_num, _ in other_errors[:200]:  # 限制200个错误
                by_file[file_path].append(line_num)
            
            print(f"\n修复其他方法的no-untyped-def错误 (处理前{len(by_file)}个文件)...")
            file_count = 0
            for file_path, line_numbers in sorted(by_file.items()):
                if file_count >= 50:
                    break
                fixed = fix_method_return_type(file_path, line_numbers)
                if fixed > 0:
                    total_fixed += fixed
                    file_count += 1
                    print(f"  {file_path}: 修复{fixed}个")
    
    # 4. 添加缺失的Any导入
    if 'name-defined' in errors:
        any_errors = [(f, l, m) for f, l, m in errors['name-defined'] if '"Any"' in m or "'Any'" in m]
        
        if any_errors:
            print(f"\n添加缺失的Any导入 ({len(any_errors)}个文件)...")
            files_to_fix = set(f for f, _, _ in any_errors)
            
            for file_path in files_to_fix:
                if add_missing_any_import(file_path):
                    total_fixed += 1
                    print(f"  {file_path}: 添加Any导入")
    
    print(f"\n总共修复了 {total_fixed} 个错误")
    print("\n重新运行mypy验证...")
    
    # 重新运行mypy
    output = run_mypy()
    errors = parse_errors(output)
    new_total = sum(len(v) for v in errors.values())
    
    print(f"\n修复后错误数: {new_total}")
    print(f"减少了: {total_errors - new_total} 个错误")


if __name__ == "__main__":
    main()
