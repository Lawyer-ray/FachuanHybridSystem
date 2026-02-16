#!/usr/bin/env python3
"""修复错误的 deque 类型注解"""
import re
from pathlib import Path

def fix_deque_types(file_path: Path) -> int:
    """修复 deque[dict[str, Any]] 回到正确的类型"""
    try:
        content = file_path.read_text()
        original = content
        
        # 查找 deque[dict[str, Any]] 并尝试恢复原始类型
        # 这个比较难，因为我们不知道原始类型是什么
        # 暂时先移除错误的类型注解，让 mypy 推断
        content = re.sub(r': deque\[dict\[str, Any\]\]', ': deque[Any]', content)
        
        if content != original:
            file_path.write_text(content)
            return 1
        return 0
    except Exception as e:
        print(f"错误: {file_path}: {e}")
        return 0

def main():
    apps_dir = Path('apps')
    py_files = list(apps_dir.rglob('*.py'))
    
    modified = 0
    for py_file in py_files:
        if fix_deque_types(py_file):
            modified += 1
            print(f"✓ {py_file}")
    
    print(f"\n完成！共修改 {modified} 个文件")

if __name__ == '__main__':
    main()
