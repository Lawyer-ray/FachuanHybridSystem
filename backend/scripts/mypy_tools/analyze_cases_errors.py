#!/usr/bin/env python3
"""分析 cases 模块的 mypy 错误"""
from __future__ import annotations

import re
import subprocess
from collections import Counter
from pathlib import Path


def main() -> None:
    # 运行 mypy
    result = subprocess.run(
        ["venv312/bin/mypy", "apps/cases/", "--strict"],
        capture_output=True,
        text=True,
        cwd=Path(__file__).parent.parent,
    )

    lines = result.stdout.split("\n")

    # 只保留 cases 模块的错误
    cases_errors = [line for line in lines if "apps/cases/" in line and "error:" in line]

    print(f"Cases 模块总错误数: {len(cases_errors)}\n")

    # 统计错误类型
    error_types = []
    for line in cases_errors:
        # 错误类型在行尾的方括号中
        match = re.search(r"\[([a-z-]+)\]\s*$", line)
        if match:
            error_types.append(match.group(1))

    print("错误类型分布:")
    for error_type, count in Counter(error_types).most_common(15):
        print(f"  {error_type:25s} {count:4d}")

    print(f"\n总计: {len(error_types)} 个错误")

    # 统计文件分布
    file_errors = []
    for line in cases_errors:
        match = re.match(r"(apps/cases/[^:]+)", line)
        if match:
            file_errors.append(match.group(1))

    print("\n\n文件错误分布 (Top 20):")
    for file_path, count in Counter(file_errors).most_common(20):
        rel_path = file_path.replace("apps/cases/", "")
        print(f"  {rel_path:60s} {count:3d}")


if __name__ == "__main__":
    main()
