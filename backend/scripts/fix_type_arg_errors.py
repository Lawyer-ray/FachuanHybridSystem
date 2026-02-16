"""修复 type-arg 错误 - 添加泛型类型参数"""

import re
import subprocess
from pathlib import Path
from typing import List, Tuple

backend_path = Path(__file__).parent.parent


def get_type_arg_errors() -> List[Tuple[str, int, str]]:
    """获取所有 type-arg 错误"""
    result = subprocess.run(
        ["mypy", "--strict", "apps/"],
        cwd=backend_path,
        capture_output=True,
        text=True
    )
    output = result.stdout + result.stderr
    
    errors = []
    lines = output.split('\n')
    
    for i, line in enumerate(lines):
        # 匹配完整的错误行
        if '[type-arg]' in line:
            match = re.match(r'(apps/[^:]+):(\d+):', line)
            if match:
                file_path = match.group(1)
                line_num = int(match.group(2))
                
                # 提取泛型类型名 - 查找下一行
                if i + 1 < len(lines):
                    next_line = lines[i + 1]
                    type_match = re.search(r'generic type "(\w+)"', line + ' ' + next_line)
                    if type_match:
                        generic_type = type_match.group(1)
                        errors.append((file_path, line_num, generic_type))
    
    return errors


def fix_type_arg(file_path: str, line_num: int, generic_type: str) -> bool:
    """修复单个 type-arg 错误"""
    try:
        full_path = backend_path / file_path
        lines = full_path.read_text(encoding="utf-8").split('\n')
        
        if line_num < 1 or line_num > len(lines):
            return False
        
        target_line = lines[line_num - 1]
        original_line = target_line
        
        # 根据泛型类型添加类型参数
        if generic_type == 'deque':
            # deque -> deque[Any]
            modified = re.sub(r'\bdeque\b(?!\[)', 'deque[Any]', target_line)
        elif generic_type == 'Callable':
            # Callable -> Callable[..., Any]
            modified = re.sub(r'\bCallable\b(?!\[)', 'Callable[..., Any]', target_line)
        elif generic_type == 'dict':
            # dict -> dict[str, Any]
            modified = re.sub(r'\bdict\b(?!\[)', 'dict[str, Any]', target_line)
        elif generic_type == 'list':
            # list -> list[Any]
            modified = re.sub(r'\blist\b(?!\[)', 'list[Any]', target_line)
        elif generic_type == 'set':
            # set -> set[Any]
            modified = re.sub(r'\bset\b(?!\[)', 'set[Any]', target_line)
        elif generic_type == 'ndarray':
            # ndarray -> ndarray[Any, Any]
            modified = re.sub(r'\bndarray\b(?!\[)', 'ndarray[Any, Any]', target_line)
        else:
            return False
        
        if modified != original_line:
            lines[line_num - 1] = modified
            full_path.write_text('\n'.join(lines), encoding="utf-8")
            print(f"✓ 修复 {file_path}:{line_num}")
            print(f"  原: {original_line.strip()}")
            print(f"  新: {modified.strip()}")
            return True
        
        return False
        
    except Exception as e:
        print(f"✗ 修复失败 {file_path}:{line_num}: {e}")
        return False


def main():
    print("=" * 80)
    print("修复 type-arg 错误（泛型类型参数）")
    print("=" * 80)
    
    errors = get_type_arg_errors()
    print(f"\n找到 {len(errors)} 个 type-arg 错误\n")
    
    # 统计各类型的数量
    type_counts = {}
    for _, _, generic_type in errors:
        type_counts[generic_type] = type_counts.get(generic_type, 0) + 1
    
    print("错误分布:")
    for gtype, count in sorted(type_counts.items(), key=lambda x: -x[1]):
        print(f"  {gtype}: {count}")
    print()
    
    # 只修复前 50 个（避免一次改太多）
    fixed = 0
    for file_path, line_num, generic_type in errors[:50]:
        if fix_type_arg(file_path, line_num, generic_type):
            fixed += 1
    
    print(f"\n✅ 完成: 修复了 {fixed} 个错误")
    
    # 验证
    remaining = get_type_arg_errors()
    print(f"剩余 type-arg 错误: {len(remaining)}")
    
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
