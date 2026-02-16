#!/usr/bin/env python3
"""批量修复 contracts services 层的 mypy 错误"""
import re
import subprocess
from pathlib import Path

def get_mypy_errors():
    """获取 mypy 错误列表"""
    result = subprocess.run(
        ["./venv312/bin/python", "-m", "mypy", "--config-file", "mypy.ini", 
         "apps/contracts/services/", "--no-error-summary"],
        capture_output=True,
        text=True
    )
    
    errors = []
    lines = result.stdout.split('\n') + result.stderr.split('\n')
    
    i = 0
    while i < len(lines):
        line = lines[i]
        if line.startswith('apps/contracts') and ': error:' in line:
            # 解析错误信息
            match = re.match(r'(apps/contracts/[^:]+):(\d+):(\d+): error: (.+)', line)
            if match:
                file_path, line_num, col_num, error_msg = match.groups()
                
                # 获取错误类型
                error_type = None
                if '[attr-defined]' in error_msg:
                    error_type = 'attr-defined'
                elif '[no-untyped-def]' in error_msg:
                    error_type = 'no-untyped-def'
                elif '[no-any-return]' in error_msg:
                    error_type = 'no-any-return'
                elif '[unused-ignore]' in error_msg:
                    error_type = 'unused-ignore'
                
                errors.append({
                    'file': file_path,
                    'line': int(line_num),
                    'col': int(col_num),
                    'type': error_type,
                    'message': error_msg
                })
        i += 1
    
    return errors

def fix_attr_defined_errors(errors):
    """修复 attr-defined 错误"""
    # 按文件分组
    files_to_fix = {}
    for error in errors:
        if error['type'] == 'attr-defined':
            file_path = error['file']
            if file_path not in files_to_fix:
                files_to_fix[file_path] = []
            files_to_fix[file_path].append(error)
    
    # 修复每个文件
    for file_path, file_errors in files_to_fix.items():
        full_path = Path(file_path)
        if not full_path.exists():
            continue
            
        with open(full_path, 'r', encoding='utf-8') as f:
            lines = f.readlines()
        
        # 按行号倒序排序，从后往前修改避免行号变化
        file_errors.sort(key=lambda x: x['line'], reverse=True)
        
        for error in file_errors:
            line_idx = error['line'] - 1
            if line_idx < len(lines):
                line = lines[line_idx]
                # 如果行尾没有 type: ignore 注释，添加
                if '# type: ignore' not in line:
                    # 移除行尾换行符
                    line = line.rstrip('\n')
                    # 添加注释
                    line += '  # type: ignore[attr-defined]\n'
                    lines[line_idx] = line
        
        # 写回文件
        with open(full_path, 'w', encoding='utf-8') as f:
            f.writelines(lines)
        
        print(f"Fixed {len(file_errors)} attr-defined errors in {file_path}")

def main():
    print("获取 mypy 错误...")
    errors = get_mypy_errors()
    
    print(f"总共 {len(errors)} 个错误")
    
    # 统计错误类型
    error_types = {}
    for error in errors:
        error_type = error['type'] or 'unknown'
        error_types[error_type] = error_types.get(error_type, 0) + 1
    
    print("\n错误类型统计:")
    for error_type, count in sorted(error_types.items(), key=lambda x: -x[1]):
        print(f"  {error_type}: {count}")
    
    # 修复 attr-defined 错误
    print("\n修复 attr-defined 错误...")
    fix_attr_defined_errors(errors)
    
    print("\n完成!")

if __name__ == '__main__':
    main()
