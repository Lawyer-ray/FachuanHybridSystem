"""修复name-defined错误 - 添加缺失的导入"""

import re
import subprocess
from pathlib import Path
from collections import defaultdict

backend_path = Path(__file__).parent.parent


def get_name_defined_errors():
    """获取所有name-defined错误"""
    result = subprocess.run(
        ["mypy", "--strict", "apps/"],
        cwd=backend_path,
        capture_output=True,
        text=True
    )
    output = result.stdout + result.stderr
    
    errors = defaultdict(set)  # file_path -> set of missing names
    lines = output.split('\n')
    
    for i, line in enumerate(lines):
        match = re.match(r'(apps/[^:]+):(\d+):\d+:', line)
        if match:
            # 检查是否是 name-defined 错误
            is_name_defined = False
            
            # 检查当前行或后续几行是否有 [name-defined]
            for j in range(i, min(i + 3, len(lines))):
                if '[name-defined]' in lines[j]:
                    is_name_defined = True
                    break
            
            if is_name_defined and 'is not defined' in line:
                file_path = match.group(1)
                
                # 提取缺失的名称
                name_match = re.search(r'Name "([^"]+)" is not defined', line)
                if name_match:
                    missing_name = name_match.group(1)
                    errors[file_path].add(missing_name)
    
    return errors


def has_typing_import(file_path: Path) -> tuple[bool, int]:
    """检查文件是否已有typing导入，返回(是否存在, 插入位置)"""
    lines = file_path.read_text(encoding="utf-8").split('\n')
    
    import_line = -1
    last_import_line = -1
    
    for i, line in enumerate(lines):
        if line.startswith('from typing import'):
            import_line = i
            last_import_line = i
        elif line.startswith('import ') or line.startswith('from '):
            last_import_line = i
    
    return (import_line >= 0, import_line if import_line >= 0 else last_import_line + 1)


def add_missing_imports(file_path: str, missing_names: set[str]) -> bool:
    """添加缺失的导入"""
    try:
        full_path = backend_path / file_path
        lines = full_path.read_text(encoding="utf-8").split('\n')
        
        # 只处理typing相关的导入
        typing_names = {'Any', 'Optional', 'Dict', 'List', 'Set', 'Tuple', 'Union', 'Callable'}
        missing_typing = missing_names & typing_names
        
        if not missing_typing:
            return False
        
        has_import, insert_pos = has_typing_import(full_path)
        
        if has_import:
            # 已有typing导入，添加到现有导入
            import_line = lines[insert_pos]
            
            # 提取现有的导入
            match = re.match(r'from typing import (.+)', import_line)
            if match:
                existing = set(name.strip() for name in match.group(1).split(','))
                all_imports = existing | missing_typing
                
                # 重新组织导入
                sorted_imports = sorted(all_imports)
                lines[insert_pos] = f"from typing import {', '.join(sorted_imports)}"
        else:
            # 没有typing导入，添加新的
            sorted_imports = sorted(missing_typing)
            new_import = f"from typing import {', '.join(sorted_imports)}"
            lines.insert(insert_pos, new_import)
        
        full_path.write_text('\n'.join(lines), encoding="utf-8")
        print(f"✓ 修复 {file_path}")
        print(f"  添加: {', '.join(sorted(missing_typing))}")
        return True
        
    except Exception as e:
        print(f"✗ 修复失败 {file_path}: {e}")
        return False


def fix_logger_imports(file_path: str) -> bool:
    """修复logger导入"""
    try:
        full_path = backend_path / file_path
        lines = full_path.read_text(encoding="utf-8").split('\n')
        
        # 检查是否已有logger导入
        has_logger = any('import logging' in line or 'from logging import' in line for line in lines)
        
        if has_logger:
            return False
        
        # 查找导入位置
        insert_pos = 0
        for i, line in enumerate(lines):
            if line.startswith('import ') or line.startswith('from '):
                insert_pos = i + 1
        
        # 添加logger导入
        lines.insert(insert_pos, 'import logging')
        lines.insert(insert_pos + 1, '')
        lines.insert(insert_pos + 2, 'logger = logging.getLogger(__name__)')
        
        full_path.write_text('\n'.join(lines), encoding="utf-8")
        print(f"✓ 修复 {file_path} - 添加logger")
        return True
        
    except Exception as e:
        print(f"✗ 修复失败 {file_path}: {e}")
        return False


def main():
    print("=" * 80)
    print("修复name-defined错误（缺失导入）")
    print("=" * 80)
    
    errors = get_name_defined_errors()
    print(f"\n找到 {len(errors)} 个文件有name-defined错误\n")
    
    fixed = 0
    for file_path, missing_names in errors.items():
        print(f"\n处理: {file_path}")
        print(f"  缺失: {', '.join(sorted(missing_names))}")
        
        # 处理logger
        if 'logger' in missing_names:
            if fix_logger_imports(file_path):
                fixed += 1
                missing_names.remove('logger')
        
        # 处理typing导入
        if missing_names:
            if add_missing_imports(file_path, missing_names):
                fixed += 1
    
    print(f"\n✅ 完成: 修复了 {fixed} 个文件")
    
    # 验证
    remaining = get_name_defined_errors()
    print(f"剩余name-defined错误: {len(remaining)} 个文件")
    
    # 检查总错误数
    result = subprocess.run(
        ["mypy", "--strict", "apps/"],
        cwd=backend_path,
        capture_output=True,
        text=True
    )
    output = result.stdout + result.stderr
    for line in output.split('\n'):
        if 'Found' in line and 'errors' in line:
            print(f"\n{line}")
            break


if __name__ == "__main__":
    main()
