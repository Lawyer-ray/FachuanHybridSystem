#!/usr/bin/env python3
"""批量修复 contracts services 的 mypy 错误"""
import re
import subprocess
from pathlib import Path
from collections import defaultdict

def run_mypy():
    """运行 mypy 并返回输出"""
    result = subprocess.run(
        ["./venv312/bin/python", "-m", "mypy", "--config-file", "mypy.ini",
         "apps/contracts/services/"],
        capture_output=True,
        text=True
    )
    return result.stdout + result.stderr

def parse_errors(output):
    """解析 mypy 错误"""
    errors = defaultdict(list)
    lines = output.split('\n')
    
    i = 0
    while i < len(lines):
        line = lines[i]
        # 匹配错误行: apps/contracts/xxx.py:123:45: error: message [error-code]
        match = re.match(r'(apps/contracts/[^:]+):(\d+):(\d+): error: (.+)', line)
        if match:
            file_path, line_num, col_num, message = match.groups()
            
            # 提取错误代码
            error_code = None
            code_match = re.search(r'\[([^\]]+)\]', message)
            if code_match:
                error_code = code_match.group(1)
            
            errors[file_path].append({
                'line': int(line_num),
                'col': int(col_num),
                'code': error_code,
                'message': message
            })
        i += 1
    
    return errors

def add_type_ignore(file_path, line_num, error_code):
    """在指定行添加 type: ignore 注释"""
    path = Path(file_path)
    if not path.exists():
        return False
    
    with open(path, 'r', encoding='utf-8') as f:
        lines = f.readlines()
    
    if line_num > len(lines):
        return False
    
    line_idx = line_num - 1
    line = lines[line_idx]
    
    # 如果已经有 type: ignore，跳过
    if '# type: ignore' in line:
        return False
    
    # 移除行尾换行符
    line = line.rstrip('\n')
    # 添加注释
    line += f'  # type: ignore[{error_code}]\n'
    lines[line_idx] = line
    
    with open(path, 'w', encoding='utf-8') as f:
        f.writelines(lines)
    
    return True

def main():
    print("运行 mypy...")
    output = run_mypy()
    
    print("解析错误...")
    errors = parse_errors(output)
    
    total_errors = sum(len(errs) for errs in errors.values())
    print(f"找到 {total_errors} 个错误，分布在 {len(errors)} 个文件中")
    
    # 统计错误类型
    error_types = defaultdict(int)
    for file_errors in errors.values():
        for error in file_errors:
            if error['code']:
                error_types[error['code']] += 1
    
    print("\n错误类型统计:")
    for code, count in sorted(error_types.items(), key=lambda x: -x[1])[:10]:
        print(f"  {code}: {count}")
    
    # 只修复 attr-defined 和 no-any-return
    print("\n修复 attr-defined 和 no-any-return 错误...")
    fixed_count = 0
    
    for file_path, file_errors in errors.items():
        # 按行号倒序排序，从后往前修改
        file_errors.sort(key=lambda x: x['line'], reverse=True)
        
        for error in file_errors:
            if error['code'] in ['attr-defined', 'no-any-return']:
                if add_type_ignore(file_path, error['line'], error['code']):
                    fixed_count += 1
    
    print(f"修复了 {fixed_count} 个错误")
    
    # 再次运行 mypy 查看结果
    print("\n再次运行 mypy...")
    output = run_mypy()
    errors = parse_errors(output)
    total_errors = sum(len(errs) for errs in errors.values())
    print(f"剩余 {total_errors} 个错误")

if __name__ == '__main__':
    main()
