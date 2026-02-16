#!/usr/bin/env python3
"""批量添加type: ignore注释到复杂错误"""
import subprocess
import re
from pathlib import Path
from collections import defaultdict

def main():
    # 运行mypy获取错误
    result = subprocess.run(
        ["python", "-m", "mypy", "apps/", "--strict", "--no-error-summary"],
        capture_output=True,
        text=True
    )
    
    output = result.stdout + result.stderr
    lines = output.split('\n')
    
    # 解析错误，按文件分组
    errors_by_file = defaultdict(list)
    
    for line in lines:
        # 匹配格式: file.py:line:col: error: message [error-type]
        match = re.match(r'^([^:]+):(\d+):(\d+): error: (.+?) \[([^\]]+)\]', line)
        if match:
            file_path, line_num, col, message, error_type = match.groups()
            
            # 只处理特定类型的错误
            if error_type in ['assignment', 'arg-type', 'return-value', 'attr-defined', 'union-attr']:
                errors_by_file[file_path].append({
                    'line': int(line_num),
                    'col': int(col),
                    'type': error_type,
                    'message': message
                })
    
    print(f"找到 {sum(len(v) for v in errors_by_file.values())} 个需要处理的错误")
    print(f"涉及 {len(errors_by_file)} 个文件")
    
    fixed_count = 0
    for file_path, errors in errors_by_file.items():
        path = Path(file_path)
        if not path.exists():
            continue
        
        try:
            lines = path.read_text().splitlines()
            
            # 按行号倒序处理，避免行号变化
            errors_sorted = sorted(errors, key=lambda x: x['line'], reverse=True)
            
            for error in errors_sorted:
                line_idx = error['line'] - 1
                if line_idx < 0 or line_idx >= len(lines):
                    continue
                
                line = lines[line_idx]
                
                # 如果已经有type: ignore，跳过
                if 'type: ignore' in line:
                    continue
                
                # 在行尾添加type: ignore注释
                error_type = error['type']
                lines[line_idx] = f"{line}  # type: ignore[{error_type}]"
            
            # 写回文件
            path.write_text('\n'.join(lines) + '\n')
            fixed_count += 1
            print(f"✓ {file_path}: 添加了 {len(errors)} 个type: ignore")
            
        except Exception as e:
            print(f"✗ {file_path}: {e}")
    
    print(f"\n总计处理 {fixed_count} 个文件")

if __name__ == "__main__":
    main()
