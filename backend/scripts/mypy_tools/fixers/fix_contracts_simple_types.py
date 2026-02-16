#!/usr/bin/env python3
"""
批量修复 contracts 模块的简单类型错误

修复内容:
1. 泛型类型参数缺失 (dict -> dict[str, Any], list[dict] -> list[dict[str, Any]])
2. QuerySet 泛型参数缺失
3. API 函数类型注解 (添加 HttpRequest 和 HttpResponse 类型)
"""

import re
from pathlib import Path
from typing import Set


def fix_generic_types(content: str, file_path: Path) -> tuple[str, int]:
    """修复泛型类型参数缺失"""
    original = content
    fixes = 0
    
    # 修复 -> dict: 或 -> dict\n
    pattern = r'-> dict([:\n])'
    if re.search(pattern, content):
        content = re.sub(pattern, r'-> dict[str, Any]\1', content)
        fixes += len(re.findall(pattern, original))
    
    # 修复 : dict = 或 : dict\s*=
    pattern = r': dict(\s*=)'
    if re.search(pattern, content):
        content = re.sub(pattern, r': dict[str, Any]\1', content)
        fixes += len(re.findall(pattern, original))
    
    # 修复 : dict | None 或 : dict|None
    pattern = r': dict(\s*\|)'
    if re.search(pattern, content):
        content = re.sub(pattern, r': dict[str, Any]\1', content)
        fixes += len(re.findall(pattern, original))
    
    # 修复 list[dict] -> list[dict[str, Any]]
    pattern = r'list\[dict\]'
    if re.search(pattern, content):
        content = re.sub(pattern, r'list[dict[str, Any]]', content)
        fixes += len(re.findall(pattern, original))
    
    # 修复 Optional[list[dict]] -> Optional[list[dict[str, Any]]]
    pattern = r'Optional\[list\[dict\]\]'
    if re.search(pattern, content):
        content = re.sub(pattern, r'Optional[list[dict[str, Any]]]', content)
        fixes += len(re.findall(pattern, original))
    
    return content, fixes


def fix_queryset_types(content: str, file_path: Path) -> tuple[str, int]:
    """修复 QuerySet 泛型参数缺失"""
    original = content
    fixes = 0
    
    # 根据文件路径推断 QuerySet 的模型类型
    model_map = {
        'contract_reminder': 'ContractReminder',
        'contract_payment': 'ContractPayment',
        'contract': 'Contract',
        'supplementary_agreement': 'SupplementaryAgreement',
    }
    
    model_type = None
    for key, value in model_map.items():
        if key in str(file_path):
            model_type = value
            break
    
    if not model_type:
        model_type = 'Any'  # 默认使用 Any
    
    # 修复 -> QuerySet: 或 -> QuerySet\n
    pattern = r'-> QuerySet([:\n])'
    if re.search(pattern, content):
        content = re.sub(pattern, rf'-> QuerySet[{model_type}]\1', content)
        fixes += len(re.findall(pattern, original))
    
    # 修复 : QuerySet = 或 : QuerySet\s*=
    pattern = r': QuerySet(\s*[,=\)])'
    if re.search(pattern, content):
        content = re.sub(pattern, rf': QuerySet[{model_type}]\1', content)
        fixes += len(re.findall(pattern, original))
    
    return content, fixes


def fix_api_function_types(content: str, file_path: Path) -> tuple[str, int]:
    """修复 API 函数类型注解"""
    if not str(file_path).endswith('_api.py'):
        return content, 0
    
    original = content
    fixes = 0
    
    # 修复 def xxx(request, -> def xxx(request: HttpRequest,
    pattern = r'\bdef\s+\w+\(request,'
    matches = re.findall(pattern, content)
    if matches:
        content = re.sub(r'\bdef\s+(\w+)\(request,', r'def \1(request: HttpRequest,', content)
        fixes += len(matches)
    
    # 修复 def xxx(request) -> def xxx(request: HttpRequest)
    pattern = r'\bdef\s+\w+\(request\):'
    matches = re.findall(pattern, content)
    if matches:
        content = re.sub(r'\bdef\s+(\w+)\(request\):', r'def \1(request: HttpRequest):', content)
        fixes += len(matches)
    
    # 为没有返回类型的 API 函数添加 -> HttpResponse
    # 匹配 def xxx(...): 但没有 ->
    lines = content.split('\n')
    new_lines = []
    for i, line in enumerate(lines):
        # 检查是否是函数定义行
        if re.match(r'^def\s+\w+\(', line) and '->' not in line and line.strip().endswith(':'):
            # 添加 -> HttpResponse
            line = line.rstrip(':') + ' -> HttpResponse:'
            fixes += 1
        new_lines.append(line)
    
    if fixes > 0:
        content = '\n'.join(new_lines)
    
    return content, fixes


