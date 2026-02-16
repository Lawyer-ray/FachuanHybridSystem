#!/usr/bin/env python3
"""
修复 document_delivery 模块的 Django ORM 类型错误
使用 cast() 处理 Model 动态属性
"""

import re
from pathlib import Path
from typing import Any


def add_cast_import(content: str) -> str:
    """确保文件中有 cast 导入"""
    if 'from typing import cast' in content:
        return content
    
    # 查找 typing 导入行
    typing_import_pattern = r'from typing import ([^\n]+)'
    match = re.search(typing_import_pattern, content)
    
    if match:
        # 已有 typing 导入，添加 cast
        imports = match.group(1)
        if 'cast' not in imports:
            new_imports = imports.rstrip() + ', cast'
            content = content.replace(match.group(0), f'from typing import {new_imports}')
    else:
        # 没有 typing 导入，在 import 区域添加
        # 找到第一个非 import 行
        lines = content.split('\n')
        insert_idx = 0
        for i, line in enumerate(lines):
            if line.strip() and not (line.startswith('import ') or line.startswith('from ') or 
                                    line.startswith('#') or line.startswith('"""') or line.startswith("'''")):
                insert_idx = i
                break
        
        lines.insert(insert_idx, 'from typing import cast')
        content = '\n'.join(lines)
    
    return content


def fix_model_id_access(content: str, model_name: str) -> str:
    """修复 Model.id 访问"""
    # 匹配 model_instance.id 模式
    # 例如: sms.id, case.id, schedule.id
    pattern = rf'(\b\w+)\.id\b'
    
    def replace_id(match: re.Match[str]) -> str:
        var_name = match.group(1)
        # 只替换特定的变量名
        if model_name.lower() in var_name.lower() or var_name in ['sms', 'schedule', 'case', 'record']:
            return f'cast(int, {var_name}.id)'
        return match.group(0)
    
    content = re.sub(pattern, replace_id, content)
    return content


def fix_foreign_key_id_access(content: str) -> str:
    """修复外键 ID 访问，如 sms.case_id, sms.case_log_id"""
    # 匹配 model_instance.foreign_key_id 模式
    patterns = [
        (r'(\bsms)\.case_id\b', r'cast(int | None, \1.case_id)'),
        (r'(\bsms)\.case_log_id\b', r'cast(int | None, \1.case_log_id)'),
        (r'(\bschedule)\.credential_id\b', r'cast(int | None, \1.credential_id)'),
    ]
    
    for pattern, replacement in patterns:
        content = re.sub(pattern, replacement, content)
    
    return content


def fix_queryset_generic(content: str) -> str:
    """为 QuerySet 添加泛型参数"""
    # 匹配 QuerySet 类型注解
    patterns = [
        (r'-> QuerySet:', r'-> QuerySet[CourtSMS]:'),
        (r'-> QuerySet\[', r'-> QuerySet['),  # 已有泛型参数，跳过
        (r': QuerySet =', r': QuerySet[CourtSMS] ='),
    ]
    
    for pattern, replacement in patterns:
        if 'QuerySet[' not in replacement or 'QuerySet[' not in content:
            content = re.sub(pattern, replacement, content)
    
    return content


def process_file(file_path: Path) -> bool:
    """处理单个文件"""
    try:
        content = file_path.read_text(encoding='utf-8')
        original = content
        
        # 检查是否包含需要修复的模式
        needs_fix = False
        
        # 检查是否有 .id 访问
        if re.search(r'\b(sms|schedule|case|record)\.id\b', content):
            needs_fix = True
            content = add_cast_import(content)
            content = fix_model_id_access(content, 'CourtSMS')
            content = fix_model_id_access(content, 'DocumentDeliverySchedule')
        
        # 检查是否有外键 ID 访问
        if re.search(r'\b(sms\.case_id|sms\.case_log_id|schedule\.credential_id)\b', content):
            needs_fix = True
            content = add_cast_import(content)
            content = fix_foreign_key_id_access(content)
        
        # 检查是否有 QuerySet 类型注解
        if 'QuerySet' in content and 'QuerySet[' not in content:
            needs_fix = True
            content = fix_queryset_generic(content)
        
        if needs_fix and content != original:
            file_path.write_text(content, encoding='utf-8')
            return True
        
        return False
    
    except Exception as e:
        print(f"处理文件 {file_path} 时出错: {e}")
        return False


def main():
    backend_path = Path(__file__).parent.parent
    document_delivery_path = backend_path / 'apps' / 'automation' / 'services' / 'document_delivery'
    
    if not document_delivery_path.exists():
        print(f"错误: 找不到目录 {document_delivery_path}")
        return
    
    fixed_count = 0
    for py_file in document_delivery_path.rglob('*.py'):
        if py_file.name == '__init__.py':
            continue
        
        if process_file(py_file):
            fixed_count += 1
            print(f"已修复: {py_file.relative_to(backend_path)}")
    
    print(f"\n总计修复: {fixed_count} 个文件")


if __name__ == '__main__':
    main()
