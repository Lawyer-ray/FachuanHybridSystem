#!/usr/bin/env python3
"""
修复 contracts 模块剩余的类型错误

策略：
1. 为 Django Model 的 .id 属性使用 cast(Any, obj).id
2. 修复缺少的类型注解
3. 修复 DTO 导入问题
"""

import re
from pathlib import Path
from typing import List, Tuple


def add_cast_import(content: str) -> str:
    """确保有 cast 导入"""
    if 'from typing import' in content and 'cast' not in content:
        content = re.sub(
            r'from typing import ([^\n]+)',
            lambda m: f"from typing import {m.group(1)}, cast" if 'cast' not in m.group(1) else m.group(0),
            content,
            count=1
        )
    return content


def fix_model_id_access(content: str) -> str:
    """修复 Model.id 访问 - 使用 cast(Any, obj).id"""
    # 常见的模式：contract.id, obj.id, etc.
    # 但要避免已经 cast 过的
    patterns = [
        # contract.id -> cast(Any, contract).id
        (r'\bcontract\.id\b(?!\))', r'cast(Any, contract).id'),
        # obj.id -> cast(Any, obj).id (但要小心不要重复 cast)
        (r'(?<!cast\(Any, )(?<!cast\(Any, )\bobj\.id\b(?!\))', r'cast(Any, obj).id'),
        # payment.id -> cast(Any, payment).id
        (r'\bpayment\.id\b(?!\))', r'cast(Any, payment).id'),
        # reminder.id -> cast(Any, reminder).id
        (r'\breminder\.id\b(?!\))', r'cast(Any, reminder).id'),
        # lawyer.id -> cast(Any, lawyer).id
        (r'\blawyer\.id\b(?!\))', r'cast(Any, lawyer).id'),
    ]
    
    for pattern, replacement in patterns:
        content = re.sub(pattern, replacement, content)
    
    return content


def fix_unused_type_ignore(content: str) -> str:
    """移除未使用的 type: ignore"""
    # 如果一行有 # type: ignore 但实际上不需要，移除它
    content = re.sub(r'\s*#\s*type:\s*ignore\[return-value\]\s*$', '', content, flags=re.MULTILINE)
    return content


def fix_missing_return_types(content: str) -> str:
    """修复缺少的返回类型注解"""
    # 查找没有返回类型的函数定义
    # def function_name(...) -> None:
    patterns = [
        # API 函数通常返回 HttpResponse
        (r'(@router\.(get|post|put|delete|patch)\([^\)]+\)\s+def\s+\w+\([^)]+\)):', r'\1 -> Any:'),
    ]
    
    for pattern, replacement in patterns:
        content = re.sub(pattern, replacement, content)
    
    return content


def fix_dto_imports(content: str) -> str:
    """修复 DTO 导入问题"""
    # 如果使用了 ContractDTO 但没有导入
    if 'ContractDTO' in content and 'from apps.contracts.dtos import' not in content:
        # 在文件开头添加导入
        lines = content.split('\n')
        import_index = -1
        for i, line in enumerate(lines):
            if line.startswith('from apps.') or line.startswith('import '):
                import_index = i
        
        if import_index >= 0:
            lines.insert(import_index + 1, 'from apps.contracts.dtos import ContractDTO')
            content = '\n'.join(lines)
    
    # 同样处理 LawyerDTO
    if 'LawyerDTO' in content and 'from apps.organization.dtos import' not in content:
        lines = content.split('\n')
        import_index = -1
        for i, line in enumerate(lines):
            if line.startswith('from apps.') or line.startswith('import '):
                import_index = i
        
        if import_index >= 0:
            lines.insert(import_index + 1, 'from apps.organization.dtos import LawyerDTO')
            content = '\n'.join(lines)
    
    return content


def fix_file(file_path: Path) -> Tuple[bool, str]:
    """修复单个文件"""
    try:
        content = file_path.read_text(encoding='utf-8')
        original = content
        
        # 应用修复
        content = add_cast_import(content)
        content = fix_model_id_access(content)
        content = fix_unused_type_ignore(content)
        content = fix_missing_return_types(content)
        content = fix_dto_imports(content)
        
        if content != original:
            file_path.write_text(content, encoding='utf-8')
            return True, "修复成功"
        else:
            return False, "无需修复"
    except Exception as e:
        return False, f"错误: {e}"


def main():
    """主函数"""
    backend_path = Path(__file__).parent.parent
    contracts_path = backend_path / "apps" / "contracts"
    
    print(f"修复 {contracts_path} 目录...")
    
    # 重点修复的文件
    priority_files = [
        "services/contract_service.py",
        "services/contract/contract_mutation_facade.py",
        "services/contract/contract_access_policy.py",
        "services/contract/contract_workflow_service.py",
        "services/payment/contract_payment_service.py",
        "services/payment/contract_finance_mutation_service.py",
        "api/contractreminder_api.py",
        "api/contractpayment_api.py",
        "api/contractfinance_api.py",
        "schemas/contract_schemas.py",
    ]
    
    fixed_count = 0
    for rel_path in priority_files:
        file_path = contracts_path / rel_path
        if file_path.exists():
            fixed, msg = fix_file(file_path)
            if fixed:
                fixed_count += 1
                print(f"✓ {rel_path}")
    
    print(f"\n修复完成: {fixed_count}/{len(priority_files)} 个文件")


if __name__ == "__main__":
    main()
