#!/usr/bin/env python3
"""分析 contracts 模块的 mypy 错误"""

import re
import subprocess
from collections import defaultdict
from pathlib import Path


def run_mypy_on_contracts() -> list[str]:
    """运行 mypy 检查 contracts 模块"""
    result = subprocess.run(
        ["mypy", "apps/contracts/", "--strict"], capture_output=True, text=True, cwd=Path(__file__).parent.parent
    )
    return result.stdout.split("\n")


def parse_error_line(line: str) -> dict[str, str] | None:
    """解析错误行"""
    # 匹配格式: apps/contracts/file.py:line:col: error: message [error-code]
    pattern = r"^(apps/contracts/[^:]+):(\d+):(\d+): error: (.+?)(?:\s+\[([^\]]+)\])?$"
    match = re.match(pattern, line)

    if match:
        return {
            "file": match.group(1),
            "line": match.group(2),
            "col": match.group(3),
            "message": match.group(4),
            "code": match.group(5) if match.group(5) else "unknown",
        }
    return None


def categorize_error(error: dict[str, str]) -> str:
    """分类错误类型"""
    message = error["message"]
    code = error["code"]

    # 根据错误代码分类
    if code == "attr-defined":
        if '"Contract" has no attribute' in message:
            return "Django ORM - Contract 属性"
        elif '"QuerySet"' in message:
            return "Django ORM - QuerySet 泛型"
        else:
            return "attr-defined - 其他"
    elif code == "no-untyped-def":
        return "函数缺少类型注解"
    elif code == "return-value":
        return "返回值类型不匹配"
    elif code == "arg-type":
        return "参数类型不匹配"
    elif code == "no-any-return":
        return "返回 Any 类型"
    elif code == "type-arg":
        return "泛型参数缺失"
    elif code == "misc":
        if "Self argument missing" in message:
            return "缺少 self 参数"
        else:
            return "misc - 其他"
    elif code == "name-defined":
        return "变量未定义"
    elif code == "assignment":
        return "赋值类型不匹配"
    elif "Signature" in message:
        return "方法签名不匹配"
    else:
        return f"{code} - 其他"


def main():
    print("正在运行 mypy 检查 contracts 模块...")
    lines = run_mypy_on_contracts()

    errors = []
    for line in lines:
        error = parse_error_line(line)
        if error:
            errors.append(error)

    print(f"\n总错误数: {len(errors)}")

    # 按类别统计
    categories = defaultdict(list)
    for error in errors:
        category = categorize_error(error)
        categories[category].append(error)

    print("\n按错误类别统计:")
    print("-" * 80)
    for category, errs in sorted(categories.items(), key=lambda x: len(x[1]), reverse=True):
        print(f"{category:40} {len(errs):4} ({len(errs)/len(errors)*100:5.1f}%)")

    # 按文件统计
    files = defaultdict(int)
    for error in errors:
        files[error["file"]] += 1

    print("\n错误最多的文件 (Top 20):")
    print("-" * 80)
    for file, count in sorted(files.items(), key=lambda x: x[1], reverse=True)[:20]:
        short_file = file.replace("apps/contracts/", "")
        print(f"{short_file:60} {count:4}")

    # 输出详细错误到文件
    output_file = Path(__file__).parent.parent / "contracts_errors_analysis.txt"
    with open(output_file, "w", encoding="utf-8") as f:
        f.write("=" * 80 + "\n")
        f.write("Contracts 模块错误详细分析\n")
        f.write("=" * 80 + "\n\n")

        for category, errs in sorted(categories.items(), key=lambda x: len(x[1]), reverse=True):
            f.write(f"\n{category} ({len(errs)} 个错误)\n")
            f.write("-" * 80 + "\n")
            for error in errs[:10]:  # 每个类别只显示前 10 个
                f.write(f"{error['file']}:{error['line']}\n")
                f.write(f"  {error['message']}\n\n")

    print(f"\n详细错误已保存到: {output_file}")


if __name__ == "__main__":
    main()
