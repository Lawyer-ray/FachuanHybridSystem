#!/usr/bin/env python3
"""
批量修复所有剩余的语法错误
"""
import re
from pathlib import Path

def fix_file(file_path: str) -> int:
    """修复单个文件中的所有语法错误"""
    path = Path(file_path)
    if not path.exists():
        return 0
    
    content = path.read_text()
    original = content
    fixes = 0
    
    # 修复模式 1: | None: Any = None → | None = None
    pattern1 = r'\|\s*None:\s*Any\s*='
    if re.search(pattern1, content):
        content = re.sub(pattern1, '| None =', content)
        fixes += 1
    
    # 修复模式 2: Callable[..., Any]: Any → Callable[..., Any]
    pattern2 = r'Callable\[\.\.\..*?\]:\s*Any'
    if re.search(pattern2, content):
        content = re.sub(pattern2, lambda m: m.group(0).replace(': Any', ''), content)
        fixes += 1
    
    # 修复模式 3: dict[...] | None: Any = None → dict[...] | None = None
    pattern3 = r'dict\[[^\]]+\]\s*\|\s*None:\s*Any\s*='
    if re.search(pattern3, content):
        content = re.sub(pattern3, lambda m: m.group(0).replace(': Any', ''), content)
        fixes += 1
    
    # 修复模式 4: list[...] | None: Any = None → list[...] | None = None
    pattern4 = r'list\[[^\]]+\]\s*\|\s*None:\s*Any\s*='
    if re.search(pattern4, content):
        content = re.sub(pattern4, lambda m: m.group(0).replace(': Any', ''), content)
        fixes += 1
    
    if content != original:
        path.write_text(content)
        print(f"✓ 修复 {file_path} ({fixes} 处)")
        return fixes
    
    return 0

def main():
    # 查找所有 services 文件
    services_dirs = [
        "apps/automation/services",
        "apps/cases/services",
        "apps/contracts/services",
        "apps/documents/services",
        "apps/litigation_ai/services",
        "apps/client/services",
        "apps/organization/services",
        "apps/core/services",
    ]
    
    total_fixes = 0
    files_fixed = 0
    
    for services_dir in services_dirs:
        path = Path(services_dir)
        if not path.exists():
            continue
        
        for py_file in path.rglob("*.py"):
            fixes = fix_file(str(py_file))
            if fixes > 0:
                total_fixes += fixes
                files_fixed += 1
    
    print(f"\n✅ 修复了 {files_fixed} 个文件，共 {total_fixes} 处")

if __name__ == '__main__':
    main()
