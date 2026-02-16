#!/usr/bin/env python3
"""
修复 scraper 模块中的 Django ORM 类型错误

使用 cast() 处理 Model 动态属性 (id, case_id 等)
"""
from pathlib import Path
import re
from typing import cast as typing_cast


def fix_orm_types_in_file(file_path: Path) -> int:
    """修复单个文件中的 Django ORM 类型错误"""
    content = file_path.read_text(encoding='utf-8')
    original = content
    fixes = 0
    
    # 确保导入 cast
    has_cast_import = 'from typing import cast' in content
    
    # 修复 task.id -> cast(int, task.id)
    # 匹配模式: task.id (但不匹配已经有 cast 的)
    pattern = r'(?<!cast\(int, )(\btask\.id\b)(?!\))'
    matches = re.findall(pattern, content)
    if matches:
        content = re.sub(pattern, r'cast(int, \1)', content)
        fixes += len(matches)
    
    # 修复 task.case_id -> cast(int, task.case_id)
    pattern = r'(?<!cast\(int, )(\btask\.case_id\b)(?!\))'
    matches = re.findall(pattern, content)
    if matches:
        content = re.sub(pattern, r'cast(int, \1)', content)
        fixes += len(matches)
    
    # 修复 document.id -> cast(int, document.id)
    pattern = r'(?<!cast\(int, )(\bdocument\.id\b)(?!\))'
    matches = re.findall(pattern, content)
    if matches:
        content = re.sub(pattern, r'cast(int, \1)', content)
        fixes += len(matches)
    
    # 修复 document.case_id -> cast(int, document.case_id)
    pattern = r'(?<!cast\(int, )(\bdocument\.case_id\b)(?!\))'
    matches = re.findall(pattern, content)
    if matches:
        content = re.sub(pattern, r'cast(int, \1)', content)
        fixes += len(matches)
    
    # 修复 sms.id -> cast(int, sms.id)
    pattern = r'(?<!cast\(int, )(\bsms\.id\b)(?!\))'
    matches = re.findall(pattern, content)
    if matches:
        content = re.sub(pattern, r'cast(int, \1)', content)
        fixes += len(matches)
    
    # 修复 sms.case_id -> cast(int, sms.case_id)
    pattern = r'(?<!cast\(int, )(\bsms\.case_id\b)(?!\))'
    matches = re.findall(pattern, content)
    if matches:
        content = re.sub(pattern, r'cast(int, \1)', content)
        fixes += len(matches)
    
    # 修复 case.id -> cast(int, case.id)
    pattern = r'(?<!cast\(int, )(\bcase\.id\b)(?!\))'
    matches = re.findall(pattern, content)
    if matches:
        content = re.sub(pattern, r'cast(int, \1)', content)
        fixes += len(matches)
    
    # 修复 quote.id -> cast(int, quote.id)
    pattern = r'(?<!cast\(int, )(\bquote\.id\b)(?!\))'
    matches = re.findall(pattern, content)
    if matches:
        content = re.sub(pattern, r'cast(int, \1)', content)
        fixes += len(matches)
    
    # 如果有修复且没有 cast 导入,添加导入
    if fixes > 0 and not has_cast_import:
        # 查找 typing 导入行
        typing_import_pattern = r'^from typing import (.+)$'
        typing_match = re.search(typing_import_pattern, content, re.MULTILINE)
        
        if typing_match:
            # 已有 typing 导入,添加 cast
            old_imports = typing_match.group(1)
            if 'cast' not in old_imports:
                new_imports = old_imports + ', cast'
                content = re.sub(
                    typing_import_pattern,
                    f'from typing import {new_imports}',
                    content,
                    count=1,
                    flags=re.MULTILINE
                )
        else:
            # 没有 typing 导入,在文件开头添加
            lines = content.split('\n')
            # 找到第一个非注释、非空行的 import 位置
            insert_pos = 0
            for i, line in enumerate(lines):
                stripped = line.strip()
                if stripped and not stripped.startswith('#') and not stripped.startswith('"""'):
                    if stripped.startswith('import ') or stripped.startswith('from '):
                        insert_pos = i
                        break
            
            # 在 import 区域后添加
            if insert_pos > 0:
                # 找到最后一个 import
                for i in range(insert_pos, len(lines)):
                    stripped = lines[i].strip()
                    if stripped and not stripped.startswith('import ') and not stripped.startswith('from '):
                        insert_pos = i
                        break
                    insert_pos = i + 1
            
            lines.insert(insert_pos, 'from typing import cast')
            content = '\n'.join(lines)
    
    if content != original:
        file_path.write_text(content, encoding='utf-8')
        return fixes
    
    return 0


def main():
    """主函数"""
    backend_path = Path(__file__).parent.parent
    
    # 修复 automation/tasks.py
    tasks_file = backend_path / 'apps' / 'automation' / 'tasks.py'
    if tasks_file.exists():
        fixes = fix_orm_types_in_file(tasks_file)
        if fixes > 0:
            print(f"✓ {tasks_file.relative_to(backend_path)}: {fixes} 处修复")
    
    # 修复 scraper 模块
    scraper_path = backend_path / 'apps' / 'automation' / 'services' / 'scraper'
    total_fixes = 0
    fixed_files = 0
    
    for py_file in scraper_path.rglob('*.py'):
        if py_file.name == '__init__.py' or '__pycache__' in str(py_file):
            continue
        
        fixes = fix_orm_types_in_file(py_file)
        if fixes > 0:
            total_fixes += fixes
            fixed_files += 1
            print(f"✓ {py_file.relative_to(backend_path)}: {fixes} 处修复")
    
    print(f"\n总计: 修复 {fixed_files} 个文件, {total_fixes} 处 ORM 类型错误")


if __name__ == '__main__':
    main()
