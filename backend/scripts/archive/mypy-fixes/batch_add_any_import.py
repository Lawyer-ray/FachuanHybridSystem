"""批量添加Any导入"""

import sys
from pathlib import Path

backend_path = Path(__file__).parent.parent

# 读取需要修复的文件列表
files = [
    "apps/automation/services/document_delivery/api/document_delivery_api_service.py",
    "apps/automation/services/document_delivery/court_document_api_client.py",
    "apps/automation/services/document_delivery/document_delivery_service.py",
    "apps/automation/services/document_delivery/playwright/document_delivery_playwright_service.py",
    "apps/automation/services/document_delivery/processor/document_delivery_processor.py",
    "apps/automation/services/insurance/preservation_quote_service.py",
    "apps/automation/services/scraper/core/anti_detection.py",
    "apps/automation/services/scraper/core/browser_manager.py",
    "apps/automation/services/scraper/core/security_service.py",
    "apps/automation/services/sms/matching/party_matching_service.py",
]

fixed = 0
for file_path in files:
    full_path = backend_path / file_path
    
    if not full_path.exists():
        print(f"✗ 文件不存在: {file_path}")
        continue
    
    lines = full_path.read_text(encoding="utf-8").split('\n')
    
    # 查找typing导入行
    typing_import_line = -1
    for i, line in enumerate(lines):
        if line.startswith('from typing import'):
            typing_import_line = i
            break
    
    if typing_import_line >= 0:
        # 已有typing导入，检查是否有Any
        import_line = lines[typing_import_line]
        if 'Any' not in import_line:
            # 添加Any到导入
            import_line = import_line.replace('from typing import ', '')
            imports = [imp.strip() for imp in import_line.split(',')]
            imports.append('Any')
            imports = sorted(set(imports))
            lines[typing_import_line] = f"from typing import {', '.join(imports)}"
            
            full_path.write_text('\n'.join(lines), encoding="utf-8")
            print(f"✓ {file_path}")
            fixed += 1
        else:
            print(f"- {file_path} (已有Any)")
    else:
        # 没有typing导入，添加新的
        # 找到第一个import语句后面
        insert_pos = 0
        for i, line in enumerate(lines):
            if line.startswith('import ') or line.startswith('from '):
                insert_pos = i + 1
        
        lines.insert(insert_pos, 'from typing import Any')
        full_path.write_text('\n'.join(lines), encoding="utf-8")
        print(f"✓ {file_path} (新增)")
        fixed += 1

print(f"\n修复了 {fixed} 个文件")
