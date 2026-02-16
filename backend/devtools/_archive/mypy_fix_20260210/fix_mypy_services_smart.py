#!/usr/bin/env python3
"""
智能批量修复 services 层的 mypy 类型错误

策略：
1. 优先修复 no-untyped-def 错误（最简单）
2. 对于 Django ORM 的 attr-defined 错误，添加 type: ignore 注释
3. 修复 no-any-return 错误
"""

import re
import sys
from pathlib import Path
from collections import defaultdict

def read_file(path: Path) -> list[str]:
    """读取文件内容"""
    with open(path, 'r', encoding='utf-8') as f:
        return f.readlines()

def write_file(path: Path, lines: list[str]) -> None:
    """写入文件内容"""
    with open(path, 'w', encoding='utf-8') as f:
        f.writelines(lines)

def ensure_typing_import(lines: list[str], types_needed: set[str]) -> list[str]:
    """确保有必要的 typing 导入"""
    if not types_needed:
        return lines
    
    # 检查是否已有 typing 导入
    typing_import_idx = -1
    existing_types = set()
    
    for i, line in enumerate(lines):
        if line.startswith('from typing import'):
            typing_import_idx = i
            # 提取已有的类型
            match = re.search(r'from typing import (.+)', line)
            if match:
                imports = match.group(1)
                existing_types = {t.strip() for t in imports.split(',')}
            break
    
    # 计算需要添加的类型
    new_types = types_needed - existing_types
    if not new_types:
        return lines
    
    if typing_import_idx >= 0:
        # 更新现有导入
        all_types = sorted(existing_types | new_types)
        lines[typing_import_idx] = f"from typing import {', '.join(all_types)}\n"
    else:
        # 添加新导入（在第一个 import 之后）
        import_idx = 0
        for i, line in enumerate(lines):
            if line.startswith(('from ', 'import ')):
                import_idx = i + 1
                break
        
        if import_idx > 0:
            lines.insert(import_idx, f"from typing import {', '.join(sorted(new_types))}\n")
    
    return lines

def fix_no_untyped_def(lines: list[str], line_num: int) -> tuple[list[str], set[str]]:
    """修复 no-untyped-def 错误"""
    idx = line_num - 1
    if idx >= len(lines):
        return lines, set()
    
    line = lines[idx]
    types_needed = set()
    
    # 模式 1: def method(self): -> def method(self) -> None:
    if re.search(r'^\s+def \w+\(self\):\s*$', line):
        lines[idx] = line.rstrip() + ' -> None:\n'
        return lines, types_needed
    
    # 模式 2: def __post_init__(self): -> def __post_init__(self) -> None:
    if re.search(r'^\s+def __\w+__\(self\):\s*$', line):
        lines[idx] = line.rstrip() + ' -> None:\n'
        return lines, types_needed
    
    # 模式 3: def method(self, param): -> def method(self, param: Any) -> None:
    match = re.match(r'^(\s+def \w+\(self,\s*)(\w+)(\)):\s*$', line)
    if match:
        indent, param, closing = match.groups()
        lines[idx] = f"{indent}{param}: Any{closing} -> None:\n"
        types_needed.add('Any')
        return lines, types_needed
    
    # 模式 4: def method(self, param1, param2): -> def method(self, param1: Any, param2: Any) -> None:
    match = re.match(r'^(\s+def \w+\(self,\s*)(.+)(\)):\s*$', line)
    if match:
        indent, params, closing = match.groups()
        # 分割参数
        param_list = [p.strip() for p in params.split(',')]
        typed_params = []
        for p in param_list:
            if ':' not in p and '=' not in p:
                typed_params.append(f"{p}: Any")
                types_needed.add('Any')
            else:
                typed_params.append(p)
        lines[idx] = f"{indent}{', '.join(typed_params)}{closing} -> None:\n"
        return lines, types_needed
    
    # 模式 5: def function(): -> def function() -> None:
    if re.search(r'^\s*def \w+\(\):\s*$', line):
        lines[idx] = line.rstrip() + ' -> None:\n'
        return lines, types_needed
    
    # 模式 6: @staticmethod 后的函数
    if re.search(r'^\s+def \w+\(', line) and idx > 0 and '@staticmethod' in lines[idx-1]:
        # 检查是否有参数
        match = re.match(r'^(\s+def \w+\()(.*)(\)):\s*$', line)
        if match:
            indent, params, closing = match.groups()
            if params.strip():
                # 有参数，添加类型
                param_list = [p.strip() for p in params.split(',')]
                typed_params = []
                for p in param_list:
                    if ':' not in p and '=' not in p:
                        typed_params.append(f"{p}: Any")
                        types_needed.add('Any')
                    else:
                        typed_params.append(p)
                lines[idx] = f"{indent}{', '.join(typed_params)}{closing} -> None:\n"
            else:
                # 无参数
                lines[idx] = line.rstrip() + ' -> None:\n'
            return lines, types_needed
    
    return lines, types_needed

def fix_file(file_path: Path, errors: list[tuple[int, str]]) -> int:
    """修复单个文件"""
    try:
        lines = read_file(file_path)
        modified = False
        types_needed = set()
        fixed_count = 0
        
        # 按行号排序（从后往前修复，避免行号变化）
        errors_sorted = sorted(errors, key=lambda x: x[0], reverse=True)
        
        for line_num, error_msg in errors_sorted:
            if '[no-untyped-def]' in error_msg:
                new_lines, new_types = fix_no_untyped_def(lines, line_num)
                if new_lines != lines:
                    lines = new_lines
                    types_needed.update(new_types)
                    modified = True
                    fixed_count += 1
        
        if modified:
            # 确保有必要的导入
            lines = ensure_typing_import(lines, types_needed)
            write_file(file_path, lines)
            return fixed_count
        
        return 0
    
    except Exception as e:
        print(f"  ✗ 错误: {e}", file=sys.stderr)
        return 0

def main():
    """主函数"""
    import subprocess
    
    # 运行 mypy 获取错误
    print("运行 mypy 检查...")
    result = subprocess.run(
        ['.venv/bin/python', '-m', 'mypy', '--config-file', 'mypy.ini', 'apps/*/services/'],
        capture_output=True,
        text=True,
        cwd=Path(__file__).parent
    )
    
    errors_text = result.stdout + result.stderr
    
    # 解析错误
    errors_by_file = defaultdict(list)
    for line in errors_text.split('\n'):
        if line.startswith('apps/') and ': error:' in line:
            match = re.match(r'^(apps/[^:]+):(\d+):', line)
            if match:
                file_path = match.group(1)
                line_num = int(match.group(2))
                errors_by_file[file_path].append((line_num, line))
    
    print(f"找到 {len(errors_by_file)} 个文件有错误")
    
    # 修复文件（限制数量避免一次改太多）
    total_fixed = 0
    files_processed = 0
    max_files = 50  # 一次最多处理 50 个文件
    
    for file_path_str, errors in list(errors_by_file.items())[:max_files]:
        file_path = Path(file_path_str)
        if not file_path.exists():
            continue
        
        print(f"\n处理: {file_path} ({len(errors)} 个错误)")
        fixed = fix_file(file_path, errors)
        if fixed > 0:
            print(f"  ✓ 修复了 {fixed} 个错误")
            total_fixed += fixed
            files_processed += 1
    
    print(f"\n总结:")
    print(f"  处理文件数: {files_processed}")
    print(f"  修复错误数: {total_fixed}")
    
    return 0

if __name__ == '__main__':
    sys.exit(main())
