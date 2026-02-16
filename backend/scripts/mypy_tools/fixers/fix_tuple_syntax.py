#!/usr/bin/env python3
"""修复错误的tuple类型注解语法"""
import re
from pathlib import Path

def fix_tuple_syntax(file_path: Path) -> bool:
    """修复文件中的tuple类型注解语法错误"""
    try:
        content = file_path.read_text(encoding='utf-8')
        original = content
        
        # 修复 tuple[Any, ...][type1, type2] -> tuple[type1, type2]
        pattern = r'tuple\[Any, \.\.\.\]\[([^\]]+)\]'
        content = re.sub(pattern, r'tuple[\1]', content)
        
        # 修复 list[Any]["Type"] -> list["Type"]
        pattern2 = r'list\[Any\]\[([^\]]+)\]'
        content = re.sub(pattern2, r'list[\1]', content)
        
        # 修复 dict[Any, Any][key, value] -> dict[key, value]
        pattern3 = r'dict\[Any, Any\]\[([^\]]+)\]'
        content = re.sub(pattern3, r'dict[\1]', content)
        
        # 修复 dict[str, Any][key, value] -> dict[key, value]
        pattern4 = r'dict\[str, Any\]\[([^\]]+)\]'
        content = re.sub(pattern4, r'dict[\1]', content)
        
        if content != original:
            file_path.write_text(content, encoding='utf-8')
            return True
        return False
    except Exception as e:
        print(f"处理文件 {file_path} 时出错: {e}")
        return False

def main() -> None:
    """主函数"""
    backend_dir = Path(__file__).parent.parent
    apps_dir = backend_dir / "apps"
    
    fixed_count = 0
    for py_file in apps_dir.rglob("*.py"):
        if fix_tuple_syntax(py_file):
            print(f"已修复: {py_file.relative_to(backend_dir)}")
            fixed_count += 1
    
    print(f"\n总共修复了 {fixed_count} 个文件")

if __name__ == "__main__":
    main()
