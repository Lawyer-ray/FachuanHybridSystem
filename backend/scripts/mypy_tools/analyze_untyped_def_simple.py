#!/usr/bin/env python3
"""简单分析no-untyped-def错误"""

from __future__ import annotations

import re
import subprocess
from collections import defaultdict
from pathlib import Path


def main() -> None:
    """主函数"""
    print("运行mypy检查...")
    result = subprocess.run(
        ["python", "-m", "mypy", "apps/", "--strict"],
        capture_output=True,
        text=True,
        cwd=Path(__file__).parent.parent,
    )

    output = result.stdout + result.stderr
    lines = output.split("\n")

    # 解析错误
    error_pattern = re.compile(r"^(apps/[^:]+):(\d+):(\d+): error: (.+) \[no-untyped-def\]")

    errors = []
    for line in lines:
        match = error_pattern.match(line)
        if match:
            file_path, line_no, col, message = match.groups()
            errors.append({"file": file_path, "line": int(line_no), "col": int(col), "message": message})

    print(f"\n找到 {len(errors)} 个no-untyped-def错误")

    # 按文件分组
    by_file = defaultdict(list)
    for error in errors:
        by_file[error["file"]].append(error)

    print(f"涉及 {len(by_file)} 个文件")

    # 按消息类型分类
    by_type = defaultdict(list)
    for error in errors:
        msg = error["message"]
        if "missing a return type annotation" in msg:
            by_type["missing_return"].append(error)
        elif "missing a type annotation for one or more arguments" in msg:
            by_type["missing_args"].append(error)
        elif "missing a type annotation" in msg:
            by_type["missing_annotation"].append(error)
        else:
            by_type["other"].append(error)

    print("\n按错误类型分类:")
    for error_type, error_list in sorted(by_type.items(), key=lambda x: len(x[1]), reverse=True):
        print(f"  {error_type}: {len(error_list)}")

    # 显示错误最多的前20个文件
    print("\n错误最多的前20个文件:")
    sorted_files = sorted(by_file.items(), key=lambda x: len(x[1]), reverse=True)
    for file_path, file_errors in sorted_files[:20]:
        print(f"  {file_path}: {len(file_errors)}")

    # 显示一些示例
    print("\n示例错误:")
    for i, error in enumerate(errors[:10], 1):
        print(f"\n{i}. {error['file']}:{error['line']}")
        print(f"   {error['message']}")

    # 保存详细报告
    report_path = Path(__file__).parent.parent / "no_untyped_def_report.txt"
    with open(report_path, "w") as f:
        f.write(f"no-untyped-def错误分析报告\n")
        f.write(f"=" * 80 + "\n\n")
        f.write(f"总错误数: {len(errors)}\n")
        f.write(f"涉及文件数: {len(by_file)}\n\n")

        f.write("按错误类型分类:\n")
        for error_type, error_list in sorted(by_type.items(), key=lambda x: len(x[1]), reverse=True):
            f.write(f"  {error_type}: {len(error_list)}\n")

        f.write("\n按文件分组 (错误数 >= 5):\n")
        for file_path, file_errors in sorted_files:
            if len(file_errors) >= 5:
                f.write(f"\n{file_path} ({len(file_errors)} 个错误):\n")
                for error in file_errors:
                    f.write(f"  Line {error['line']}: {error['message']}\n")

    print(f"\n详细报告已保存到: {report_path}")


if __name__ == "__main__":
    main()
