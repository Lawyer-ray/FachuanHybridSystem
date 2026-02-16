#!/usr/bin/env python3
"""分析 mypy 错误类型"""

import argparse
import re
import subprocess
import sys
from collections import Counter

parser = argparse.ArgumentParser()
parser.add_argument("--config-file", default="mypy.ini")
parser.add_argument("targets", nargs="*", default=["apps/"])
args = parser.parse_args()

result = subprocess.run(
    [sys.executable, "-m", "mypy", "--config-file", args.config_file, *args.targets],
    capture_output=True,
    text=True,
)

end_code = re.compile(r"\s\[([a-z][a-z0-9\-]+)\]\s*$")
standalone_code = re.compile(r"^\s*\[([a-z][a-z0-9\-]+)\]\s*$")
error_start = re.compile(r"^[^:]+:\d+:\d+:\s+error:")

errors: list[str] = []
pending = False
pending_has_code = False
for raw_line in result.stdout.splitlines():
    line = raw_line.rstrip("\n")
    if error_start.match(line):
        pending = True
        pending_has_code = False
        match = end_code.search(line)
        if match:
            errors.append(match.group(1))
            pending_has_code = True
        continue

    if pending:
        match = end_code.search(line)
        if match:
            errors.append(match.group(1))
            pending_has_code = True
            continue
        match = standalone_code.match(line)
        if match:
            errors.append(match.group(1))
            pending_has_code = True
            continue

counter = Counter(errors)
print("错误类型分布:")
for error_type, count in counter.most_common(20):
    print(f"  {error_type:30s}: {count:4d}")

print(f"\n总错误数: {len(errors)}")
