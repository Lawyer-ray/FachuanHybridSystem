#!/usr/bin/env python3
"""批量修复 core/config 模块的复杂类型错误"""
import re
from pathlib import Path
from typing import List, Tuple

def fix_file(file_path: Path) -> Tuple[int, List[str]]:
    """修复单个文件，返回修复数量和修复描述"""
    content = file_path.read_text()
    original_content = content
    fixes: List[str] = []
    
    # 1. 修复 result = {} 为 result: Dict[str, Any] = {}
    pattern1 = r'(\s+)(result) = \{'
    if re.search(pattern1, content):
        content = re.sub(pattern1, r'\1\2: Dict[str, Any] = {', content)
        fixes.append("添加 result 变量类型注解")
    
    # 2. 修复 data = {} 为 data: Dict[str, Any] = {}
    pattern2 = r'(\s+)(data) = \{'
    if re.search(pattern2, content):
        content = re.sub(pattern2, r'\1\2: Dict[str, Any] = {', content)
        fixes.append("添加 data 变量类型注解")
    
    # 3. 修复 info = {} 为 info: Dict[str, Any] = {}
    pattern3 = r'(\s+)(info) = \{'
    if re.search(pattern3, content):
        content = re.sub(pattern3, r'\1\2: Dict[str, Any] = {', content)
        fixes.append("添加 info 变量类型注解")
    
    # 4. 修复 stats = {} 为 stats: Dict[str, Any] = {}
    pattern4 = r'(\s+)(stats) = \{'
    if re.search(pattern4, content):
        content = re.sub(pattern4, r'\1\2: Dict[str, Any] = {', content)
        fixes.append("添加 stats 变量类型注解")
    
    # 5. 修复 errors = [] 为 errors: List[str] = []
    pattern5 = r'(\s+)(errors) = \[\]'
    if re.search(pattern5, content):
        content = re.sub(pattern5, r'\1\2: List[str] = []', content)
        fixes.append("添加 errors 变量类型注解")
    
    # 6. 修复 warnings = [] 为 warnings: List[str] = []
    pattern6 = r'(\s+)(warnings) = \[\]'
    if re.search(pattern6, content):
        content = re.sub(pattern6, r'\1\2: List[str] = []', content)
        fixes.append("添加 warnings 变量类型注解")
    
    # 7. 确保有 Dict, List, Any 导入
    if content != original_content:
        # 检查是否已有 typing 导入
        if 'from typing import' in content:
            # 检查是否缺少 Dict, List, Any
            typing_line_match = re.search(r'from typing import ([^\n]+)', content)
            if typing_line_match:
                imports = typing_line_match.group(1)
                needed = []
                if 'Dict' not in imports and 'Dict[str, Any]' in content:
                    needed.append('Dict')
                if 'List' not in imports and 'List[' in content:
                    needed.append('List')
                if 'Any' not in imports and 'Any' in content:
                    needed.append('Any')
                
                if needed:
                    # 添加缺失的导入
                    new_imports = imports.rstrip() + ', ' + ', '.join(needed)
                    content = content.replace(
                        f'from typing import {imports}',
                        f'from typing import {new_imports}'
                    )
                    fixes.append(f"添加导入: {', '.join(needed)}")
        else:
            # 没有 typing 导入，添加一个
            if 'Dict[str, Any]' in content or 'List[' in content:
                # 在第一个 import 之后添加
                import_match = re.search(r'(import [^\n]+\n)', content)
                if import_match:
                    insert_pos = import_match.end()
                    imports_needed = []
                    if 'Dict[str, Any]' in content:
                        imports_needed.extend(['Dict', 'Any'])
                    if 'List[' in content:
                        imports_needed.append('List')
                    
                    import_line = f"from typing import {', '.join(set(imports_needed))}\n"
                    content = content[:insert_pos] + import_line + content[insert_pos:]
                    fixes.append(f"添加 typing 导入")
    
    if content != original_content:
        file_path.write_text(content)
        return len(fixes), fixes
    
    return 0, []

def main() -> None:
    """主函数"""
    config_dir = Path("apps/core/config")
    
    # 需要修复的文件列表
    target_files = [
        "migrator.py",
        "steering_integration.py",
        "steering/integration.py",
        "manager_tools.py",
        "migration_tracker.py",
        "manager.py",
        "compatibility.py",
        "utils.py",
    ]
    
    total_fixes = 0
    for file_name in target_files:
        file_path = config_dir / file_name
        if file_path.exists():
            count, fixes = fix_file(file_path)
            if count > 0:
                print(f"\n{file_path}:")
                for fix in fixes:
                    print(f"  - {fix}")
                total_fixes += count
    
    print(f"\n总共修复了 {total_fixes} 处")

if __name__ == "__main__":
    main()
