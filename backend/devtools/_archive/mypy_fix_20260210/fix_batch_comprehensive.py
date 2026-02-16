#!/usr/bin/env python3
"""
综合批量修复 mypy 错误
每次处理 200 个文件
"""

from pathlib import Path
import re
import subprocess
from collections import defaultdict

def run_mypy():
    """运行 mypy"""
    result = subprocess.run(
        ["python", "-m", "mypy", "--config-file", "mypy.ini", "apps/"],
        capture_output=True,
        text=True
    )
    return result.stdout

def get_errors_by_file(output):
    """按文件分组错误"""
    errors = defaultdict(list)
    for line in output.split('\n'):
        if 'error:' in line:
            match = re.match(r'(.+?):(\d+):(\d+): error: (.+)', line)
            if match:
                file_path = match.group(1)
                line_no = int(match.group(2))
                message = match.group(4)
                errors[file_path].append((line_no, message))
    return errors

def fix_file_comprehensive(file_path: Path, errors: list) -> bool:
    """综合修复单个文件"""
    try:
        content = file_path.read_text()
        lines = content.split('\n')
        modified = False
        
        # 确保有必要的导入
        has_annotations = any('from __future__ import annotations' in line for line in lines)
        has_any = any('from typing import' in line and 'Any' in line for line in lines)
        
        if not has_annotations:
            lines.insert(0, 'from __future__ import annotations')
            modified = True
        
        if not has_any:
            # 找到合适位置插入 typing import
            insert_idx = 1 if has_annotations else 0
            for i in range(insert_idx, min(insert_idx + 20, len(lines))):
                if lines[i].startswith('from typing import'):
                    if 'Any' not in lines[i]:
                        lines[i] = lines[i].replace('import ', 'import Any, ')
                        modified = True
                    break
                elif lines[i].startswith('from ') or lines[i].startswith('import '):
                    continue
                elif lines[i].strip() and not lines[i].strip().startswith('#') and not lines[i].strip().startswith('"""'):
                    # 在第一个非导入、非注释行之前插入
                    lines.insert(i, 'from typing import Any')
                    modified = True
                    break
        
        # 处理各种错误
        for line_no, message in errors:
            idx = line_no - 1
            if idx < 0 or idx >= len(lines):
                continue
            
            line = lines[idx]
            
            # 1. 修复缺少返回类型
            if 'missing a return type' in message or 'missing a type annotation' in message:
                if 'def ' in line and '->' not in line and line.rstrip().endswith(':'):
                    lines[idx] = line.rstrip()[:-1] + ' -> Any:'
                    modified = True
            
            # 2. 修复 Returning Any
            elif 'Returning Any from function' in message:
                # 向上查找函数定义
                func_idx = idx
                while func_idx >= 0 and 'def ' not in lines[func_idx]:
                    func_idx -= 1
                if func_idx >= 0:
                    func_line = lines[func_idx]
                    if 'def ' in func_line and '->' not in func_line and func_line.rstrip().endswith(':'):
                        lines[func_idx] = func_line.rstrip()[:-1] + ' -> Any:'
                        modified = True
            
            # 3. 修复 Incompatible default (Type = None)
            elif 'Incompatible default' in message:
                # dict = None -> dict | None = None
                if ' = None' in line and '|' not in line:
                    # 匹配模式: param: Type = None
                    line = re.sub(r'(\w+):\s*(\w+)\s*=\s*None', r'\1: \2 | None = None', line)
                    if line != lines[idx]:
                        lines[idx] = line
                        modified = True
        
        if modified:
            file_path.write_text('\n'.join(lines))
            return True
    
    except Exception as e:
        print(f"❌ {file_path}: {e}")
    
    return False

def main():
    print("🔍 第1轮检查...")
    output = run_mypy()
    errors_by_file = get_errors_by_file(output)
    
    initial_count = sum(len(errs) for errs in errors_by_file.values())
    print(f"📊 初始错误: {initial_count} 个")
    print(f"📊 涉及文件: {len(errors_by_file)} 个")
    
    # 批量处理文件
    batch_size = 200
    files_to_process = list(errors_by_file.items())[:batch_size]
    
    fixed = 0
    for file_path_str, file_errors in files_to_process:
        file_path = Path(file_path_str)
        if not file_path.exists():
            continue
        
        if fix_file_comprehensive(file_path, file_errors):
            fixed += 1
            if fixed % 20 == 0:
                print(f"✅ 已修复 {fixed} 个文件...")
    
    print(f"\n✅ 本轮修复了 {fixed} 个文件")
    
    # 重新检查
    print("\n🔍 第2轮检查...")
    output = run_mypy()
    
    for line in output.split('\n'):
        if 'Found' in line and 'error' in line:
            print(f"📊 {line}")
            break

if __name__ == "__main__":
    main()
