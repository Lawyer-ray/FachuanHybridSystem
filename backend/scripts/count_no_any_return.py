#!/usr/bin/env python
"""统计no-any-return错误"""

from __future__ import annotations

import subprocess
from pathlib import Path


def main() -> None:
    backend_path = Path(__file__).parent.parent

    # 运行mypy
    result = subprocess.run(
        ["mypy", "apps/", "--strict", "--no-error-summary"], capture_output=True, text=True, cwd=backend_path
    )

    output = result.stdout + result.stderr

    # 保存到文件
    output_file = backend_path / "mypy_full_output.txt"
    output_file.write_text(output)
    print(f"完整输出已保存到: {output_file}")

    # 统计no-any-return错误
    lines = output.split("\n")
    no_any_return_count = 0
    no_any_return_errors = []

    for i, line in enumerate(lines):
        if "no-any-return" in line:
            no_any_return_count += 1
            # 尝试找到前一行（包含文件名和行号）
            if i > 0:
                prev_line = lines[i - 1]
                if ".py:" in prev_line and ": error:" in prev_line:
                    no_any_return_errors.append(prev_line)
            # 或者当前行就包含文件名
            if ".py:" in line and ": error:" in line:
                no_any_return_errors.append(line)

    print(f"\nno-any-return错误数: {no_any_return_count}")
    print(f"可解析的错误数: {len(no_any_return_errors)}")

    # 显示前20个
    print("\n前20个错误:")
    for i, line in enumerate(no_any_return_errors[:20], 1):
        # 提取文件名和行号
        if ":" in line:
            parts = line.split(": error:")
            if len(parts) >= 1:
                print(f"{i}. {parts[0]}")


if __name__ == "__main__":
    main()

if __name__ == "__main__":
    main()
