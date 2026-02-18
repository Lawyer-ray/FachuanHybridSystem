"""批量修复 type-arg 错误"""

import re
import subprocess
from pathlib import Path
from typing import List, Tuple

backend_path = Path(__file__).parent.parent


def get_type_arg_errors() -> List[Tuple[str, int, str, str]]:
    """获取所有 type-arg 错误，返回 (文件路径, 行号, 泛型类型, 完整行内容)"""
    result = subprocess.run(
        ["mypy", "--strict", "apps/"],
        cwd=backend_path,
        capture_output=True,
        text=True
    )
    output = result.stdout + result.stderr
    
    errors = []
    lines = output.split('\n')
    
    i = 0
    while i < len(lines):
        line = lines[i]
        # 匹配错误行
        match = re.match(r'(apps/[^:]+):(\d+):', line)
        if match and '[type-arg]' in line:
            file_path = match.group(1)
            line_num = int(match.group(2))
            
            # 提取泛型类型
            type_match = re.search(r'generic type "(\w+)"', line)
            if type_match:
                generic_type = type_match.group(1)
                
                # 获取下一行（代码行）
                if i + 1 < len(lines):
                    code_line = lines[i + 1].strip()
                    errors.append((file_path, line_num, generic_type, code_line))
        i += 1
    
    return errors


def fix_deque_type(line: str) -> str:
    """修复 deque 类型"""
    # deque -> deque[Any]
    return re.sub(r'\bdeque\b(?!\[)', 'deque[Any]', line)


def fix_callable_type(line: str) -> str:
    """修复 Callable 类型"""
    # Callable -> Callable[..., Any]
    return re.sub(r'\bCallable\b(?!\[)', 'Callable[..., Any]', line)


def fix_dict_type(line: str) -> str:
    """修复 dict 类型"""
    # dict -> dict[str, Any]
    return re.sub(r'\bdict\b(?!\[)', 'dict[str, Any]', line)


def fix_list_type(line: str) -> str:
    """修复 list 类型"""
    # list -> list[Any]
    return re.sub(r'\blist\b(?!\[)', 'list[Any]', line)


def fix_set_type(line: str) -> str:
    """修复 set 类型"""
    # set -> set[Any]
    return re.sub(r'\bset\b(?!\[)', 'set[Any]', line)


def fix_ndarray_type(line: str) -> str:
    """修复 ndarray 类型"""
    # ndarray -> ndarray[Any, Any]
    return re.sub(r'\bndarray\b(?!\[)', 'ndarray[Any, Any]', line)


def fix_type_arg_in_file(file_path: str, line_num: int, generic_type: str) -> bool:
    """修复文件中的 type-arg 错误"""
    try:
        full_path = backend_path / file_path
        lines = full_path.read_text(encoding="utf-8").split('\n')
        
        if line_num < 1 or line_num > len(lines):
            return False
        
        original_line = lines[line_num - 1]
        
        # 根据泛型类型选择修复函数
        fix_funcs = {
            'deque': fix_deque_type,
            'Callable': fix_callable_type,
            'dict': fix_dict_type,
            'list': fix_list_type,
            'set': fix_set_type,
            'ndarray': fix_ndarray_type,
        }
        
        fix_func = fix_funcs.get(generic_type)
        if not fix_func:
            return False
        
        modified_line = fix_func(original_line)
        
        if modified_line != original_line:
            lines[line_num - 1] = modified_line
            full_path.write_text('\n'.join(lines), encoding="utf-8")
            print(f"✓ {file_path}:{line_num}")
            print(f"  原: {original_line.strip()}")
            print(f"  新: {modified_line.strip()}")
            return True
        
        return False
        
    except Exception as e:
        print(f"✗ 修复失败 {file_path}:{line_num}: {e}")
        return False


def main():
    print("=" * 80)
    print("批量修复 type-arg 错误")
    print("=" * 80)
    
    errors = get_type_arg_errors()
    print(f"\n找到 {len(errors)} 个 type-arg 错误\n")
    
    # 统计各类型数量
    type_counts = {}
    for _, _, generic_type, _ in errors:
        type_counts[generic_type] = type_counts.get(generic_type, 0) + 1
    
    print("错误分布:")
    for gtype, count in sorted(type_counts.items(), key=lambda x: -x[1]):
        print(f"  {gtype}: {count}")
    print()
    
    # 修复所有错误
    fixed = 0
    for file_path, line_num, generic_type, code_line in errors:
        if fix_type_arg_in_file(file_path, line_num, generic_type):
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
