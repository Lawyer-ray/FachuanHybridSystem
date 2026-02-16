#!/usr/bin/env python3
"""
修复 'from typing import Any' 插入到错误位置的问题
"""

from pathlib import Path
import re

def fix_file(file_path: Path) -> bool:
    """修复单个文件的导入位置"""
    content = file_path.read_text()
    
    # 检查是否有错误的导入位置
    # 模式: from xxx import (\nfrom typing import Any\n    yyy,\n)
    pattern = r'(from [^\n]+ import \()\nfrom typing import Any\n(\s+[^\n]+)'
    
    if not re.search(pattern, content):
        return False
    
    # 移除错误位置的 'from typing import Any'
    content = re.sub(r'\nfrom typing import Any\n(?=\s+\w)', '\n', content)
    
    # 检查是否已有 typing 导入
    has_typing = 'from typing import' in content
    
    if not has_typing:
        # 在 from __future__ import annotations 之后添加
        if 'from __future__ import annotations' in content:
            content = content.replace(
                'from __future__ import annotations\n',
                'from __future__ import annotations\nfrom typing import Any\n'
            )
        else:
            # 在第一个 import 之前添加
            lines = content.split('\n')
            for i, line in enumerate(lines):
                if line.startswith('from ') or line.startswith('import '):
                    lines.insert(i, 'from typing import Any')
                    break
            content = '\n'.join(lines)
    
    file_path.write_text(content)
    return True

def main():
    apps_dir = Path('apps')
    fixed = 0
    
    for py_file in apps_dir.rglob('*.py'):
        if fix_file(py_file):
            print(f"✅ {py_file}")
            fixed += 1
    
    print(f"\n修复了 {fixed} 个文件")

if __name__ == "__main__":
    main()
