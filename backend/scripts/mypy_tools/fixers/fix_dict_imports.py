#!/usr/bin/env python3
"""批量修复缺少Dict导入的文件"""

import re
from pathlib import Path

files_to_fix = [
    "apps/core/config/schema_migrator.py",
    "apps/automation/utils/file_utils.py",
    "apps/automation/services/scraper/core/validator_service.py",
    "apps/automation/services/scraper/core/monitor_service.py",
    "apps/automation/services/fee_notice/extraction_service.py",
    "apps/automation/services/document/document_processing_service_adapter.py",
    "apps/automation/services/court_document_recognition/extractor_parsers.py",
    "apps/documents/services/placeholders/litigation/defense_party_service.py",
    "apps/client/services/property_clue_service.py",
    "apps/client/services/client_service.py",
    "apps/client/services/client_admin_service.py",
]

def fix_file(filepath: str) -> bool:
    """修复单个文件的Dict导入"""
    path = Path(filepath)
    if not path.exists():
        print(f"跳过不存在的文件: {filepath}")
        return False
    
    content = path.read_text(encoding='utf-8')
    
    # 查找from typing import行
    pattern = r'(from typing import )([^\n]+)'
    matches = list(re.finditer(pattern, content))
    
    if not matches:
        print(f"跳过没有typing导入的文件: {filepath}")
        return False
    
    # 检查是否已经有Dict
    for match in matches:
        imports = match.group(2)
        if 'Dict' in imports:
            print(f"跳过已有Dict导入的文件: {filepath}")
            return False
    
    # 在第一个typing导入中添加Dict
    match = matches[0]
    old_imports = match.group(2).strip()
    
    # 解析现有导入
    import_list = [imp.strip() for imp in old_imports.split(',')]
    
    # 添加Dict并排序
    if 'Dict' not in import_list:
        import_list.append('Dict')
        import_list.sort()
    
    new_imports = ', '.join(import_list)
    new_line = f"from typing import {new_imports}"
    
    # 替换
    new_content = content[:match.start()] + new_line + content[match.end():]
    
    path.write_text(new_content, encoding='utf-8')
    print(f"✓ 修复: {filepath}")
    return True

def main():
    fixed_count = 0
    for filepath in files_to_fix:
        if fix_file(filepath):
            fixed_count += 1
    
    print(f"\n总计修复 {fixed_count} 个文件")

if __name__ == "__main__":
    main()
