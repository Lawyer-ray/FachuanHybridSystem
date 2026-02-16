#!/usr/bin/env python3
"""分析 cases 模块的 mypy 类型错误"""

import re
from collections import defaultdict
from pathlib import Path


def main() -> None:
    error_file = Path(__file__).parent.parent / "cases_errors.txt"

    if not error_file.exists():
        print(f"错误文件不存在: {error_file}")
        return

    content = error_file.read_text(encoding="utf-8")

    # 统计 cases 模块的错误
    cases_errors = []
    error_types: dict[str, int] = defaultdict(int)
    file_errors: dict[str, int] = defaultdict(int)

    # 匹配错误行
    pattern = r"(apps/cases/[^:]+):(\d+):(\d+): error: (.+?) \[([^\]]+)\]"

    for match in re.finditer(pattern, content):
        file_path, line_num, col, message, error_type = match.groups()
        cases_errors.append((file_path, line_num, error_type, message))
        error_types[error_type] += 1
        file_errors[file_path] += 1

    total_errors = len(cases_errors)

    print("=" * 80)
    print("Cases 模块 Mypy 类型错误分析报告")
    print("=" * 80)
    print(f"\n总错误数: {total_errors}\n")

    # 按错误类型统计
    print("-" * 80)
    print("错误类型分布（Top 15）:")
    print("-" * 80)
    print(f"{'错误类型':<40} {'数量':>10} {'占比':>10}")
    print("-" * 80)

    for i, (error_type, count) in enumerate(sorted(error_types.items(), key=lambda x: x[1], reverse=True)[:15], 1):
        percentage = (count / total_errors * 100) if total_errors > 0 else 0
        print(f"{i:2}. {error_type:<37} {count:>10} {percentage:>9.1f}%")

    # 按文件统计
    print("\n" + "-" * 80)
    print("文件错误分布（Top 15）:")
    print("-" * 80)
    print(f"{'文件路径':<60} {'错误数':>10}")
    print("-" * 80)

    for i, (file_path, count) in enumerate(sorted(file_errors.items(), key=lambda x: x[1], reverse=True)[:15], 1):
        # 简化文件路径显示
        short_path = file_path.replace("apps/cases/", "")
        print(f"{i:2}. {short_path:<57} {count:>10}")

    # 错误类型示例
    print("\n" + "=" * 80)
    print("主要错误类型示例（每类最多3个）:")
    print("=" * 80)

    examples_by_type: dict[str, list[tuple[str, str, str]]] = defaultdict(list)
    for file_path, line_num, error_type, message in cases_errors:
        if len(examples_by_type[error_type]) < 3:
            examples_by_type[error_type].append((file_path, line_num, message))

    for error_type in sorted(error_types.keys(), key=lambda x: error_types[x], reverse=True)[:10]:
        print(f"\n[{error_type}] ({error_types[error_type]} 个错误)")
        print("-" * 80)
        for file_path, line_num, message in examples_by_type[error_type]:
            short_path = file_path.replace("apps/cases/", "")
            # 清理消息中的换行
            clean_message = " ".join(message.split())[:100]
            print(f"  • {short_path}:{line_num}")
            print(f"    {clean_message}")

    # 保存统计结果
    output_file = Path(__file__).parent.parent / "cases_errors_summary.txt"
    with open(output_file, "w", encoding="utf-8") as f:
        f.write("=" * 80 + "\n")
        f.write("Cases 模块 Mypy 类型错误分析报告\n")
        f.write("=" * 80 + "\n")
        f.write(f"\n总错误数: {total_errors}\n\n")

        f.write("-" * 80 + "\n")
        f.write("错误类型分布:\n")
        f.write("-" * 80 + "\n")
        for error_type, count in sorted(error_types.items(), key=lambda x: x[1], reverse=True):
            percentage = (count / total_errors * 100) if total_errors > 0 else 0
            f.write(f"{error_type:<40} {count:>10} {percentage:>9.1f}%\n")

        f.write("\n" + "-" * 80 + "\n")
        f.write("文件错误分布:\n")
        f.write("-" * 80 + "\n")
        for file_path, count in sorted(file_errors.items(), key=lambda x: x[1], reverse=True):
            f.write(f"{file_path:<60} {count:>10}\n")

    print(f"\n\n统计结果已保存到: {output_file}")


if __name__ == "__main__":
    main()
