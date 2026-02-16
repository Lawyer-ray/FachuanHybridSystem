#!/usr/bin/env python3
"""
快速修复 automation 模块的简单类型错误
- 修复泛型类型参数缺失（dict → dict[str, Any], list → list[Any]）
- 修复变量类型注解缺失
- 修复无效类型名称（any → Any）
"""
from __future__ import annotations

import re
from pathlib import Path
from typing import Any


def fix_generic_types(content: str) -> tuple[str, int]:
    """修复泛型类型参数缺失"""
    fixes = 0
    
    # dict = None → dict[str, Any] | None = None
    pattern1 = r'(\w+):\s*dict\s*=\s*None'
    def repl1(m):
        nonlocal fixes
        fixes += 1
        return f'{m.group(1)}: dict[str, Any] | None = None'
    content = re.sub(pattern1, repl1, content)
    
    # list = None → list[Any] | None = None
    pattern2 = r'(\w+):\s*list\s*=\s*None'
    def repl2(m):
        nonlocal fixes
        fixes += 1
        return f'{m.group(1)}: list[Any] | None = None'
    content = re.sub(pattern2, repl2, content)
    
    # -> dict: → -> dict[str, Any]:
    pattern3 = r'->\s*dict\s*:'
    def repl3(m):
        nonlocal fixes
        fixes += 1
        return '-> dict[str, Any]:'
    content = re.sub(pattern3, repl3, content)
    
    # -> list: → -> list[Any]:
    pattern4 = r'->\s*list\s*:'
    def repl4(m):
        nonlocal fixes
        fixes += 1
        return '-> list[Any]:'
    content = re.sub(pattern4, repl4, content)
    
    # param: dict) → param: dict[str, Any])
    pattern5 = r'(\w+):\s*dict\s*\)'
    def repl5(m):
        nonlocal fixes
        fixes += 1
        return f'{m.group(1)}: dict[str, Any])'
    content = re.sub(pattern5, repl5, content)
    
    # param: list) → param: list[Any])
    pattern6 = r'(\w+):\s*list\s*\)'
    def repl6(m):
        nonlocal fixes
        fixes += 1
        return f'{m.group(1)}: list[Any])'
    content = re.sub(pattern6, repl6, content)
    
    # param: dict, → param: dict[str, Any],
    pattern7 = r'(\w+):\s*dict\s*,'
    def repl7(m):
        nonlocal fixes
        fixes += 1
        return f'{m.group(1)}: dict[str, Any],'
    content = re.sub(pattern7, repl7, content)
    
    # param: list, → param: list[Any],
    pattern8 = r'(\w+):\s*list\s*,'
    def repl8(m):
        nonlocal fixes
        fixes += 1
        return f'{m.group(1)}: list[Any],'
    content = re.sub(pattern8, repl8, content)
    
    return content, fixes


def fix_invalid_type_names(content: str) -> tuple[str, int]:
    """修复无效类型名称（any → Any）"""
    fixes = 0
    
    # : any → : Any
    pattern1 = r':\s*any\b'
    if re.search(pattern1, content):
        content = re.sub(pattern1, ': Any', content)
        fixes += len(re.findall(pattern1, content))
    
    return content, fixes


def fix_optional_defaults(content: str) -> tuple[str, int]:
    """修复可选参数默认值（= None 但类型不是 Optional）"""
    fixes = 0
    
    # config: dict = None → config: dict[str, Any] | None = None
    pattern1 = r'(\w+):\s*dict\s*=\s*None'
    def repl1(m):
        nonlocal fixes
        fixes += 1
        return f'{m.group(1)}: dict[str, Any] | None = None'
    content = re.sub(pattern1, repl1, content)
    
    # param: str = None → param: str | None = None
    pattern2 = r'(\w+):\s*str\s*=\s*None'
    def repl2(m):
        nonlocal fixes
        fixes += 1
        return f'{m.group(1)}: str | None = None'
    content = re.sub(pattern2, repl2, content)
    
    # param: int = None → param: int | None = None
    pattern3 = r'(\w+):\s*int\s*=\s*None'
    def repl3(m):
        nonlocal fixes
        fixes += 1
        return f'{m.group(1)}: int | None = None'
    content = re.sub(pattern3, repl3, content)
    
    # param: Exception = None → param: Exception | None = None
    pattern4 = r'(\w+):\s*Exception\s*=\s*None'
    def repl4(m):
        nonlocal fixes
        fixes += 1
        return f'{m.group(1)}: Exception | None = None'
    content = re.sub(pattern4, repl4, content)
    
    return content, fixes


