#!/usr/bin/env python3
"""批量修复 services 层的类型注解错误"""

import re
import subprocess
from pathlib import Path
from typing import Dict, List, Tuple


def get_mypy_errors(paths: List[str]) -> List[Tuple[str, int, str, str]]:
    """运行 mypy 并解析错误"""
    cmd = ["mypy", "--config-file", "mypy.ini"] + paths
    result = subprocess.run(cmd, capture_output=True, text=True, cwd=".")
    
    # mypy 输出到 stdout 和 stderr，合并处理
    output = result.stdout + result.stderr
    
    errors = []
    for line in output.split('\n'):
        if 'error:' in line and '[' in line and ']' in line:
            # 解析格式: file.py:line:col: error: message [error-code]
            # 注意：文件路径可能被截断，需要更灵活的匹配
            parts = line.split(':')
            if len(parts) >= 4:
                try:
                    file_path = parts[0].strip()
                    line_num = int(parts[1].strip())
                    # 提取错误代码
                    error_code_match = re.search(r'\[([^\]]+)\]', line)
                    if error_code_match:
                        error_code = error_code_match.group(1)
                        # 提取消息（error: 和 [ 之间的内容）
                        message_match = re.search(r'error:\s*(.+?)\s*\[', line)
                        if message_match:
                            message = message_match.group(1).strip()
                            errors.append((file_path, line_num, message, error_code))
                except (ValueError, IndexError):
                    continue
    
    return errors


def fix_no_untyped_def(file_path: str, line_num: int, message: str) -> bool:
    """修复 no-untyped-def 错误"""
    path = Path(file_path)
    if not path.exists():
        return False
    
    content = path.read_text()
    lines = content.split('\n')
    
    if line_num > len(lines):
        return False
    
    target_line = lines[line_num - 1]
    
    # 检查是否是 __init__ 方法
    if 'def __init__' in target_line and '-> None' not in target_line:
        # 添加 -> None
        fixed_line = target_line.replace('):', ') -> None:')
        lines[line_num - 1] = fixed_line
        path.write_text('\n'.join(lines))
        return True
    
    # 检查是否是其他没有返回类型的方法
    if 'def ' in target_line and '->' not in target_line and ':' in target_line:
        # 如果消息提示使用 -> None
        if 'Use "-> None"' in message:
            fixed_line = target_line.replace('):', ') -> None:')
            lines[line_num - 1] = fixed_line
            path.write_text('\n'.join(lines))
            return True
    
    return False


def fix_valid_type_any(file_path: str, line_num: int) -> bool:
    """修复 any -> Any 错误"""
    path = Path(file_path)
    if not path.exists():
        return False
    
    content = path.read_text()
    lines = content.split('\n')
    
    if line_num > len(lines):
        return False
    
    target_line = lines[line_num - 1]
    
    # 替换 any 为 Any
    if ': any' in target_line or ', any' in target_line:
        fixed_line = target_line.replace(': any', ': Any').replace(', any', ', Any')
        lines[line_num - 1] = fixed_line
        
        # 确保导入了 Any
        has_any_import = False
        for i, line in enumerate(lines):
            if 'from typing import' in line and 'Any' in line:
                has_any_import = True
                break
            if 'import typing' in line:
                has_any_import = True
                break
        
        if not has_any_import:
            # 找到第一个 import 语句后插入
            for i, line in enumerate(lines):
                if line.startswith('from ') or line.startswith('import '):
                    lines.insert(i, 'from typing import Any')
                    break
        
        path.write_text('\n'.join(lines))
        return True
    
    return False


def fix_var_annotated(file_path: str, line_num: int, message: str) -> bool:
    """修复 var-annotated 错误"""
    path = Path(file_path)
    if not path.exists():
        return False
    
    content = path.read_text()
    lines = content.split('\n')
    
    if line_num > len(lines):
        return False
    
    target_line = lines[line_num - 1]
    
    # 提取变量名和建议的类型
    # 格式: Need type annotation for "var" (hint: "var: List[<type>] = ...")
    var_match = re.search(r'Need type annotation for "(.+?)"', message)
    if not var_match:
        return False
    
    var_name = var_match.group(1)
    
    # 常见模式修复
    if f'{var_name} = []' in target_line:
        # 空列表
        fixed_line = target_line.replace(f'{var_name} = []', f'{var_name}: list = []')
        lines[line_num - 1] = fixed_line
        path.write_text('\n'.join(lines))
        return True
    
    if f'{var_name} = {{}}' in target_line:
        # 空字典
        fixed_line = target_line.replace(f'{var_name} = {{}}', f'{var_name}: dict = {{}}')
        lines[line_num - 1] = fixed_line
        path.write_text('\n'.join(lines))
        return True
    
    return False


def main():
    """主函数"""
    service_paths = [
        "apps/automation/services/",
        "apps/cases/services/",
        "apps/client/services/",
        "apps/contracts/services/",
        "apps/documents/services/",
    ]
    
    print("正在收集 mypy 错误...")
    errors = get_mypy_errors(service_paths)
    print(f"共发现 {len(errors)} 个错误")
    
    # 按错误类型分组
    errors_by_type: Dict[str, List[Tuple[str, int, str]]] = {}
    for file_path, line_num, message, error_code in errors:
        if error_code not in errors_by_type:
            errors_by_type[error_code] = []
        errors_by_type[error_code].append((file_path, line_num, message))
    
    print("\n错误类型分布:")
    for error_code, error_list in sorted(errors_by_type.items(), key=lambda x: len(x[1]), reverse=True):
        print(f"  {error_code}: {len(error_list)}")
    
    # 修复 no-untyped-def 错误
    if 'no-untyped-def' in errors_by_type:
        print(f"\n开始修复 no-untyped-def 错误 ({len(errors_by_type['no-untyped-def'])} 个)...")
        fixed_count = 0
        for file_path, line_num, message in errors_by_type['no-untyped-def']:
            if fix_no_untyped_def(file_path, line_num, message):
                fixed_count += 1
        print(f"已修复 {fixed_count} 个 no-untyped-def 错误")
    
    # 修复 valid-type 错误 (any -> Any)
    if 'valid-type' in errors_by_type:
        print(f"\n开始修复 valid-type 错误 ({len(errors_by_type['valid-type'])} 个)...")
        fixed_count = 0
        for file_path, line_num, message in errors_by_type['valid-type']:
            if 'Perhaps you meant "typing.Any"' in message:
                if fix_valid_type_any(file_path, line_num):
                    fixed_count += 1
        print(f"已修复 {fixed_count} 个 valid-type 错误")
    
    # 修复 var-annotated 错误
    if 'var-annotated' in errors_by_type:
        print(f"\n开始修复 var-annotated 错误 ({len(errors_by_type['var-annotated'])} 个)...")
        fixed_count = 0
        for file_path, line_num, message in errors_by_type['var-annotated']:
            if fix_var_annotated(file_path, line_num, message):
                fixed_count += 1
        print(f"已修复 {fixed_count} 个 var-annotated 错误")
    
    print("\n重新运行 mypy 检查剩余错误...")
    errors_after = get_mypy_errors(service_paths)
    print(f"剩余 {len(errors_after)} 个错误")


if __name__ == '__main__':
    main()
