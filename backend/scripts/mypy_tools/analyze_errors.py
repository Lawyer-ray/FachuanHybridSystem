"""分析mypy错误类型分布"""

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
    
    # 解析错误类型
    for line in result.stdout.split('\n'):
        if ': error:' in line and '[' in line and ']' in line:
            # 提取错误类型 [error-type]
            match = re.search(r'\[([a-z-]+)\]', line)
            if match:
                error_types[match.group(1)] += 1
    
    total = sum(error_types.values())
    print(f"总错误数: {total}\n")
    print("错误类型分布 (前20):")
    print("-" * 60)
    for error_type, count in error_types.most_common(20):
        percentage = count / total * 100 if total > 0 else 0
        print(f"  {error_type:30s} {count:5d} ({percentage:5.1f}%)")


if __name__ == '__main__':
    main()
