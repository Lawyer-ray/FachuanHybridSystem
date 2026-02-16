#!/usr/bin/env python3
"""分析复杂的no-any-return错误"""
import re
from collections import defaultdict
from pathlib import Path


def parse_mypy_errors(error_file: Path) -> list[dict[str, str]]:
    """解析mypy错误输出"""
    errors = []
    with open(error_file) as f:
        for line in f:
            # 格式: file:line:col: error: message [no-any-return]
            match = re.match(r"(.+?):(\d+):(\d+): error: (.+?) \[no-any-return\]", line)
            if match:
                errors.append(
                    {
                        "file": match.group(1),
                        "line": int(match.group(2)),
                        "column": int(match.group(3)),
                        "message": match.group(4).strip(),
                    }
                )
    return errors


def categorize_errors(errors: list[dict[str, str]]) -> dict[str, list[dict[str, str]]]:
    """按返回类型分类错误"""
    categories = defaultdict(list)

    for error in errors:
        msg = error["message"]
        # 提取返回类型
        if "declared to return" in msg:
            # 提取 "declared to return "XXX"" 中的 XXX
            match = re.search(r'declared to return "([^"]+)"', msg)
            if match:
                return_type = match.group(1)
                categories[return_type].append(error)

    return categories


def main():
    error_file = Path("/tmp/no_any_return_current.txt")
    errors = parse_mypy_errors(error_file)

    print(f"总错误数: {len(errors)}\n")

    # 按返回类型分类
    categories = categorize_errors(errors)

    print("按返回类型分类:")
    for return_type, errs in sorted(categories.items(), key=lambda x: len(x[1]), reverse=True):
        print(f"  {return_type}: {len(errs)} 个")

    print("\n\n复杂类型（泛型T）详情:")
    if "T" in categories:
        for err in categories["T"]:
            print(f"  {err['file']}:{err['line']}")

    print("\n\n按文件统计（前20）:")
    file_counts = defaultdict(int)
    for err in errors:
        file_counts[err["file"]] += 1

    for file, count in sorted(file_counts.items(), key=lambda x: x[1], reverse=True)[:20]:
        print(f"  {file}: {count} 个")


if __name__ == "__main__":
    main()
