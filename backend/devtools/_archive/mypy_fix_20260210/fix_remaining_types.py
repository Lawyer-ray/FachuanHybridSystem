#!/usr/bin/env python3
"""
修复剩余的 no-untyped-def 错误

策略：
1. 为缺少类型注解的函数参数添加 Any
2. 为缺少返回类型的函数添加 -> None 或 -> Any
"""

import re
import subprocess
from pathlib import Path
from collections import defaultdict

def get_mypy_errors():
    """运行 mypy 并获取错误"""
    result = subprocess.run(
        ['.venv/bin/python', '-m', 'mypy', '--config-file', 'mypy.ini', 'apps/*/services/'],
        capture_output=True,
        text=True,
        cwd=Path(__file__).parent
    )
    return result.stdout + result.stderr

def parse_errors(errors_text):
    """解析 mypy 错误"""
    errors_by_file = defaultdict(list)
    
    for line in errors_text.split('\n'):
        if '[no-untyped-def]' in line and line.startswith('apps/'):
            match = re.match(r'^(apps/[^:]+):(\d+):', line)
            if match:
                file_path = match.group(1)
                line_num = int(match.group(2))
                errors_by_file[file_path].append((line_num, line))
    
    return errors_by_file

def fix_function_signature(line: str) -> tuple[str, bool, set[str]]:
    """
    修复函数签名
    
    返回: (修复后的行, 是否修改, 需要的类型导入)
    """
    types_needed = set()
    
    # 跳过已有返回类型的
    if ' -> ' in line:
        return line, False, types_needed
    
    # 跳过 @property
    if '@property' in line:
        return line, False, types_needed
    
    # 模式 1: def method(self, param1, param2, ...):
    match = re.match(r'^(\s+def \w+\()(self(?:,\s*.+)?)(\)):\s*$', line)
    if match:
        indent, params, closing = match.groups()
        
        # 分析参数
        param_parts = [p.strip() for p in params.split(',')]
        new_params = []
        
        for param in param_parts:
            if param == 'self':
                new_params.append('self')
            elif ':' in param or '=' in param:
                # 已有类型注解或默认值
                new_params.append(param)
            else:
                # 需要添加类型
                new_params.append(f"{param}: Any")
                types_needed.add('Any')
        
        new_line = f"{indent}{', '.join(new_params)}{closing} -> None:\n"
        return new_line, True, types_needed
    
    # 模式 2: def function(param1, param2):
    match = re.match(r'^(\s*def \w+\()(.+)(\)):\s*$', line)
    if match and 'self' not in line:
        indent, params, closing = match.groups()
        
        param_parts = [p.strip() for p in params.split(',')]
        new_params = []
        
        for param in param_parts:
            if ':' in param or '=' in param:
                new_params.append(param)
            else:
                new_params.append(f"{param}: Any")
                types_needed.add('Any')
        
        new_line = f"{indent}{', '.join(new_params)}{closing} -> None:\n"
        return new_line, True, types_needed
    
    # 模式 3: def method(self):
    if re.match(r'^\s+def \w+\(self\):\s*$', line):
        return line.rstrip() + ' -> None:\n', True, types_needed
    
    # 模式 4: def function():
    if re.match(r'^\s*def \w+\(\):\s*$', line):
        return line.rstrip() + ' -> None:\n', True, types_needed
    
    return line, False, types_needed

def ensure_typing_imports(lines: list[str], types_needed: set[str]) -> list[str]:
    """确保有必要的 typing 导入"""
    if not types_needed:
        return lines
    
    # 查找现有的 typing 导入
    typing_line_idx = -1
    existing_types = set()
    
    for i, line in enumerate(lines):
        if line.startswith('from typing import'):
            typing_line_idx = i
            # 提取已有类型
            match = re.search(r'from typing import (.+)', line)
            if match:
                imports_str = match.group(1).strip()
                # 处理多行导入
                if '(' in imports_str:
                    imports_str = imports_str.replace('(', '').replace(')', '')
                existing_types = {t.strip() for t in imports_str.split(',')}
            break
    
    # 计算需要添加的类型
    new_types = types_needed - existing_types
    if not new_types:
        return lines
    
    if typing_line_idx >= 0:
        # 更新现有导入
        all_types = sorted(existing_types | new_types)
        lines[typing_line_idx] = f"from typing import {', '.join(all_types)}\n"
    else:
        # 添加新导入
        # 找到第一个非 __future__ 的 import
        insert_idx = 0
        for i, line in enumerate(lines):
            if line.startswith(('from ', 'import ')) and '__future__' not in line:
                insert_idx = i + 1
                break
        
        if insert_idx > 0:
            lines.insert(insert_idx, f"from typing import {', '.join(sorted(new_types))}\n")
    
    return lines

def fix_file(file_path: Path, errors: list[tuple[int, str]]) -> int:
    """修复单个文件"""
    if not file_path.exists():
        return 0
    
    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            lines = f.readlines()
        
        modified = False
        fixed_count = 0
        all_types_needed = set()
        
        # 按行号排序（从后往前，避免行号变化）
        errors_sorted = sorted(errors, key=lambda x: x[0], reverse=True)
        
        for line_num, error_msg in errors_sorted:
            idx = line_num - 1
            if idx >= len(lines):
                continue
            
            new_line, changed, types_needed = fix_function_signature(lines[idx])
            if changed:
                lines[idx] = new_line
                all_types_needed.update(types_needed)
                modified = True
                fixed_count += 1
        
        if modified:
            lines = ensure_typing_imports(lines, all_types_needed)
            
            with open(file_path, 'w', encoding='utf-8') as f:
                f.writelines(lines)
            
            return fixed_count
        
        return 0
    
    except Exception as e:
        print(f"✗ {file_path}: {e}")
        return 0

def main():
    """主函数"""
    print("获取 mypy 错误...")
    errors_text = get_mypy_errors()
    
    errors_by_file = parse_errors(errors_text)
    print(f"找到 {len(errors_by_file)} 个文件有 no-untyped-def 错误\n")
    
    total_fixed = 0
    files_processed = 0
    max_files = 100  # 一次处理 100 个文件
    
    for file_path_str, errors in list(errors_by_file.items())[:max_files]:
        file_path = Path(file_path_str)
        fixed = fix_file(file_path, errors)
        
        if fixed > 0:
            print(f"✓ {file_path.name}: 修复 {fixed} 处")
            total_fixed += fixed
            files_processed += 1
    
    print(f"\n总结:")
    print(f"  处理文件: {files_processed}")
    print(f"  修复错误: {total_fixed}")

if __name__ == '__main__':
    main()
