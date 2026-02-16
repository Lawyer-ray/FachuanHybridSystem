#!/usr/bin/env python3
"""
批量修复 api/schemas 层的类型注解问题
基于 batch 2 (services 层) 的成功经验
"""
import re
import sys
from pathlib import Path
from typing import Any

def fix_file(file_path: Path) -> tuple[int, list[str]]:
    """修复单个文件的类型注解问题"""
    try:
        content = file_path.read_text(encoding='utf-8')
        original = content
        changes = []
        
        # 1. 修复 from_model 方法缺少返回类型
        # def from_model(cls, obj): → def from_model(cls, obj: Any) -> "ClassName":
        class_name_match = re.search(r'class\s+(\w+)', content)
        if class_name_match:
            class_name = class_name_match.group(1)
            pattern = r'(\s+)def from_model\(cls,\s*obj\):'
            replacement = rf'\1def from_model(cls, obj: Any) -> "{class_name}":'
            if re.search(pattern, content):
                content = re.sub(pattern, replacement, content)
                changes.append(f"Added type annotation to from_model method")
        
        # 2. 修复缺少参数类型的函数
        # def func(self, param): → def func(self, param: Any) -> None:
        pattern = r'(\s+def\s+\w+\([^)]*\w+)(\)):\s*$'
        def add_any_type(match: re.Match[str]) -> str:
            params = match.group(1)
            # 如果参数没有类型注解，添加 Any
            if ':' not in params.split(',')[-1]:
                # 获取最后一个参数
                parts = params.rsplit(',', 1)
                if len(parts) == 2:
                    return f"{parts[0]}, {parts[1].strip()}: Any) -> None:"
                else:
                    # 只有一个参数（除了 self/cls）
                    param_match = re.search(r'(self|cls),\s*(\w+)$', params)
                    if param_match:
                        return f"{param_match.group(1)}, {param_match.group(2)}: Any) -> None:"
            return match.group(0)
        
        # 3. 修复 __init__ 缺少返回类型
        pattern = r'(\s+def __init__\([^)]+\)):\s*$'
        content = re.sub(pattern, r'\1 -> None:', content, flags=re.MULTILINE)
        
        # 4. 修复 get_valid_name 等缺少类型的方法
        pattern = r'(\s+def\s+\w+\(self,\s*\w+)\)\s*:\s*$'
        content = re.sub(pattern, r'\1: Any) -> Any:', content, flags=re.MULTILINE)
        
        # 5. 添加必要的 Any 导入
        if 'Any' in content and 'from typing import' in content:
            # 检查是否已经导入 Any
            if not re.search(r'from typing import.*\bAny\b', content):
                # 找到第一个 from typing import 并添加 Any
                content = re.sub(
                    r'(from typing import)([^(\n]*?)(\n)',
                    lambda m: f"{m.group(1)}{m.group(2)}, Any{m.group(3)}" if 'Any' not in m.group(2) else m.group(0),
                    content,
                    count=1
                )
                changes.append("Added Any to typing imports")
        elif 'Any' in content and 'from typing import' not in content:
            # 需要添加完整的 typing 导入
            # 在第一个 import 之前添加
            import_match = re.search(r'^(import |from )', content, re.MULTILINE)
            if import_match:
                pos = import_match.start()
                content = content[:pos] + "from typing import Any\n\n" + content[pos:]
                changes.append("Added typing import")
        
        # 6. 移除未使用的 type: ignore 注释
        pattern = r'\s*#\s*type:\s*ignore\s*(?:\[[\w-]+\])?\s*$'
        content = re.sub(pattern, '', content, flags=re.MULTILINE)
        
        # 7. 修复 cast() 返回 Any 的问题
        # return cast(...) → return cast(SpecificType, ...)
        # 这个需要手动处理，脚本只能标记
        
        if content != original:
            file_path.write_text(content, encoding='utf-8')
            return (1, changes)
        return (0, [])
        
    except Exception as e:
        print(f"Error processing {file_path}: {e}", file=sys.stderr)
        return (0, [])

def main() -> None:
    """主函数"""
    backend_dir = Path(__file__).parent
    
    # 收集所有 api 和 schemas 文件
    api_files = list(backend_dir.glob("apps/*/api/**/*.py"))
    schema_files = list(backend_dir.glob("apps/*/schemas/**/*.py"))
    schema_files += list(backend_dir.glob("apps/*/schemas.py"))
    
    all_files = api_files + schema_files
    
    print(f"Found {len(all_files)} files to process")
    
    fixed_count = 0
    for file_path in all_files:
        if file_path.name == "__init__.py":
            continue
        
        count, changes = fix_file(file_path)
        if count > 0:
            fixed_count += 1
            print(f"✓ {file_path.relative_to(backend_dir)}")
            for change in changes:
                print(f"  - {change}")
    
    print(f"\nFixed {fixed_count} files")

if __name__ == "__main__":
    main()
