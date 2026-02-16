#!/usr/bin/env python3
"""
专门修复 Incompatible default 错误
模式: param: Type = None -> param: Type | None = None
"""

from pathlib import Path
import re
import subprocess

def run_mypy():
    """运行 mypy 获取错误"""
    result = subprocess.run(
        ["python", "-m", "mypy", "--config-file", "mypy.ini", "apps/"],
        capture_output=True,
        text=True
    )
    return result.stdout

def get_incompatible_default_errors(output):
    """提取所有 Incompatible default 错误"""
    errors = {}
    for line in output.split('\n'):
        if 'Incompatible default' in line:
            match = re.match(r'(.+?):(\d+):(\d+):', line)
            if match:
                file_path = match.group(1)
                line_no = int(match.group(2))
                if file_path not in errors:
                    errors[file_path] = []
                errors[file_path].append(line_no)
    return errors

def fix_file(file_path: Path, line_numbers: list) -> bool:
    """修复文件中的 Incompatible default 错误"""
    try:
        content = file_path.read_text()
        lines = content.split('\n')
        modified = False
        
        for line_no in line_numbers:
            idx = line_no - 1
            if idx < 0 or idx >= len(lines):
                continue
            
            line = lines[idx]
            original = line
            
            # 模式1: param: dict = None -> param: dict | None = None
            line = re.sub(r'(\w+):\s*dict\s*=\s*None', r'\1: dict | None = None', line)
            
            # 模式2: param: list = None -> param: list | None = None
            line = re.sub(r'(\w+):\s*list\s*=\s*None', r'\1: list | None = None', line)
            
            # 模式3: param: set = None -> param: set | None = None
            line = re.sub(r'(\w+):\s*set\s*=\s*None', r'\1: set | None = None', line)
            
            # 模式4: param: Dict[str, Any] = None -> param: Dict[str, Any] | None = None
            line = re.sub(r'(\w+):\s*Dict\[([^\]]+)\]\s*=\s*None', r'\1: Dict[\2] | None = None', line)
            
            # 模式5: param: Type = None -> param: Type | None = None (通用)
            # 但要避免已经有 | None 的
            if ' = None' in line and '| None' not in line and '|None' not in line:
                # 匹配 param: SomeType = None
                line = re.sub(r'(\w+):\s*([A-Z]\w+)\s*=\s*None', r'\1: \2 | None = None', line)
            
            if line != original:
                lines[idx] = line
                modified = True
        
        if modified:
            file_path.write_text('\n'.join(lines))
            return True
    
    except Exception as e:
        print(f"❌ {file_path}: {e}")
    
    return False

def main():
    print("🔍 获取 Incompatible default 错误...")
    output = run_mypy()
    errors = get_incompatible_default_errors(output)
    
    print(f"📊 发现 {len(errors)} 个文件有 Incompatible default 错误")
    
    fixed = 0
    for file_path_str, line_numbers in errors.items():
        file_path = Path(file_path_str)
        if not file_path.exists():
            continue
        
        if fix_file(file_path, line_numbers):
            fixed += 1
            if fixed % 10 == 0:
                print(f"✅ 已修复 {fixed} 个文件...")
    
    print(f"\n✅ 修复了 {fixed} 个文件")
    
    # 重新检查
    print("\n🔍 重新检查...")
    output = run_mypy()
    for line in output.split('\n'):
        if 'Found' in line and 'error' in line:
            print(f"📊 {line}")
            break

if __name__ == "__main__":
    main()
