#!/usr/bin/env python3
"""分析特定类型的mypy错误"""
import re
import subprocess
import sys


def main():
    if len(sys.argv) < 2:
        print("Usage: python analyze_errors_by_type.py <error_type>")
        print("Example: python analyze_errors_by_type.py assignment")
        sys.exit(1)

    error_type = sys.argv[1]

    # 运行mypy
    result = subprocess.run(["python", "-m", "mypy", "apps/", "--strict"], capture_output=True, text=True, cwd=".")

    output = result.stdout + result.stderr
    lines = output.split("\n")

    # 过滤特定错误类型
    matching_errors = []
    for line in lines:
        if f"[{error_type}]" in line and "error:" in line:
            matching_errors.append(line)

    print(f"找到 {len(matching_errors)} 个 [{error_type}] 错误:")
    print("=" * 100)

    for i, error in enumerate(matching_errors[:50], 1):  # 只显示前50个
        print(f"{i}. {error.strip()}")

    if len(matching_errors) > 50:
        print(f"\n... 还有 {len(matching_errors) - 50} 个错误未显示")


if __name__ == "__main__":
    main()
