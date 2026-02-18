"""修复var-annotated错误 - 添加变量类型注解"""

import re
import subprocess
from pathlib import Path

backend_path = Path(__file__).parent.parent


def get_var_annotated_errors():
    """获取所有var-annotated错误"""
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
        match = re.match(r'(apps/[^:]+):(\d+):(\d+):', line)
        if match and 'Need type annotation' in line:
            # 检查是否是 var-annotated 错误
            for j in range(i, min(i + 3, len(lines))):
                if '[var-annotated]' in lines[j]:
                    file_path = match.group(1)
                    line_num = int(match.group(2))
                    
                    # 提取变量名和提示
                    var_match = re.search(r'for "([^"]+)"', line)
                    hint_match = re.search(r'\(hint: "([^"]+)"\)', line)
                    
                    if var_match:
                        var_name = var_match.group(1)
                        hint = hint_match.group(1) if hint_match else None
                        errors.append((file_path, line_num, var_name, hint))
                    break
    
    return errors


def fix_var_annotation(file_path: str, line_num: int, var_name: str, hint: str | None) -> bool:
    """修复单个var-annotated错误"""
    try:
        full_path = backend_path / file_path
        lines = full_path.read_text(encoding="utf-8").split('\n')
        
        if line_num < 1 or line_num > len(lines):
            return False
        
        target_line = lines[line_num - 1]
        original_line = target_line
        
        # 根据hint推断类型
        if hint:
            if 'Dict[<type>, <type>]' in hint:
                type_annotation = 'dict[str, Any]'
            elif 'List[<type>]' in hint:
                type_annotation = 'list[Any]'
            elif 'Set[<type>]' in hint:
                type_annotation = 'set[Any]'
            else:
                # 尝试从hint中提取类型
                type_match = re.search(r': ([^=]+) =', hint)
                if type_match:
                    type_annotation = type_match.group(1).strip()
                else:
                    return False
        else:
            # 没有hint，尝试从代码推断
            if '= {}' in target_line:
                type_annotation = 'dict[str, Any]'
            elif '= []' in target_line:
                type_annotation = 'list[Any]'
            elif '= set()' in target_line:
                type_annotation = 'set[Any]'
            else:
                return False
        
        # 修复：var_name = value -> var_name: type = value
        # 匹配模式：变量名 = 值
        pattern = rf'(\s*)({re.escape(var_name)})\s*=\s*'
        
        def replace_func(match):
            indent = match.group(1)
            name = match.group(2)
            return f'{indent}{name}: {type_annotation} = '
        
        modified = re.sub(pattern, replace_func, target_line, count=1)
        
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
    print("修复var-annotated错误（变量类型注解）")
    print("=" * 80)
    
    errors = get_var_annotated_errors()
    print(f"\n找到 {len(errors)} 个var-annotated错误\n")
    
    fixed = 0
    for file_path, line_num, var_name, hint in errors:
        if fix_var_annotation(file_path, line_num, var_name, hint):
            fixed += 1
    
    print(f"\n✅ 完成: 修复了 {fixed} 个错误")
    
    # 验证
    remaining = get_var_annotated_errors()
    print(f"剩余var-annotated错误: {len(remaining)}")
    
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
