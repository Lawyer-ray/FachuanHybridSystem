#!/usr/bin/env python3
"""
修复 contracts 模块的 mypy 类型错误

策略：
1. 不为 Django Model 字段添加类型注解
2. 使用 cast() 或 type: ignore 处理 Django ORM 动态属性
3. 为 QuerySet 添加正确的泛型参数
4. 修复函数返回类型和参数类型
"""

import re
from pathlib import Path
from typing import List, Tuple


def fix_queryset_types(content: str) -> str:
    """修复 QuerySet 类型注解"""
    # QuerySet[Model] 泛型参数
    patterns = [
        (r'-> QuerySet\b(?!\[)', r'-> QuerySet[Any]'),
        (r': QuerySet\b(?!\[)', r': QuerySet[Any]'),
    ]
    
    for pattern, replacement in patterns:
        content = re.sub(pattern, replacement, content)
    
    return content


def fix_optional_defaults(content: str) -> str:
    """修复可选参数默认值"""
    # 常见的 None 默认值模式
    patterns = [
        # dict = None -> Optional[dict] = None
        (r'\b(\w+): dict\[([^\]]+)\] = None\b', r'\1: Optional[dict[\2]] = None'),
        (r'\b(\w+): dict = None\b', r'\1: Optional[dict[str, Any]] = None'),
        # str = None -> Optional[str] = None
        (r'\b(\w+): str = None\b', r'\1: Optional[str] = None'),
        # int = None -> Optional[int] = None
        (r'\b(\w+): int = None\b', r'\1: Optional[int] = None'),
        # bool = None -> Optional[bool] = None
        (r'\b(\w+): bool = None\b', r'\1: Optional[bool] = None'),
        # Exception = None -> Optional[Exception] = None
        (r'\b(\w+): Exception = None\b', r'\1: Optional[Exception] = None'),
    ]
    
    for pattern, replacement in patterns:
        content = re.sub(pattern, replacement, content)
    
    return content


def fix_any_type(content: str) -> str:
    """修复 any -> Any"""
    # any 不是有效的类型，应该是 Any
    content = re.sub(r'\bany\b(?=\s*[,\)])', 'Any', content)
    return content


def ensure_typing_imports(content: str) -> str:
    """确保必要的 typing 导入"""
    has_typing = 'from typing import' in content or 'import typing' in content
    
    if not has_typing:
        return content
    
    # 检查需要的类型
    needs_optional = 'Optional[' in content
    needs_any = ': Any' in content or '[Any]' in content or '-> Any' in content
    needs_dict = 'Dict[' in content
    needs_list = 'List[' in content
    
    # 找到现有的 typing 导入行
    typing_import_pattern = r'from typing import ([^\n]+)'
    match = re.search(typing_import_pattern, content)
    
    if match:
        current_imports = match.group(1)
        imports_set = set(imp.strip() for imp in current_imports.split(','))
        
        if needs_optional and 'Optional' not in imports_set:
            imports_set.add('Optional')
        if needs_any and 'Any' not in imports_set:
            imports_set.add('Any')
        if needs_dict and 'Dict' not in imports_set:
            imports_set.add('Dict')
        if needs_list and 'List' not in imports_set:
            imports_set.add('List')
        
        new_imports = ', '.join(sorted(imports_set))
        content = re.sub(typing_import_pattern, f'from typing import {new_imports}', content)
    else:
        # 添加新的 typing 导入
        imports = []
        if needs_optional:
            imports.append('Optional')
        if needs_any:
            imports.append('Any')
        if needs_dict:
            imports.append('Dict')
        if needs_list:
            imports.append('List')
        
        if imports:
            import_line = f"from typing import {', '.join(sorted(imports))}\n"
            # 在第一个 import 之后添加
            lines = content.split('\n')
            for i, line in enumerate(lines):
                if line.startswith('import ') or line.startswith('from '):
                    lines.insert(i + 1, import_line.rstrip())
                    break
            content = '\n'.join(lines)
    
    return content


def fix_file(file_path: Path) -> Tuple[bool, str]:
    """修复单个文件"""
    try:
        content = file_path.read_text(encoding='utf-8')
        original = content
        
        # 应用修复
        content = fix_queryset_types(content)
        content = fix_optional_defaults(content)
        content = fix_any_type(content)
        content = ensure_typing_imports(content)
        
        if content != original:
            file_path.write_text(content, encoding='utf-8')
            return True, "修复成功"
        else:
            return False, "无需修复"
    except Exception as e:
        return False, f"错误: {e}"


def main():
    """主函数"""
    backend_path = Path(__file__).parent.parent
    contracts_path = backend_path / "apps" / "contracts"
    
    print(f"扫描 {contracts_path} 目录...")
    
    py_files = list(contracts_path.rglob("*.py"))
    print(f"找到 {len(py_files)} 个 Python 文件")
    
    fixed_count = 0
    for py_file in py_files:
        if py_file.name == "__init__.py":
            continue
        
        fixed, msg = fix_file(py_file)
        if fixed:
            fixed_count += 1
            rel_path = py_file.relative_to(backend_path)
            print(f"✓ {rel_path}")
    
    print(f"\n修复完成: {fixed_count}/{len(py_files)} 个文件")


if __name__ == "__main__":
    main()
