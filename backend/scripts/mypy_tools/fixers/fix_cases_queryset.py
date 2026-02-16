#!/usr/bin/env python3
"""
修复cases模块中的QuerySet类型参数问题
Django 5.0+ 的 QuerySet 需要两个类型参数: QuerySet[Model, Model]
"""
import re
from pathlib import Path

def fix_file(file_path: Path) -> bool:
    """修复单个文件"""
    try:
        content = file_path.read_text(encoding="utf-8")
        original = content
        
        # 修复 QuerySet[Model] -> QuerySet[Model, Model]
        # 匹配 QuerySet[单个类型] 但不匹配已经有两个参数的
        content = re.sub(
            r'QuerySet\[(\w+)\](?!\s*,)',
            r'QuerySet[\1, \1]',
            content
        )
        
        if content != original:
            file_path.write_text(content, encoding="utf-8")
            return True
        return False
    except Exception as e:
        print(f"处理文件 {file_path} 时出错: {e}")
        return False

def main() -> None:
    """主函数"""
    cases_dir = Path("apps/cases")
    if not cases_dir.exists():
        print(f"目录不存在: {cases_dir}")
        return
    
    fixed_count = 0
    total_count = 0
    
    # 遍历所有Python文件
    for py_file in cases_dir.rglob("*.py"):
        total_count += 1
        if fix_file(py_file):
            fixed_count += 1
            print(f"✓ 修复: {py_file}")
    
    print(f"\n总计: 检查了 {total_count} 个文件, 修复了 {fixed_count} 个文件")

if __name__ == "__main__":
    main()
