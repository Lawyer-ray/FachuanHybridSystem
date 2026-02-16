#!/usr/bin/env python3
"""
批量修复 services 层的 mypy 类型错误

优先修复 no-untyped-def 错误
"""

import re
import subprocess
from pathlib import Path
from typing import Any

# 运行 mypy 并获取 no-untyped-def 错误
result = subprocess.run(
    ["source", ".venv/bin/activate", "&&", "mypy", "--config-file", "mypy.ini", "apps/*/services/"],
    shell=True,
    executable="/bin/zsh",
    capture_output=True,
    text=True,
    cwd=Path(__file__).parent,
)

errors = result.stdout + result.stderr

# 解析错误
no_untyped_def_errors = []
for line in errors.split("\n"):
    if "[no-untyped-def]" in line and line.startswith("apps/"):
        # 提取文件路径和行号
        match = re.match(r"^(apps/[^:]+):(\d+):", line)
        if match:
            file_path = match.group(1)
            line_num = int(match.group(2))
            no_untyped_def_errors.append((file_path, line_num, line))

print(f"找到 {len(no_untyped_def_errors)} 个 no-untyped-def 错误")

# 按文件分组
from collections import defaultdict

errors_by_file = defaultdict(list)
for file_path, line_num, error_line in no_untyped_def_errors:
    errors_by_file[file_path].append((line_num, error_line))

print(f"涉及 {len(errors_by_file)} 个文件")

# 修复每个文件
fixed_count = 0
for file_path, errors in list(errors_by_file.items())[:20]:  # 先处理前 20 个文件
    print(f"\n处理文件: {file_path} ({len(errors)} 个错误)")

    try:
        with open(file_path, "r", encoding="utf-8") as f:
            lines = f.readlines()

        modified = False
        for line_num, error_line in errors:
            idx = line_num - 1
            if idx >= len(lines):
                continue

            line = lines[idx]

            # 修复常见模式
            # 1. def method(self): -> def method(self) -> None:
            if re.search(r"def \w+\(self\):\s*$", line):
                lines[idx] = line.rstrip() + " -> None:\n"
                modified = True
                fixed_count += 1

            # 2. def method(self, param): -> def method(self, param: Any) -> None:
            elif re.search(r"def \w+\(self,\s*\w+\):\s*$", line):
                lines[idx] = re.sub(r"def (\w+)\(self,\s*(\w+)\):", r"def \1(self, \2: Any) -> None:", line)
                modified = True
                fixed_count += 1

            # 3. def function(): -> def function() -> None:
            elif re.search(r"def \w+\(\):\s*$", line):
                lines[idx] = line.rstrip() + " -> None:\n"
                modified = True
                fixed_count += 1

        if modified:
            # 确保有 typing 导入
            has_any_import = any("from typing import" in l and "Any" in l for l in lines)
            if not has_any_import and "Any" in "".join(lines):
                # 找到第一个 import 语句的位置
                import_idx = 0
                for i, l in enumerate(lines):
                    if l.startswith("from ") or l.startswith("import "):
                        import_idx = i
                        break

                # 在第一个 import 后插入
                if import_idx > 0:
                    lines.insert(import_idx + 1, "from typing import Any\n")

            with open(file_path, "w", encoding="utf-8") as f:
                f.writelines(lines)

            print(f"  ✓ 已修复")

    except Exception as e:
        print(f"  ✗ 错误: {e}")

print(f"\n总共修复了 {fixed_count} 个错误")
