#!/usr/bin/env python3
"""批量修复assignment错误"""
import subprocess
import re
from pathlib import Path
from collections import defaultdict

def get_assignment_errors():
    """获取所有assignment错误"""
    result = subprocess.run(
        ["python", "-m", "mypy", "apps/", "--strict"],
        capture_output=True,
        text=True
    )
    
    output = result.stdout + result.stderr
    lines = output.split('\n')
    
    errors = []
    for line in lines:
        if '[assignment]' in line and 'error:' in line:
            # 解析错误信息
            match = re.match(r'([^:]+):(\d+):(\d+): error: (.+) \[assignment\]', line)
            if match:
                file_path, line_num, col, message = match.groups()
                errors.append({
                    'file': file_path,
                    'line': int(line_num),
                    'col': int(col),
                    'message': message
                })
    
    return errors

def fix_optional_defaults(file_path: Path, content: str) -> str:
    """修复 = None 的默认参数类型"""
    # 匹配模式: param: Type = None
    pattern = r'(\w+):\s*([^=\s,\)]+)\s*=\s*None'
    
    def replace_func(match):
        param_name = match.group(1)
        type_name = match.group(2)
        # 如果类型已经是Optional或包含|None，不修改
        if 'None' in type_name or 'Optional' in type_name:
            return match.group(0)
        return f'{param_name}: {type_name} | None = None'
    
    return re.sub(pattern, replace_func, content)

def main():
    errors = get_assignment_errors()
    print(f"找到 {len(errors)} 个assignment错误")
    
    # 按文件分组
    files_to_fix = defaultdict(list)
    for error in errors:
        if 'default has type "None"' in error['message']:
            files_to_fix[error['file']].append(error)
    
    print(f"需要修复 {len(files_to_fix)} 个文件")
    
    fixed_count = 0
    for file_path, file_errors in files_to_fix.items():
        path = Path(file_path)
        if not path.exists():
            continue
        
        content = path.read_text()
        new_content = fix_optional_defaults(path, content)
        
        if new_content != content:
            path.write_text(new_content)
            fixed_count += 1
            print(f"✓ 修复: {file_path}")
    
    print(f"\n总计修复 {fixed_count} 个文件")

if __name__ == "__main__":
    main()
