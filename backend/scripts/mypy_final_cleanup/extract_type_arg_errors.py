"""提取type-arg错误的文件列表"""

from __future__ import annotations

import re
from pathlib import Path


def extract_type_arg_errors(mypy_output_file: str) -> dict[str, list[int]]:
    """
    从mypy输出中提取type-arg错误
    
    Returns:
        字典: {文件路径: [行号列表]}
    """
    errors: dict[str, list[int]] = {}
    
    with open(mypy_output_file, 'r', encoding='utf-8') as f:
        lines = f.readlines()
    
    for line in lines:
        if '[type-arg]' in line:
            # 匹配格式: apps/xxx/yyy.py:123:45: error: ...
            match = re.match(r'^(apps/[^:]+):(\d+):', line)
            if match:
                file_path = match.group(1)
                line_num = int(match.group(2))
                
                if file_path not in errors:
                    errors[file_path] = []
                errors[file_path].append(line_num)
    
    return errors


if __name__ == '__main__':
    errors = extract_type_arg_errors('/tmp/type_arg_errors_full.txt')
    
    print(f"找到 {len(errors)} 个文件包含type-arg错误:")
    print(f"总错误数: {sum(len(lines) for lines in errors.values())}")
    print()
    
    for file_path in sorted(errors.keys()):
        print(f"{file_path}: {len(errors[file_path])}个错误")
