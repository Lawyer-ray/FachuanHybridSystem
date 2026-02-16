#!/usr/bin/env python3
"""批量修复简单的类型注解错误"""

import re
from pathlib import Path

# 需要修复的文件列表（从 mypy 错误中提取）
FILES_TO_FIX = [
    "apps/automation/services/scraper/core/captcha_service.py",
    "apps/automation/services/document/document_processing.py",
    "apps/documents/services/evidence_storage.py",
    "apps/automation/services/token/token_service_adapter.py",
    "apps/cases/services/case/assembler/case_dto_assembler.py",
    "apps/automation/services/ocr/ocr_service.py",
    "apps/automation/services/image_rotation/orientation/service.py",
    "apps/automation/services/image_rotation/pdf_extraction_service.py",
    "apps/documents/services/placeholders/registry.py",
    "apps/automation/services/chat/audit_logger.py",
]

def add_type_annotation(line: str) -> tuple[str, bool]:
    """为函数添加类型注解"""
    # 模式 1: def method(self): -> def method(self) -> None:
    if re.match(r'^\s+def \w+\(self\):\s*$', line):
        return line.rstrip() + ' -> None:\n', True
    
    # 模式 2: def function(): -> def function() -> None:
    if re.match(r'^\s*def \w+\(\):\s*$', line):
        return line.rstrip() + ' -> None:\n', True
    
    # 模式 3: def __init__(self, ...): -> def __init__(self, ...) -> None:
    if re.match(r'^\s+def __\w+__\(', line) and line.rstrip().endswith(':'):
        if ' -> ' not in line:
            return line.rstrip()[:-1] + ' -> None:\n', True
    
    return line, False

def ensure_any_import(content: str) -> str:
    """确保文件有 Any 导入"""
    if 'from typing import' in content and 'Any' not in content:
        # 找到 typing 导入行并添加 Any
        lines = content.split('\n')
        for i, line in enumerate(lines):
            if line.startswith('from typing import'):
                if 'Any' not in line:
                    # 添加 Any 到导入列表
                    lines[i] = line.rstrip().rstrip(')') + ', Any'
                    if not line.rstrip().endswith(')'):
                        lines[i] += ')'
                break
        return '\n'.join(lines)
    elif 'from typing import' not in content and 'Any' in content:
        # 需要添加 typing 导入
        lines = content.split('\n')
        # 找到第一个 import 语句后插入
        for i, line in enumerate(lines):
            if line.startswith(('from ', 'import ')) and 'future' not in line:
                lines.insert(i + 1, 'from typing import Any')
                break
        return '\n'.join(lines)
    return content

def fix_file(file_path: Path) -> int:
    """修复单个文件，返回修复的行数"""
    if not file_path.exists():
        print(f"⚠️  文件不存在: {file_path}")
        return 0
    
    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            lines = f.readlines()
        
        modified = False
        fixed_count = 0
        
        for i, line in enumerate(lines):
            new_line, changed = add_type_annotation(line)
            if changed:
                lines[i] = new_line
                modified = True
                fixed_count += 1
        
        if modified:
            content = ''.join(lines)
            content = ensure_any_import(content)
            
            with open(file_path, 'w', encoding='utf-8') as f:
                f.write(content)
            
            print(f"✓ {file_path}: 修复 {fixed_count} 处")
            return fixed_count
        
        return 0
    
    except Exception as e:
        print(f"✗ {file_path}: {e}")
        return 0

def main():
    """主函数"""
    total_fixed = 0
    
    print("开始批量修复类型注解...\n")
    
    for file_path_str in FILES_TO_FIX:
        file_path = Path(file_path_str)
        fixed = fix_file(file_path)
        total_fixed += fixed
    
    print(f"\n总计修复: {total_fixed} 处")

if __name__ == '__main__':
    main()
