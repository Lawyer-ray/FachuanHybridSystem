#!/usr/bin/env python3
"""测试错误解析"""

import subprocess
import re
from pathlib import Path

result = subprocess.run(
    ["python", "-m", "mypy", "apps/", "--strict"],
    capture_output=True,
    text=True,
    cwd=Path(__file__).parent.parent
)

output = result.stdout + result.stderr
lines = output.split('\n')

print(f"总行数: {len(lines)}")
print("\n前20行:")
for i, line in enumerate(lines[:20], 1):
    print(f"{i}: {repr(line)}")

# 统计错误
error_lines = [line for line in lines if 'error:' in line]
print(f"\n包含'error:'的行数: {len(error_lines)}")

# 尝试解析
errors = []
for line in lines:
    if 'error:' in line and '[' in line:
        match = re.match(r'^(.+?):(\d+):', line)
        if match:
            file_path, line_num = match.groups()
            error_code_match = re.search(r'\[([a-z-]+)\]', line)
            if error_code_match:
                error_code = error_code_match.group(1)
                errors.append((file_path, int(line_num), error_code))

print(f"\n成功解析的错误数: {len(errors)}")

# 统计错误类型
error_types = {}
for _, _, error_code in errors:
    error_types[error_code] = error_types.get(error_code, 0) + 1

print("\n错误类型分布:")
for error_type, count in sorted(error_types.items(), key=lambda x: x[1], reverse=True)[:10]:
    print(f"  {error_type}: {count}")
