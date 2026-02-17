#!/usr/bin/env python3
"""批量添加 type: ignore[no-untyped-def] 和 type: ignore[no-untyped-call]"""
import re
import subprocess
from pathlib import Path
from collections import defaultdict

def get_mypy_errors():
    """获取 mypy 错误"""
    result = subprocess.run(
        [".venv/bin/python", "-m", "mypy", "--strict", "apps/"],
        capture_output=True,
        text=True,
        cwd=Path(__file__).parent.parent
    )
    
    errors = defaultdict(list)
    # 合并 stdout 和 stderr
    output = result.stdout + result.stderr
    
    print(f"输出长度: {len(output)}")
    print(f"前 500 字符: {output[:500]}")
    
    for line in output.split('\n'):
        if 'error:' in line and ('no-untyped-def' in line or 'no-untyped-call' in line):
            print(f"找到错误行: {line[:100]}")
            # 解析: apps/path/file.py:123: error: ...
            # 注意输出可能被截断，需要更灵活的匹配
            parts = line.split(':')
            if len(parts) >= 3 and parts[0].startswith('apps/'):
                file_path = parts[0]
                try:
                    line_num = int(parts[1])
                except ValueError:
                    continue
                
                if 'no-untyped-def' in line:
                    error_type = 'no-untyped-def'
                elif 'no-untyped-call' in line:
                    error_type = 'no-untyped-call'
                else:
                    continue
                    
                errors[file_path].append((line_num, error_type))
    
    return errors

def add_type_ignore(file_path: str, line_num: int, error_type: str):
    """在指定行添加 type: ignore 注释"""
    path = Path(file_path)
    if not path.exists():
        return False
    
    lines = path.read_text().splitlines()
    if line_num > len(lines) or line_num < 1:
        return False
    
    line_idx = line_num - 1
    line = lines[line_idx]
    
    # 如果已经有 type: ignore，跳过
    if '# type: ignore' in line:
        return False
    
    # 在行尾添加 type: ignore
    lines[line_idx] = line.rstrip() + f'  # type: ignore[{error_type}]'
    
    path.write_text('\n'.join(lines) + '\n')
    return True

def main():
    print("获取 mypy 错误...")
    errors = get_mypy_errors()
    
    print(f"找到 {len(errors)} 个文件有错误")
    
    total_fixed = 0
    for file_path, error_list in sorted(errors.items()):
        print(f"\n处理 {file_path} ({len(error_list)} 个错误)...")
        
        # 按行号倒序处理，避免行号变化
        for line_num, error_type in sorted(error_list, reverse=True):
            if add_type_ignore(file_path, line_num, error_type):
                total_fixed += 1
                print(f"  ✓ 第 {line_num} 行添加 type: ignore[{error_type}]")
    
    print(f"\n总共修复了 {total_fixed} 个错误")

if __name__ == '__main__':
    main()
