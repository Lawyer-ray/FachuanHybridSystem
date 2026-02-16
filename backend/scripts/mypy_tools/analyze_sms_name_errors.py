#!/usr/bin/env python
"""分析 SMS 模块的 name-defined 错误"""
import subprocess
import re
import os
from collections import defaultdict
from pathlib import Path

def main() -> None:
    # 获取当前目录
    backend_dir = Path(__file__).parent.parent
    
    # 运行 mypy
    result = subprocess.run(
        ['python', '-m', 'mypy', 'apps/automation/services/sms/', '--strict', '--show-error-codes'],
        capture_output=True,
        text=True,
        cwd=str(backend_dir)
    )
    
    output = result.stdout + result.stderr
    
    # 提取 name-defined 错误
    errors = defaultdict(list)
    
    for line in output.split('\n'):
        if 'name-defined' in line and 'apps/automation/services/sms' in line:
            # 提取文件名和错误信息
            match = re.match(r'(apps/automation/services/sms/[^:]+):(\d+):(\d+): error: (.+) \[name-defined\]', line)
            if match:
                file_path = match.group(1)
                line_no = match.group(2)
                error_msg = match.group(4)
                errors[file_path].append((line_no, error_msg))
    
    # 打印结果
    print(f"SMS 模块 name-defined 错误统计:")
    print(f"总计: {sum(len(v) for v in errors.values())} 个错误")
    print(f"涉及文件: {len(errors)} 个\n")
    
    for file_path in sorted(errors.keys()):
        print(f"\n{file_path}:")
        for line_no, error_msg in errors[file_path]:
            print(f"  Line {line_no}: {error_msg}")

if __name__ == '__main__':
    main()
