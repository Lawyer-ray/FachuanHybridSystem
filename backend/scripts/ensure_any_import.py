#!/usr/bin/env python3
"""确保所有使用Any的文件都导入了Any"""

import re
from pathlib import Path


def ensure_any_import(content: str) -> str:
    """确保导入了Any"""
    # 检查是否使用了Any
    if 'Any' not in content:
        return content
    
    # 检查是否已经导入了Any
    if re.search(r'from typing import.*\bAny\b', content):
        return content
    
    # 需要添加Any导入
    if 'from typing import' in content:
        # 在现有的typing导入中添加Any
        content = re.sub(
            r'(from typing import )([^\n]+)',
            lambda m: f"{m.group(1)}Any, {m.group(2)}" if not m.group(2).startswith('Any') else m.group(0),
            content,
            count=1
        )
    else:
        # 添加新的typing导入
        lines = content.split('\n')
        insert_pos = 0
        for i, line in enumerate(lines):
            if line.startswith('from ') or line.startswith('import '):
                insert_pos = i + 1
            elif line.strip() and not line.startswith('#'):
                break
        lines.insert(insert_pos, 'from typing import Any')
        content = '\n'.join(lines)
    
    return content


def process_file(file_path: Path) -> bool:
    """处理单个文件"""
    try:
        content = file_path.read_text(encoding='utf-8')
        original = content
        
        content = ensure_any_import(content)
        
        if content != original:
            file_path.write_text(content, encoding='utf-8')
            return True
        return False
    except Exception as e:
        print(f"✗ 错误 {file_path}: {e}")
        return False


def main() -> None:
    """主函数"""
    base_dir = Path(__file__).parent.parent / "apps"
    
    fixed_count = 0
    for py_file in base_dir.rglob("*.py"):
        if "__pycache__" in str(py_file):
            continue
        if process_file(py_file):
            fixed_count += 1
    
    print(f"完成! 修复了 {fixed_count} 个文件")


if __name__ == "__main__":
    main()
