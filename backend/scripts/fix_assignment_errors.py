"""修复assignment错误 - Optional默认值问题"""

import re
import subprocess
from pathlib import Path

backend_path = Path(__file__).parent.parent


def get_assignment_errors():
    """获取所有assignment错误"""
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
        if match and i + 1 < len(lines) and '[assignment]' in lines[i + 1]:
            # 只处理"Incompatible default"和"None"相关的
            if 'Incompatible default' in line and 'None' in line:
                file_path = match.group(1)
                line_num = int(match.group(2))
                errors.append((file_path, line_num))
    
    return errors


def fix_assignment(file_path: str, line_num: int) -> bool:
    """修复单个assignment错误"""
    try:
        full_path = backend_path / file_path
        lines = full_path.read_text(encoding="utf-8").split('\n')
        
        if line_num < 1 or line_num > len(lines):
            return False
        
        target_line = lines[line_num - 1]
        original_line = target_line
        
        # 修复模式：arg: Type = None -> arg: Type | None = None
        # 支持多种类型：str, int, dict, Dict, list, List, Exception等
        
        # 模式1: arg: Type = None (简单类型)
        pattern1 = r'(\w+):\s*([A-Z][A-Za-z_]\w*(?:\[[^\]]+\])?)\s*=\s*None'
        replacement1 = r'\1: \2 | None = None'
        modified = re.sub(pattern1, replacement1, target_line)
        
        # 模式2: arg: type = None (小写类型)
        if modified == target_line:
            pattern2 = r'(\w+):\s*(str|int|float|bool|dict|list|set|tuple)\s*=\s*None'
            replacement2 = r'\1: \2 | None = None'
            modified = re.sub(pattern2, replacement2, target_line)
        
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
    print("修复assignment错误（Optional默认值）")
    print("=" * 80)
    
    errors = get_assignment_errors()
    print(f"\n找到 {len(errors)} 个assignment错误\n")
    
    fixed = 0
    for file_path, line_num in errors:
        if fix_assignment(file_path, line_num):
            fixed += 1
    
    print(f"\n✅ 完成: 修复了 {fixed} 个assignment错误")
    
    # 验证
    remaining = get_assignment_errors()
    print(f"剩余assignment错误: {len(remaining)}")
    
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
