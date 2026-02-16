#!/usr/bin/env python3
"""修复cases模块的Django ORM类型错误"""
import re
from pathlib import Path
from typing import Any

def add_cast_import(content: str) -> str:
    """确保导入cast"""
    if 'cast(' in content and 'from typing import' in content:
        if not re.search(r'from typing import.*\bcast\b', content):
            # 在第一个from typing import行添加cast
            content = re.sub(
                r'(from typing import [^)]+)',
                lambda m: m.group(1) + ', cast' if ')' not in m.group(1) else m.group(1),
                content,
                count=1
            )
    return content

def fix_model_id_access(content: str) -> str:
    """修复Model.id访问的attr-defined错误"""
    # 查找 model.id 模式并添加cast
    # 例如: case.id -> cast(int, case.id)
    
    # 常见的模型变量名
    model_vars = ['case', 'sms', 'task', 'party', 'log', 'material', 'template', 
                  'binding', 'assignment', 'access', 'number', 'chat', 'obj', 'instance']
    
    for var in model_vars:
        # 修复 f-string 中的 {var.id}
        pattern = rf'(\{{)\s*{var}\.id\s*(\}})'
        replacement = rf'\1cast(int, {var}.id)\2'
        content = re.sub(pattern, replacement, content)
        
        # 修复普通表达式中的 var.id (但不在cast中)
        pattern = rf'(?<!cast\(int, )(?<!\w){var}\.id(?!\))'
        # 只在特定上下文中替换，避免过度替换
        # 例如: logger.info, return, if, ==, !=
        contexts = [
            (rf'(logger\.\w+\([^)]*){var}\.id', rf'\1cast(int, {var}.id)'),
            (rf'(return\s+){var}\.id', rf'\1cast(int, {var}.id)'),
            (rf'(if\s+){var}\.id', rf'\1cast(int, {var}.id)'),
            (rf'({var}\.id)(\s*[=!<>]+)', rf'cast(int, \1)\2'),
        ]
        
        for ctx_pattern, ctx_replacement in contexts:
            content = re.sub(ctx_pattern, ctx_replacement, content)
    
    return content

def fix_queryset_types(content: str) -> str:
    """为QuerySet添加泛型参数"""
    # QuerySet -> QuerySet[Model]
    # 需要识别模型类型
    
    # 查找 objects.all(), objects.filter() 等返回QuerySet的调用
    # Case.objects.all() -> QuerySet[Case]
    
    # 修复函数返回类型中的QuerySet
    pattern = r'-> QuerySet(?!\[)'
    
    # 尝试从上下文推断模型类型
    # 如果函数名包含模型名，使用该模型
    def infer_model(match: re.Match[str]) -> str:
        # 获取函数定义
        start = max(0, match.start() - 200)
        context = content[start:match.start()]
        
        # 查找def function_name
        func_match = re.search(r'def\s+(\w+)', context)
        if func_match:
            func_name = func_match.group(1)
            # 从函数名推断模型
            if 'case' in func_name.lower() and 'party' not in func_name.lower():
                return '-> QuerySet[Case]'
            elif 'party' in func_name.lower():
                return '-> QuerySet[CaseParty]'
            elif 'log' in func_name.lower():
                return '-> QuerySet[CaseLog]'
            elif 'material' in func_name.lower():
                return '-> QuerySet[CaseMaterial]'
            elif 'assignment' in func_name.lower():
                return '-> QuerySet[CaseAssignment]'
            elif 'access' in func_name.lower():
                return '-> QuerySet[CaseAccess]'
            elif 'number' in func_name.lower():
                return '-> QuerySet[CaseNumber]'
            elif 'chat' in func_name.lower():
                return '-> QuerySet[CaseChat]'
        
        # 默认使用Any
        return '-> QuerySet[Any]'
    
    content = re.sub(pattern, infer_model, content)
    
    # 确保导入QuerySet
    if 'QuerySet[' in content:
        if 'from django.db.models import' in content:
            if not re.search(r'from django\.db\.models import.*\bQuerySet\b', content):
                content = re.sub(
                    r'(from django\.db\.models import [^)]+)',
                    lambda m: m.group(1) + ', QuerySet' if ')' not in m.group(1) else m.group(1),
                    content,
                    count=1
                )
        elif 'from django.db import models' not in content:
            # 在导入区域添加
            lines = content.split('\n')
            insert_pos = 0
            for i, line in enumerate(lines):
                if line.startswith('from django'):
                    insert_pos = i + 1
                elif line.strip() and not line.startswith('#') and not line.startswith('from') and not line.startswith('import'):
                    break
            if insert_pos > 0:
                lines.insert(insert_pos, 'from django.db.models import QuerySet')
                content = '\n'.join(lines)
    
    return content

def process_file(file_path: Path) -> tuple[bool, str]:
    """处理单个文件"""
    try:
        content = file_path.read_text(encoding='utf-8')
        original = content
        
        # 应用修复
        content = fix_model_id_access(content)
        content = fix_queryset_types(content)
        content = add_cast_import(content)
        
        if content != original:
            file_path.write_text(content, encoding='utf-8')
            return True, "已修复"
        return False, "无需修复"
    except Exception as e:
        return False, f"错误: {e}"

def main() -> None:
    """主函数"""
    cases_dir = Path("apps/cases")
    
    if not cases_dir.exists():
        print(f"错误: {cases_dir} 不存在")
        return
    
    # 获取所有Python文件
    py_files = list(cases_dir.rglob("*.py"))
    
    print(f"找到 {len(py_files)} 个Python文件")
    
    fixed_count = 0
    for py_file in py_files:
        modified, msg = process_file(py_file)
        if modified:
            fixed_count += 1
            print(f"✓ {py_file.relative_to(cases_dir)}: {msg}")
    
    print(f"\n修复完成: {fixed_count}/{len(py_files)} 个文件被修改")

if __name__ == "__main__":
    main()
