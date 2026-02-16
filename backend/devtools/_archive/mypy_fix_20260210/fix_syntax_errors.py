#!/usr/bin/env python3
"""修复语法错误"""

import re
from pathlib import Path


def fix_file(file_path: Path) -> bool:
    """修复单个文件的语法错误"""
    try:
        content = file_path.read_text(encoding='utf-8')
        original = content
        
        # 修复 1: *: Any 应该是 *
        content = re.sub(r'\(\s*\*:\s*Any\s*,', '(*, ', content)
        content = re.sub(r',\s*\*:\s*Any\s*,', ', *, ', content)
        
        # 修复 2: dict[str, Any]: Any 应该是 dict[str, Any]
        content = re.sub(r'(dict\[str, Any\]):\s*Any', r'\1', content)
        content = re.sub(r'(dict\[str, str\] \| None):\s*Any', r'\1', content)
        
        # 修复 3: 参数类型后面多了 : Any
        # 例如: param: Type: Any 应该是 param: Type
        content = re.sub(r'(\w+:\s*[A-Za-z_][A-Za-z0-9_\[\], |]*?):\s*Any(\s*[,)])', r'\1\2', content)
        
        if content != original:
            file_path.write_text(content, encoding='utf-8')
            return True
        
        return False
        
    except Exception as e:
        print(f"错误: {file_path}: {e}")
        return False


def main():
    """主函数"""
    print("=" * 80)
    print("修复语法错误")
    print("=" * 80)
    
    # 查找所有 Python 文件
    services_dir = Path(__file__).parent / "apps"
    py_files = []
    
    for app_dir in services_dir.iterdir():
        if app_dir.is_dir() and not app_dir.name.startswith('.'):
            services_path = app_dir / "services"
            if services_path.exists():
                py_files.extend(services_path.rglob("*.py"))
    
    print(f"\n扫描 {len(py_files)} 个文件...\n")
    
    fixed_count = 0
    for file_path in py_files:
        if fix_file(file_path):
            fixed_count += 1
            print(f"✓ {file_path.relative_to(Path(__file__).parent)}")
    
    print(f"\n{'=' * 80}")
    print(f"修复了 {fixed_count} 个文件")
    print(f"{'=' * 80}")
    
    # 再次检查语法错误
    print("\n检查剩余语法错误...")
    import subprocess
    result = subprocess.run(
        ["find", "apps/*/services", "-name", "*.py", "-exec", "python3", "-m", "py_compile", "{}", ";"],
        capture_output=True,
        text=True,
        cwd=Path(__file__).parent
    )
    
    syntax_errors = result.stderr.count("SyntaxError")
    if syntax_errors == 0:
        print("✅ 无语法错误！")
    else:
        print(f"⚠️  还有 {syntax_errors} 个语法错误")
        print("\n前几个错误:")
        lines = result.stderr.split('\n')
        for i, line in enumerate(lines[:20]):
            if line.strip():
                print(f"  {line}")


if __name__ == "__main__":
    main()