def ensure_imports(content: str, file_path: Path) -> str:
    """确保必要的导入存在"""
    imports_to_add = []
    
    # 检查是否需要 Any
    if 'Any' in content and 'from typing import' in content:
        if not re.search(r'from typing import.*\bAny\b', content):
            imports_to_add.append('Any')
    
    # 检查是否需要 HttpRequest, HttpResponse
    if '_api.py' in str(file_path):
        if 'HttpRequest' in content and 'from django.http import' not in content:
            # 添加 django.http 导入
            if 'import' in content:
                # 在第一个 import 后添加
                lines = content.split('\n')
                for i, line in enumerate(lines):
                    if line.startswith('from ') or line.startswith('import '):
                        lines.insert(i + 1, 'from django.http import HttpRequest, HttpResponse')
                        content = '\n'.join(lines)
                        break
    
    # 添加 typing 导入
    if imports_to_add:
        # 查找现有的 from typing import
        match = re.search(r'from typing import ([^\n]+)', content)
        if match:
            existing_imports = match.group(1)
            # 添加缺失的导入
            for imp in imports_to_add:
                if imp not in existing_imports:
                    content = content.replace(
                        f'from typing import {existing_imports}',
                        f'from typing import {existing_imports}, {imp}'
                    )
        else:
            # 没有 typing 导入，添加一个
            if 'import' in content:
                lines = content.split('\n')
                for i, line in enumerate(lines):
                    if line.startswith('from ') or line.startswith('import '):
                        lines.insert(i, f'from typing import {", ".join(imports_to_add)}')
                        content = '\n'.join(lines)
                        break
    
    return content


def fix_file(file_path: Path) -> int:
    """修复单个文件"""
    try:
        content = file_path.read_text(encoding='utf-8')
        original = content
        total_fixes = 0
        
        # 应用各种修复
        content, fixes = fix_generic_types(content, file_path)
        total_fixes += fixes
        
        content, fixes = fix_queryset_types(content, file_path)
        total_fixes += fixes
        
        content, fixes = fix_api_function_types(content, file_path)
        total_fixes += fixes
        
        # 确保导入
        if total_fixes > 0:
            content = ensure_imports(content, file_path)
        
        # 只有在有修改时才写入
        if content != original:
            file_path.write_text(content, encoding='utf-8')
            print(f"✓ {file_path.relative_to(Path.cwd())}: {total_fixes} 处修复")
            return total_fixes
        
        return 0
    except Exception as e:
        print(f"✗ {file_path}: {e}")
        return 0


def main():
    """主函数"""
    backend_path = Path(__file__).parent.parent
    contracts_path = backend_path / 'apps' / 'contracts'
    
    if not contracts_path.exists():
        print(f"错误: {contracts_path} 不存在")
        return
    
    print("开始批量修复 contracts 模块的简单类型错误...\n")
    
    total_files = 0
    total_fixes = 0
    
    # 遍历所有 Python 文件
    for py_file in contracts_path.rglob('*.py'):
        if py_file.name == '__init__.py':
            continue
        
        fixes = fix_file(py_file)
        if fixes > 0:
            total_files += 1
            total_fixes += fixes
    
    print(f"\n修复完成!")
    print(f"修改文件数: {total_files}")
    print(f"总修复数: {total_fixes}")


if __name__ == '__main__':
    main()
