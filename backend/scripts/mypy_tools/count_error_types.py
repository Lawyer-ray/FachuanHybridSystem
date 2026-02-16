"""统计mypy错误类型分布"""

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
    
    # 统计错误类型
    error_types: Counter[str] = Counter()
    
    # 统计特定错误模式
    patterns = {
        'no-any-return': 0,
        'attr-defined': 0,
        'arg-type': 0,
        'assignment': 0,
        'return-value': 0,
        'type-arg': 0,
        'name-defined': 0,
        'no-untyped-def': 0,
        'misc': 0,
        'union-attr': 0,
        'call-arg': 0,
        'override': 0,
        'operator': 0,
        'index': 0,
        'no-redef': 0,
    }
    
    for line in result.stdout.split('\n'):
        if ': error:' in line:
            for error_type in patterns.keys():
                if f'[{error_type}]' in line:
                    patterns[error_type] += 1
                    break
    
    total = sum(patterns.values())
    print(f"总错误数: {total}\n")
    print("错误类型分布:")
    print("-" * 60)
    
    for error_type, count in sorted(patterns.items(), key=lambda x: x[1], reverse=True):
        if count > 0:
            percentage = count / total * 100 if total > 0 else 0
            print(f"  {error_type:25s} {count:5d} ({percentage:5.1f}%)")


if __name__ == '__main__':
    main()
