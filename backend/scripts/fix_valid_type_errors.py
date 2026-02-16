#!/usr/bin/env python3
"""修复valid-type错误 - 移除重复的类型参数"""

import re
import subprocess
from pathlib import Path
from typing import Any

def get_valid_type_errors() -> list[tuple[str, int, str]]:
    """获取所有valid-type错误"""
    result = subprocess.run(
        ["python", "-m", "mypy", "apps/", "--strict"],
        capture_output=True,
        text=True,
        cwd="."
    )
    
    output = result.stdout + result.stderr
    errors: list[tuple[str, int, str]] = []
    
    # 解析错误：apps/path/file.py:39:43: error: Invalid type comment or annotation  [valid-type]
    # 注意：输出可能被截断，需要匹配不完整的路径
    pattern = re.compile(r'(apps/[^:]+):(\d+):\d+: error: .+ \[valid-type\]')
    
    for match in pattern.finditer(output):
        file_path = match.group(1)
        line_num = int(match.group(2))
        errors.append((file_path, line_num, match.group(0)))
    
    return errors

def fix_double_type_params(content: str) -> tuple[str, int]:
    """修复重复的类型参数，如 dict[str, Any][str, int] -> dict[str, int]"""
    fixes = 0
    
    # 匹配模式：dict[str, Any][实际类型]
    # 保留第二个类型参数（更具体的）
    patterns = [
        # dict[str, Any][str, X] -> dict[str, X]
        (r'dict\[str,\s*Any\]\[str,\s*([^\]]+)\]', r'dict[str, \1]'),
        # dict[str, Any][X, Y] -> dict[X, Y]
        (r'dict\[str,\s*Any\]\[([^\]]+)\]', r'dict[\1]'),
        # list[Any][X] -> list[X]
        (r'list\[Any\]\[([^\]]+)\]', r'list[\1]'),
        # set[Any][X] -> set[X]
        (r'set\[Any\]\[([^\]]+)\]', r'set[\1]'),
    ]
    
    for pattern, replacement in patterns:
        new_content, count = re.subn(pattern, replacement, content)
        if count > 0:
            content = new_content
            fixes += count
    
    return content, fixes

def fix_file(file_path: str) -> int:
    """修复单个文件"""
    path = Path(file_path)
    if not path.exists():
        print(f"文件不存在: {file_path}")
        return 0
    
    try:
        content = path.read_text(encoding='utf-8')
        new_content, fixes = fix_double_type_params(content)
        
        if fixes > 0:
            path.write_text(new_content, encoding='utf-8')
            print(f"✓ {file_path}: 修复了 {fixes} 处")
            return fixes
        
        return 0
    except Exception as e:
        print(f"✗ {file_path}: {e}")
        return 0

def main() -> None:
    """主函数"""
    print("正在分析valid-type错误...")
    errors = get_valid_type_errors()
    
    if not errors:
        print("没有发现valid-type错误")
        return
    
    print(f"发现 {len(errors)} 个valid-type错误")
    
    # 按文件分组
    files_to_fix: set[str] = set()
    for file_path, line_num, error_msg in errors:
        files_to_fix.add(file_path)
    
    print(f"涉及 {len(files_to_fix)} 个文件")
    print("\n开始修复...")
    
    total_fixes = 0
    for file_path in sorted(files_to_fix):
        fixes = fix_file(file_path)
        total_fixes += fixes
    
    print(f"\n总计修复: {total_fixes} 处")
    
    # 重新检查
    print("\n重新检查...")
    remaining_errors = get_valid_type_errors()
    print(f"剩余valid-type错误: {len(remaining_errors)}")

if __name__ == "__main__":
    main()
