"""正确修复type-arg错误 - 添加合适的类型参数"""

import re
import subprocess
from pathlib import Path

backend_path = Path(__file__).parent.parent


def get_type_arg_errors():
    """获取所有type-arg错误"""
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
        match = re.match(r'([^:]+):(\d+):\d+: error:', line)
        if match and i + 1 < len(lines) and '[type-arg]' in lines[i + 1]:
            file_path = match.group(1)
            line_num = int(match.group(2))
            error_msg = lines[i + 1]
            errors.append((file_path, line_num, error_msg))
    
    return errors


def fix_type_arg(file_path: str, line_num: int) -> bool:
    """修复单个type-arg错误"""
    try:
        full_path = backend_path / file_path
        lines = full_path.read_text(encoding="utf-8").split('\n')
        
        if line_num < 1 or line_num > len(lines):
            return False
        
        target_line = lines[line_num - 1]
        original_line = target_line
        
        # 修复常见模式
        # -> dict 改为 -> dict[str, Any]
        target_line = re.sub(r'-> dict\b', '-> dict[str, Any]', target_line)
        # -> Dict 改为 -> Dict[str, Any]
        target_line = re.sub(r'-> Dict\b', '-> Dict[str, Any]', target_line)
        # -> list 改为 -> list[Any]
        target_line = re.sub(r'-> list\b', '-> list[Any]', target_line)
        # -> List 改为 -> List[Any]
        target_line = re.sub(r'-> List\b', '-> List[Any]', target_line)
        
        # : dict = 改为 : dict[str, Any] =
        target_line = re.sub(r': dict\s*=', ': dict[str, Any] =', target_line)
        # : Dict = 改为 : Dict[str, Any] =
        target_line = re.sub(r': Dict\s*=', ': Dict[str, Any] =', target_line)
        # : list = 改为 : list[Any] =
        target_line = re.sub(r': list\s*=', ': list[Any] =', target_line)
        # : List = 改为 : List[Any] =
        target_line = re.sub(r': List\s*=', ': List[Any] =', target_line)
        
        if target_line != original_line:
            lines[line_num - 1] = target_line
            full_path.write_text('\n'.join(lines), encoding="utf-8")
            print(f"✓ 修复 {file_path}:{line_num}")
            return True
        
        return False
        
    except Exception as e:
        print(f"✗ 修复失败 {file_path}:{line_num}: {e}")
        return False


def main():
    print("=" * 80)
    print("正确修复type-arg错误")
    print("=" * 80)
    
    errors = get_type_arg_errors()
    print(f"\n找到 {len(errors)} 个type-arg错误\n")
    
    fixed = 0
    for file_path, line_num, error_msg in errors:
        if fix_type_arg(file_path, line_num):
            fixed += 1
    
    print(f"\n✅ 完成: 修复了 {fixed} 个type-arg错误")
    
    # 验证
    remaining = get_type_arg_errors()
    print(f"剩余type-arg错误: {len(remaining)}")


if __name__ == "__main__":
    main()