def ensure_typing_imports(content: str, needs_any: bool = False) -> str:
    """确保必要的 typing 导入存在"""
    lines = content.split('\n')
    
    # 检查是否已有 from typing import
    has_typing_import = False
    typing_import_line = -1
    imports_any = False
    
    for i, line in enumerate(lines):
        if line.startswith('from typing import'):
            has_typing_import = True
            typing_import_line = i
            if 'Any' in line:
                imports_any = True
            break
    
    # 如果需要 Any 但没有导入
    if needs_any and not imports_any:
        if has_typing_import:
            # 在现有导入中添加 Any
            line = lines[typing_import_line]
            if 'Any' not in line:
                # 简单追加
                line = line.rstrip()
                if line.endswith(')'):
                    line = line[:-1] + ', Any)'
                else:
                    line = line + ', Any'
                lines[typing_import_line] = line
        else:
            # 添加新的导入行
            # 找到合适的位置（在 from __future__ 之后，在其他导入之前）
            insert_pos = 0
            for i, line in enumerate(lines):
                if line.startswith('from __future__'):
                    insert_pos = i + 1
                    break
                elif line.startswith('import ') or line.startswith('from '):
                    insert_pos = i
                    break
            
            lines.insert(insert_pos, 'from typing import Any')
            if insert_pos > 0 and lines[insert_pos - 1].strip():
                lines.insert(insert_pos, '')
    
    return '\n'.join(lines)


def process_file(file_path: Path) -> dict[str, Any]:
    """处理单个文件"""
    try:
        content = file_path.read_text(encoding='utf-8')
        original_content = content
        total_fixes = 0
        
        # 应用修复
        content, n1 = fix_generic_types(content)
        total_fixes += n1
        
        content, n2 = fix_invalid_type_names(content)
        total_fixes += n2
        
        content, n3 = fix_optional_defaults(content)
        total_fixes += n3
        
        # 如果有修复，确保导入 Any
        if total_fixes > 0:
            needs_any = 'Any' in content and 'dict[str, Any]' in content or 'list[Any]' in content
            content = ensure_typing_imports(content, needs_any)
        
        # 只有内容变化时才写入
        if content != original_content:
            file_path.write_text(content, encoding='utf-8')
            return {
                'file': str(file_path),
                'fixes': total_fixes,
                'success': True
            }
        
        return {'file': str(file_path), 'fixes': 0, 'success': True}
        
    except Exception as e:
        return {
            'file': str(file_path),
            'fixes': 0,
            'success': False,
            'error': str(e)
        }


def main():
    """主函数"""
    backend_path = Path(__file__).parent.parent
    automation_path = backend_path / 'apps' / 'automation'
    
    print("开始批量修复 automation 模块的简单类型错误...")
    print(f"扫描目录: {automation_path}")
    
    # 收集所有 Python 文件
    py_files = list(automation_path.rglob('*.py'))
    print(f"找到 {len(py_files)} 个 Python 文件")
    
    # 处理文件
    results = []
    modified_files = []
    total_fixes = 0
    
    for py_file in py_files:
        result = process_file(py_file)
        results.append(result)
        
        if result['success'] and result['fixes'] > 0:
            modified_files.append(py_file)
            total_fixes += result['fixes']
            rel_path = py_file.relative_to(backend_path)
            print(f"  ✓ {rel_path}: {result['fixes']} 处修复")
    
    # 输出统计
    print(f"\n修复完成:")
    print(f"  - 修改文件数: {len(modified_files)}")
    print(f"  - 总修复数: {total_fixes}")
    
    # 输出失败的文件
    failed = [r for r in results if not r['success']]
    if failed:
        print(f"\n失败文件 ({len(failed)}):")
        for r in failed:
            print(f"  ✗ {r['file']}: {r.get('error', 'Unknown error')}")


if __name__ == '__main__':
    main()
