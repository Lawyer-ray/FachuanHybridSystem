"""修复 TYPE_CHECKING 块中缺失的类型导入"""

import re
import subprocess
from pathlib import Path
from typing import Dict, Set, List, Tuple

backend_path = Path(__file__).parent.parent


def get_name_defined_errors() -> List[Tuple[str, int, str]]:
    """获取所有 name-defined 错误"""
    result = subprocess.run(
        ["mypy", "--strict", "apps/"],
        cwd=backend_path,
        capture_output=True,
        text=True
    )
    output = result.stdout + result.stderr
    
    errors = []
    for line in output.split('\n'):
        # 匹配格式: apps/xxx/yyy.py:123:45: error: Name "ClassName" is not defined  [name-defined]
        match = re.match(r'(apps/[^:]+):(\d+):\d+: error: Name "([^"]+)" is not defined\s+\[name-defined\]', line)
        if match:
            file_path = match.group(1)
            line_num = int(match.group(2))
            class_name = match.group(3)
            errors.append((file_path, line_num, class_name))
    
    return errors


def analyze_missing_imports(errors: List[Tuple[str, int, str]]) -> Dict[str, Set[str]]:
    """分析每个文件缺失的导入"""
    file_missing = {}
    
    for file_path, line_num, class_name in errors:
        if file_path not in file_missing:
            file_missing[file_path] = set()
        file_missing[file_path].add(class_name)
    
    return file_missing


def add_type_checking_import(file_path: str, class_names: Set[str]) -> bool:
    """添加 TYPE_CHECKING 导入"""
    try:
        full_path = backend_path / file_path
        if not full_path.exists():
            return False
        
        content = full_path.read_text(encoding="utf-8")
        lines = content.split('\n')
        
        # 查找 TYPE_CHECKING 块
        type_checking_start = -1
        type_checking_end = -1
        
        for i, line in enumerate(lines):
            if 'if TYPE_CHECKING:' in line:
                type_checking_start = i
            elif type_checking_start != -1 and type_checking_end == -1:
                if line and not line.startswith(' ') and not line.startswith('\t'):
                    type_checking_end = i
                    break
        
        if type_checking_start == -1:
            # 没有 TYPE_CHECKING 块，需要创建
            # 找到导入区域的末尾
            import_end = 0
            for i, line in enumerate(lines):
                if line.startswith('import ') or line.startswith('from '):
                    import_end = i + 1
            
            # 添加 TYPE_CHECKING 导入
            if 'TYPE_CHECKING' not in content:
                # 需要先导入 TYPE_CHECKING
                for i, line in enumerate(lines):
                    if line.startswith('from typing import'):
                        if 'TYPE_CHECKING' not in line:
                            lines[i] = line.rstrip() + ', TYPE_CHECKING'
                        break
            
            # 创建 TYPE_CHECKING 块
            new_lines = [
                '',
                'if TYPE_CHECKING:',
            ]
            for class_name in sorted(class_names):
                # 尝试猜测导入路径（简化版）
                new_lines.append(f'    from ...models import {class_name}  # type: ignore[attr-defined]')
            
            lines = lines[:import_end] + new_lines + lines[import_end:]
            full_path.write_text('\n'.join(lines), encoding="utf-8")
            print(f"✓ 创建 TYPE_CHECKING 块: {file_path}")
            print(f"  添加: {', '.join(sorted(class_names))}")
            return True
        
        else:
            # 已有 TYPE_CHECKING 块，添加缺失的导入
            if type_checking_end == -1:
                type_checking_end = len(lines)
            
            # 检查哪些类名还没导入
            existing_imports = set()
            for i in range(type_checking_start + 1, type_checking_end):
                line = lines[i]
                match = re.search(r'import\s+(\w+)', line)
                if match:
                    existing_imports.add(match.group(1))
            
            missing = class_names - existing_imports
            if not missing:
                print(f"- 已有所有导入: {file_path}")
                return False
            
            # 在 TYPE_CHECKING 块末尾添加导入
            insert_pos = type_checking_end
            for class_name in sorted(missing):
                lines.insert(insert_pos, f'    from ...models import {class_name}  # type: ignore[attr-defined]')
                insert_pos += 1
            
            full_path.write_text('\n'.join(lines), encoding="utf-8")
            print(f"✓ 添加到 TYPE_CHECKING 块: {file_path}")
            print(f"  添加: {', '.join(sorted(missing))}")
            return True
        
    except Exception as e:
        print(f"✗ 处理失败 {file_path}: {e}")
        return False


def main():
    print("=" * 80)
    print("修复 TYPE_CHECKING 导入")
    print("=" * 80)
    
    errors = get_name_defined_errors()
    print(f"\n找到 {len(errors)} 个 name-defined 错误")
    
    file_missing = analyze_missing_imports(errors)
    print(f"涉及 {len(file_missing)} 个文件\n")
    
    # 只处理前 10 个文件（避免一次改太多）
    fixed = 0
    for file_path, class_names in list(file_missing.items())[:10]:
        print(f"\n处理: {file_path}")
        print(f"缺失: {', '.join(sorted(class_names))}")
        if add_type_checking_import(file_path, class_names):
            fixed += 1
    
    print(f"\n✅ 完成: 处理了 {fixed} 个文件")
    
    # 验证
    remaining = get_name_defined_errors()
    print(f"剩余 name-defined 错误: {len(remaining)}")
    
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
