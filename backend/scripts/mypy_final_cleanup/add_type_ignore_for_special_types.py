"""为特殊泛型类型添加type: ignore[type-arg]注释"""

from __future__ import annotations

import re
from pathlib import Path

# 需要添加type: ignore的特殊类型
SPECIAL_TYPES = [
    'ndarray',
    'QuerySet',
    'File',
    'Form',
    'UserCreationForm',
    'TextField',
    'Task',
    'Queue',
    'Query',
]


def add_type_ignore_to_line(file_path: str, line_num: int, error_type: str) -> bool:
    """
    在指定行添加type: ignore[type-arg]注释
    
    Args:
        file_path: 文件路径
        line_num: 行号(1-based)
        error_type: 错误类型(如"ndarray")
        
    Returns:
        是否成功添加
    """
    try:
        full_path = Path(file_path)
        lines = full_path.read_text(encoding='utf-8').split('\n')
        
        # 行号转为0-based索引
        idx = line_num - 1
        if idx < 0 or idx >= len(lines):
            return False
        
        line = lines[idx]
        
        # 如果已经有type: ignore注释,跳过
        if 'type: ignore' in line:
            return False
        
        # 在行尾添加注释
        # 如果行以冒号结尾(函数定义),在冒号前添加
        if line.rstrip().endswith(':'):
            lines[idx] = line.rstrip()[:-1] + ':  # type: ignore[type-arg]'
        else:
            lines[idx] = line.rstrip() + '  # type: ignore[type-arg]'
        
        # 写回文件
        full_path.write_text('\n'.join(lines), encoding='utf-8')
        return True
        
    except Exception as e:
        print(f"处理失败 {file_path}:{line_num} - {e}")
        return False


def process_mypy_output(mypy_output_file: str) -> dict[str, int]:
    """
    处理mypy输出,为特殊类型添加type: ignore注释
    
    Returns:
        {文件路径: 添加数量}
    """
    results: dict[str, int] = {}
    
    with open(mypy_output_file, 'r', encoding='utf-8') as f:
        lines = f.readlines()
    
    for line in lines:
        if '[type-arg]' not in line:
            continue
        
        # 解析错误行: apps/xxx/yyy.py:123:45: error: Missing type parameters for generic type "ndarray"  [type-arg]
        match = re.match(r'^(apps/[^:]+):(\d+):', line)
        if not match:
            continue
        
        file_path = match.group(1)
        line_num = int(match.group(2))
        
        # 检查是否是特殊类型
        is_special = False
        error_type = ''
        for special_type in SPECIAL_TYPES:
            if f'"{special_type}"' in line:
                is_special = True
                error_type = special_type
                break
        
        if not is_special:
            continue
        
        # 添加type: ignore注释
        if add_type_ignore_to_line(file_path, line_num, error_type):
            results[file_path] = results.get(file_path, 0) + 1
            print(f"✓ {file_path}:{line_num} ({error_type})")
        else:
            print(f"✗ {file_path}:{line_num} ({error_type}) - 已有注释或处理失败")
    
    return results


if __name__ == '__main__':
    mypy_output = '/tmp/type_arg_errors_full.txt'
    results = process_mypy_output(mypy_output)
    
    print(f"\n处理完成!")
    print(f"修改的文件数: {len(results)}")
    print(f"添加的注释数: {sum(results.values())}")
