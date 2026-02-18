#!/usr/bin/env python3
"""统计mypy错误类型"""
import re
import subprocess
from collections import Counter


def main():
    # 运行mypy
    result = subprocess.run(["python", "-m", "mypy", "apps/", "--strict"], capture_output=True, text=True, cwd=".")

    output = result.stdout + result.stderr

    # 提取错误类型
    error_pattern = r"\[([a-z-]+)\]"
    errors = re.findall(error_pattern, output)

    # 统计
    counter = Counter(errors)

    print("Mypy错误统计:")
    print("=" * 60)
    for error_type, count in counter.most_common():
        print(f"{error_type:30s}: {count:5d}")
    print("=" * 60)
    print(f"{'总计':30s}: {sum(counter.values()):5d}")


if __name__ == "__main__":
    main()
