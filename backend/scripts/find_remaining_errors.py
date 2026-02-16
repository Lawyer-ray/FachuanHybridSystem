"""查找剩余的no-any-return错误"""

import re
import subprocess
from pathlib import Path

result = subprocess.run(
    ["python", "-m", "mypy", "apps/", "--strict", "--show-absolute-path"],
    capture_output=True,
    text=True,
    cwd=Path(__file__).parent.parent,
)

output = result.stdout + result.stderr

# 查找所有包含no-any-return的行
lines = output.split("\n")
for i, line in enumerate(lines):
    if "[no-any-return]" in line:
        print(f"Line {i}: {line}")
        # 打印前后几行以获取上下文
        if i > 0:
            print(f"  Previous: {lines[i-1]}")
        if i < len(lines) - 1:
            print(f"  Next: {lines[i+1]}")
        print()
