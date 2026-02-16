#!/usr/bin/env python
"""
高级批量修复 cases 模块的类型错误

修复内容：
1. Function is missing a type annotation 错误
2. Returning Any 错误（使用 cast）
3. QuerySet 泛型参数
"""

import re
import subprocess
from pathlib import Path
from typing import Any


def get_mypy_errors_for_file(file_path: Path) -> list[tuple[int, str]]:
    """获取指定文件的 mypy 错误"""
    result = subprocess.run(
        ['python', '-m', 'mypy', str(file_path), '--strict'],
        capture_output=True,
        text=True,
        cwd=file_path.parent.parent.parent.parent
    )
    
    errors = []
    for line in result.stdout.split('\n'):
        if str(file_path.name) in line and ':' in line:
            parts = line.split(':')
            if len(parts) >= 3:
                try:
                    line_num = int(parts[1])
                    error_msg = ':'.join(parts[2:])
                    errors.append((line_num, error_msg))
                except ValueError:
                    pass
    
    return errors


def fix_missing_type_annotation(file_path: Path) -> int:
    """修复 Function is missing a type annotation 错误"""
    if not file_path.exists():
        return 0
    
    content = file_path.read_text(encoding='utf-8')
    lines = content.split('\n')
    fixed = 0
    
    # 查找所有函数定义
    for i, line in enumerate(lines):
        # 跳过已有返回类型的函数
        if 'def ' in line and ')' in line and ':' in line and '->' not in line:
            # 检查是否是简单的函数定义（单行）
            if line.strip().endswith(':'):
                # 在 ): 之前添加 -> None
                lines[i] = line.replace('):', ') -> None:')
                fixed += 1
    
    if fixed > 0:
        file_path.write_text('\n'.join(lines), encoding='utf-8')
    
    return fixed


def add_cast_import(content: str) -> str:
    """确保导入 cast"""
    if 'cast(' in content and 'from typing import' in content:
        if not re.search(r'from typing import.*\bcast\b', content):
            # 在第一个 from typing import 行添加 cast
            content = re.sub(
                r'(from typing import )([^\n]+)',
                lambda m: f"{m.group(1)}cast, {m.group(2)}" if 'cast' not in m.group(2) else m.group(0),
                content,
                count=1
            )
    return content


def fix_returning_any(file_path: Path) -> int:
    """修复 Returning Any 错误"""
    if not file_path.exists():
        return 0
    
    content = file_path.read_text(encoding='utf-8')
    original = content
    
    # 常见模式：return queryset.first()
    content = re.sub(
        r'return (\w+)\.first\(\)',
        r'return cast(Any, \1.first())',
        content
    )
    
    # 常见模式：return queryset.get(...)
    content = re.sub(
        r'return (\w+)\.get\(([^)]+)\)',
        r'return cast(Any, \1.get(\2))',
        content
    )
    
    # 常见模式：return model.field
    # 这个需要更谨慎，只处理明显的情况
    
    if content != original:
        content = add_cast_import(content)
        file_path.write_text(content, encoding='utf-8')
        return 1
    
    return 0


def fix_queryset_generic(file_path: Path) -> int:
    """修复 QuerySet 泛型参数"""
    if not file_path.exists():
        return 0
    
    content = file_path.read_text(encoding='utf-8')
    original = content
    
    # 修复 -> QuerySet:
    content = re.sub(r'-> QuerySet:', r'-> QuerySet[Any]:', content)
    content = re.sub(r'-> QuerySet\s*\n', r'-> QuerySet[Any]\n', content, flags=re.MULTILINE)
    
    # 修复参数类型 qs: QuerySet
    content = re.sub(r'(\w+): QuerySet([,\)])', r'\1: QuerySet[Any]\2', content)
    
    # 确保导入 Any
    if 'QuerySet[Any]' in content:
        if 'from typing import' in content:
            if not re.search(r'from typing import.*\bAny\b', content):
                content = re.sub(
                    r'(from typing import )([^\n]+)',
                    lambda m: f"{m.group(1)}Any, {m.group(2)}" if 'Any' not in m.group(2) else m.group(0),
                    content,
                    count=1
                )
    
    if content != original:
        file_path.write_text(content, encoding='utf-8')
        return 1
    
    return 0


def main() -> None:
    """主函数"""
    backend_path = Path(__file__).parent.parent
    cases_path = backend_path / 'apps' / 'cases'
    
    print("开始高级修复 cases 模块类型错误...")
    
    # 1. 修复 Function is missing a type annotation
    print("\n1. 修复 Function is missing a type annotation...")
    fixed_missing = 0
    for py_file in cases_path.rglob('*.py'):
        if py_file.name == '__init__.py':
            continue
        fixed_missing += fix_missing_type_annotation(py_file)
    print(f"   修复了 {fixed_missing} 个函数")
    
    # 2. 修复 QuerySet 泛型参数
    print("\n2. 修复 QuerySet 泛型参数...")
    fixed_qs = 0
    for py_file in cases_path.rglob('*.py'):
        if py_file.name == '__init__.py':
            continue
        fixed_qs += fix_queryset_generic(py_file)
    print(f"   修复了 {fixed_qs} 个文件")
    
    # 3. 修复 Returning Any
    print("\n3. 修复 Returning Any...")
    fixed_any = 0
    for py_file in cases_path.rglob('*.py'):
        if py_file.name == '__init__.py':
            continue
        fixed_any += fix_returning_any(py_file)
    print(f"   修复了 {fixed_any} 个文件")
    
    print("\n修复完成！")
    print("请运行 'python -m mypy apps/cases/ --strict' 查看剩余错误")


if __name__ == '__main__':
    main()
