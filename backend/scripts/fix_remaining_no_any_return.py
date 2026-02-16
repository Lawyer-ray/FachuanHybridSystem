#!/usr/bin/env python3
"""批量修复剩余的no-any-return错误"""
import re
import subprocess
from pathlib import Path
from collections import defaultdict

def get_no_any_return_errors() -> list[dict[str, any]]:
    """获取所有no-any-return错误"""
    result = subprocess.run(
        ['mypy', 'apps/', '--strict', '--no-pretty'],
        capture_output=True,
        text=True,
        cwd='/Users/huangsong21/Downloads/Coding/AI/FachuanHybridSystem/backend'
    )
    
    errors = []
    for line in result.stdout.split('\n') + result.stderr.split('\n'):
        match = re.match(r'(.+?):(\d+):(\d+): error: (.+?) \[no-any-return\]', line)
        if match:
            errors.append({
                'file': match.group(1),
                'line': int(match.group(2)),
                'column': int(match.group(3)),
                'message': match.group(4).strip()
            })
    return errors

def main():
    errors = get_no_any_return_errors()
    print(f"找到 {len(errors)} 个no-any-return错误")
    
    # 按文件分组
    by_file = defaultdict(list)
    for err in errors:
        by_file[err['file']].append(err)
    
    print(f"\n涉及 {len(by_file)} 个文件")
    
    # 显示需要手动处理的文件
    print("\n需要手动处理的文件（按错误数排序）:")
    for file, errs in sorted(by_file.items(), key=lambda x: len(x[1]), reverse=True)[:30]:
        print(f"  {file}: {len(errs)} 个错误")

if __name__ == '__main__':
    main()
