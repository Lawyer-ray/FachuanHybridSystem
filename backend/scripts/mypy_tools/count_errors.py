"""统计mypy错误类型"""

from __future__ import annotations

import re
import subprocess
from collections import Counter
from pathlib import Path


def main() -> None:
    backend_path = Path(__file__).parent.parent.parent
    
    result = subprocess.run(
        ['mypy', 'apps/', '--strict'],
        capture_output=True,
        text=True,
        cwd=backend_path,
        timeout=300
    )
    
    error_types: Counter[str] = Counter()
    
    for line in result.stdout.split('\n'):
        if ': error:' in line:
            match = re.search(r'\[([a-z-]+)\]$', line)
            if match:
                error_types[match.group(1)] += 1
    
    print(f"总错误数: {sum(error_types.values())}\n")
    print("错误类型分布:")
    for error_type, count in error_types.most_common(20):
        percentage = count / sum(error_types.values()) * 100
        print(f"  {error_type:25s} {count:4d} ({percentage:5.1f}%)")


if __name__ == '__main__':
    main()
