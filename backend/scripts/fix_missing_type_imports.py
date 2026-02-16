#!/usr/bin/env python3
"""修复缺失的TYPE_CHECKING导入"""
import subprocess
import re
from pathlib import Path
from collections import defaultdict
from typing import Any

def get_mypy_errors():
    """获取mypy错误"""
    result = subprocess.run(
        ["python", "-m", "mypy", "apps/", "--strict", "--no-error-summary"],
        capture_output=True,
        text=True,
        cwd="."
    )
    return result.stdout + result.stderr

def parse_name_defined_errors(output: str):
    """解析name-defined错误"""
    lines = output.split('\n')
    errors = []
    
    i = 0
    while i < len(lines):
        line = lines[i]
        match = re.match(r'(.+?):(\d+):(\d+): error:', line)
        if match:
            file_path, line_no, col = match.groups()
            full_line = line
            if i + 1 < len(lines) and not lines[i + 1].startswith('apps/'):
                full_line += ' ' + lines[i + 1].strip()
            
            if '[name-defined]' in full_line:
                name_match = re.search(r'Name "([^"]+)" is not defined', full_line)
                if name_match:
                    name = name_match.group(1)
                    errors.append({
                        'file': file_path,
                        'line': int(line_no),
                        'col': int(col),
                        'name': name
                    })
        i += 1
    
    return errors

# 常见的类型导入映射（用于TYPE_CHECKING）
TYPE_IMPORTS = {
    # Service interfaces
    'ICaseService': 'from apps.cases.interfaces import ICaseService',
    'IClientService': 'from apps.client.interfaces import IClientService',
    'ILawyerService': 'from apps.lawyer.interfaces import ILawyerService',
    'ICaseChatService': 'from apps.cases.interfaces import ICaseChatService',
    
    # Services
    'ClientService': 'from apps.client.services import ClientService',
    'ClientIdentityDocService': 'from apps.client.services import ClientIdentityDocService',
    'LawyerAssignmentService': 'from apps.lawyer.services import LawyerAssignmentService',
    'CaseNumberExtractorService': 'from apps.automation.services.sms import CaseNumberExtractorService',
    'DocumentAttachmentService': 'from apps.automation.services.sms import DocumentAttachmentService',
    'SMSNotificationService': 'from apps.automation.services.sms import SMSNotificationService',
    'DocumentRenamer': 'from apps.documents.services import DocumentRenamer',
    
    # DTOs
    'ContractDTO': 'from apps.contracts.dtos import ContractDTO',
    'LawyerDTO': 'from apps.lawyer.dtos import LawyerDTO',
    'ContractPayment': 'from apps.contracts.models import ContractPayment',
    
    # Models
    'CourtSMS': 'from apps.automation.models import CourtSMS',
    
    # Exceptions
    'ValidationException': 'from apps.core.exceptions import ValidationException',
    'BusinessException': 'from apps.core.exceptions import BusinessException',
}

def fix_type_imports(errors):
    """修复TYPE_CHECKING导入"""
    print("\n=== 修复TYPE_CHECKING导入 ===\n")
    
    file_errors = defaultdict(list)
    for error in errors:
        file_errors[error['file']].append(error)
    
    fixed_count = 0
    
    for file_path, errs in file_errors.items():
        undefined_names = set(e['name'] for e in errs)
        
        # 找出可以通过TYPE_CHECKING导入修复的名称
        fixable_names = undefined_names & TYPE_IMPORTS.keys()
        
        if not fixable_names:
            continue
        
        print(f"修复文件: {file_path}")
        print(f"  需要导入: {', '.join(fixable_names)}")
        
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                content = f.read()
                lines = content.split('\n')
            
            # 检查是否已有TYPE_CHECKING块
            has_type_checking = 'from typing import TYPE_CHECKING' in content
            type_checking_start = -1
            type_checking_end = -1
            
            if has_type_checking:
                # 找到TYPE_CHECKING块的位置
                for i, line in enumerate(lines):
                    if 'if TYPE_CHECKING:' in line:
                        type_checking_start = i
                        # 找到块的结束位置
                        for j in range(i + 1, len(lines)):
                            if lines[j] and not lines[j].startswith(' ') and not lines[j].startswith('\t'):
                                type_checking_end = j
                                break
                        break
            
            # 检查哪些导入已经存在
            existing_imports = set()
            for name in fixable_names:
                import_stmt = TYPE_IMPORTS[name]
                if import_stmt in content:
                    existing_imports.add(name)
            
            names_to_add = fixable_names - existing_imports
            
            if not names_to_add:
                print(f"  跳过: 所有导入已存在")
                continue
            
            # 生成导入语句
            imports_to_add = [TYPE_IMPORTS[name] for name in sorted(names_to_add)]
            
            if has_type_checking and type_checking_start >= 0:
                # 添加到现有TYPE_CHECKING块
                insert_pos = type_checking_start + 1
                # 找到第一个导入语句的位置
                for i in range(type_checking_start + 1, type_checking_end if type_checking_end > 0 else len(lines)):
                    if lines[i].strip().startswith('from ') or lines[i].strip().startswith('import '):
                        insert_pos = i + 1
                
                # 插入导入（带缩进）
                indented_imports = ['    ' + imp for imp in imports_to_add]
                lines = lines[:insert_pos] + indented_imports + lines[insert_pos:]
                
            else:
                # 创建新的TYPE_CHECKING块
                # 找到插入位置（在普通导入之后）
                insert_pos = 0
                last_import_line = -1
                
                for i, line in enumerate(lines):
                    if line.startswith('from ') or line.startswith('import '):
                        last_import_line = i
                
                if last_import_line >= 0:
                    insert_pos = last_import_line + 1
                else:
                    # 没有找到导入，插入到文件开头（跳过docstring）
                    for i, line in enumerate(lines):
                        if not line.startswith('#') and not line.startswith('"""') and not line.startswith("'''"):
                            insert_pos = i
                            break
                
                # 插入TYPE_CHECKING块
                type_checking_block = [
                    '',
                    'from typing import TYPE_CHECKING',
                    '',
                    'if TYPE_CHECKING:',
                ] + ['    ' + imp for imp in imports_to_add]
                
                lines = lines[:insert_pos] + type_checking_block + [''] + lines[insert_pos:]
            
            # 写回文件
            new_content = '\n'.join(lines)
            with open(file_path, 'w', encoding='utf-8') as f:
                f.write(new_content)
            
            print(f"  ✓ 已添加 {len(names_to_add)} 个导入")
            fixed_count += len(names_to_add)
            
        except Exception as e:
            print(f"  错误: {e}")
    
    print(f"\n总共修复了 {fixed_count} 个缺失导入")
    return fixed_count

if __name__ == "__main__":
    print("正在分析name-defined错误...")
    errors = parse_name_defined_errors(get_mypy_errors())
    
    print(f"总共 {len(errors)} 个name-defined错误\n")
    
    # 修复TYPE_CHECKING导入
    if errors:
        fix_type_imports(errors)
        
        # 再次检查
        print("\n\n=== 再次运行mypy检查 ===")
        new_errors = parse_name_defined_errors(get_mypy_errors())
        print(f"\n修复后剩余 {len(new_errors)} 个name-defined错误")
        print(f"减少了 {len(errors) - len(new_errors)} 个错误")
