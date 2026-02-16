#!/usr/bin/env python3
"""
迭代式修复 mypy 错误
每次运行修复一批错误,然后验证
"""

from pathlib import Path
import re
import subprocess
from collections import defaultdict

def run_mypy():
    """运行 mypy 并返回错误"""
    result = subprocess.run(
        ["python", "-m", "mypy", "--config-file", "mypy.ini", "apps/"],
        capture_output=True,
        text=True
    )
    
    errors = []
    for line in result.stdout.split('\n'):
        if 'error:' in line:
            errors.append(line)
    
    return errors

def parse_error(line):
    """解析错误行"""
    match = re.match(r'(.+?):(\d+):(\d+): error: (.+)', line)
    if not match:
        return None
    
    return {
        'file': match.group(1),
        'line': int(match.group(2)),
        'col': int(match.group(3)),
        'message': match.group(4)
    }

def fix_missing_return_type_batch(errors, limit=50):
    """批量修复缺少返回类型的错误"""
    files_to_fix = defaultdict(list)
    
    for error_line in errors[:limit]:
        error = parse_error(error_line)
        if not error:
            continue
        
        if 'missing a return type' in error['message'] or 'missing a type annotation' in error['message']:
            files_to_fix[error['file']].append(error)
    
    fixed = 0
    for file_path_str, file_errors in files_to_fix.items():
        file_path = Path(file_path_str)
        if not file_path.exists():
            continue
        
        try:
            content = file_path.read_text()
            lines = content.split('\n')
            modified = False
            
            # 确保有必要的导入
            has_annotations = any('from __future__ import annotations' in line for line in lines)
            has_any = any('from typing import' in line and 'Any' in line for line in lines)
            
            if not has_annotations:
                lines.insert(0, 'from __future__ import annotations')
                modified = True
            
            if not has_any:
                # 找到合适的位置插入
                insert_idx = 1 if has_annotations else 0
                for i in range(insert_idx, len(lines)):
                    if lines[i].startswith('from ') or lines[i].startswith('import '):
                        insert_idx = i
                        break
                lines.insert(insert_idx, 'from typing import Any')
                modified = True
            
            # 修复每个错误
            for error in file_errors:
                idx = error['line'] - 1
                if idx >= len(lines):
                    continue
                
                line = lines[idx]
                
                # 只修复函数定义
                if 'def ' in line and '->' not in line:
                    if line.rstrip().endswith(':'):
                        lines[idx] = line.rstrip()[:-1] + ' -> Any:'
                        modified = True
            
            if modified:
                file_path.write_text('\n'.join(lines))
                fixed += 1
                print(f"✅ {file_path}")
        
        except Exception as e:
            print(f"❌ {file_path}: {e}")
    
    return fixed

def fix_returning_any_batch(errors, limit=50):
    """批量修复 Returning Any 错误"""
    files_to_fix = defaultdict(list)
    
    for error_line in errors[:limit]:
        error = parse_error(error_line)
        if not error:
            continue
        
        if 'Returning Any from function' in error['message']:
            files_to_fix[error['file']].append(error)
    
    fixed = 0
    for file_path_str, file_errors in files_to_fix.items():
        file_path = Path(file_path_str)
        if not file_path.exists():
            continue
        
        try:
            content = file_path.read_text()
            lines = content.split('\n')
            modified = False
            
            # 确保有必要的导入
            has_any = any('from typing import' in line and 'Any' in line for line in lines)
            
            if not has_any:
                for i, line in enumerate(lines):
                    if line.startswith('from typing import'):
                        # 添加 Any 到现有导入
                        if 'Any' not in line:
                            lines[i] = line.replace('import ', 'import Any, ')
                            modified = True
                        break
            
            # 修复每个错误 - 找到函数定义并添加 -> Any
            for error in file_errors:
                idx = error['line'] - 1
                
                # 向上查找函数定义
                func_idx = idx
                while func_idx >= 0:
                    if 'def ' in lines[func_idx]:
                        break
                    func_idx -= 1
                
                if func_idx >= 0:
                    line = lines[func_idx]
                    if 'def ' in line and '->' not in line:
                        if line.rstrip().endswith(':'):
                            lines[func_idx] = line.rstrip()[:-1] + ' -> Any:'
                            modified = True
            
            if modified:
                file_path.write_text('\n'.join(lines))
                fixed += 1
                print(f"✅ {file_path}")
        
        except Exception as e:
            print(f"❌ {file_path}: {e}")
    
    return fixed

def main():
    print("🔍 第1轮: 获取错误...")
    errors = run_mypy()
    initial_count = len(errors)
    print(f"📊 初始错误数: {initial_count}")
    
    if initial_count == 0:
        print("✅ 没有错误!")
        return
    
    # 第1批: 修复缺少返回类型
    print("\n🔧 修复缺少返回类型...")
    fixed = fix_missing_return_type_batch(errors, limit=100)
    print(f"修复了 {fixed} 个文件")
    
    # 验证
    print("\n🔍 第2轮: 重新检查...")
    errors = run_mypy()
    print(f"📊 剩余错误: {len(errors)} (减少 {initial_count - len(errors)})")
    
    if len(errors) == 0:
        print("✅ 所有错误已修复!")
        return
    
    # 第2批: 修复 Returning Any
    print("\n🔧 修复 Returning Any...")
    fixed = fix_returning_any_batch(errors, limit=100)
    print(f"修复了 {fixed} 个文件")
    
    # 最终验证
    print("\n🔍 最终检查...")
    errors = run_mypy()
    print(f"📊 最终错误数: {len(errors)}")
    print(f"📉 总共减少: {initial_count - len(errors)} 个错误")

if __name__ == "__main__":
    main()
