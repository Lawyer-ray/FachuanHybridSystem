#!/usr/bin/env python3
"""修复类型注解语法错误"""
import re
from pathlib import Path
from typing import Any

def fix_syntax_errors(file_path: Path) -> bool:
    """修复文件中的类型注解语法错误"""
    content = file_path.read_text(encoding='utf-8')
    original_content = content
    
    # 修复模式: param -> ReturnType: ParamType
    # 应该是: param: ParamType
    # 返回类型应该在函数定义的末尾
    pattern = r'(\w+)\s*->\s*([^:]+):\s*([^,\)]+)'
    
    def replace_func(match: Any) -> str:
        param_name = match.group(1)
        param_type = match.group(3).strip()
        
        return f'{param_name}: {param_type}'
    
    content = re.sub(pattern, replace_func, content)
    
    if content != original_content:
        file_path.write_text(content, encoding='utf-8')
        return True
    return False

def main() -> None:
    """主函数"""
    apps_dir = Path('apps')
    fixed_count = 0
    
    for py_file in apps_dir.rglob('*.py'):
        if fix_syntax_errors(py_file):
            print(f'修复: {py_file}')
            fixed_count += 1
    
    print(f'\n总共修复 {fixed_count} 个文件')

if __name__ == '__main__':
    main()
