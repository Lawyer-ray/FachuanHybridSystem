#!/usr/bin/env python3
"""分析 SMS 模块的 mypy 类型错误 - 直接运行 mypy"""

import re
import subprocess
from collections import Counter, defaultdict
from pathlib import Path


def run_mypy() -> str:
    """运行 mypy 并获取输出"""
    result = subprocess.run(
        ["mypy", "apps/automation/services/sms/", "--strict", "--show-error-codes"],
        capture_output=True,
        text=True,
        cwd=".",
    )
    return result.stdout + result.stderr


def parse_errors(output: str) -> list[dict]:
    """解析 mypy 错误"""
    errors = []
    for line in output.split("\n"):
        if not line.startswith("apps/automation/services/sms/"):
            continue

        # 匹配: file:line:col: error: message [error-code]
        match = re.match(r"^([^:]+):(\d+):(\d+): error: (.+?)(?:\s+\[([^\]]+)\])?$", line)
        if match:
            file_path, line_num, col, message, error_code = match.groups()
            errors.append(
                {
                    "file": file_path,
                    "line": int(line_num),
                    "col": int(col),
                    "message": message.strip(),
                    "error_code": error_code or "unknown",
                }
            )
    return errors


def categorize_errors(errors: list[dict]) -> dict:
    """分类错误"""
    by_code = defaultdict(list)
    by_file = defaultdict(list)

    for error in errors:
        by_code[error["error_code"]].append(error)
        file_name = Path(error["file"]).name
        by_file[file_name].append(error)

    return {"by_code": dict(by_code), "by_file": dict(by_file), "total": len(errors)}


def generate_report(categorized: dict) -> str:
    """生成报告"""
    lines = []
    lines.append("# SMS 模块 Mypy 类型错误分析报告\n")
    lines.append(f"**总错误数**: {categorized['total']}\n")
    lines.append(f"**涉及文件数**: {len(categorized['by_file'])}\n")
    lines.append(f"**错误类型数**: {len(categorized['by_code'])}\n")

    # 按错误类型统计
    lines.append("## 按错误类型分类\n")
    sorted_codes = sorted(categorized["by_code"].items(), key=lambda x: len(x[1]), reverse=True)

    for error_code, error_list in sorted_codes:
        count = len(error_list)
        percentage = (count / categorized["total"] * 100) if categorized["total"] > 0 else 0
        lines.append(f"### {error_code} - {count} 个错误 ({percentage:.1f}%)\n")

        # 显示前3个示例
        for i, error in enumerate(error_list[:3], 1):
            file_name = Path(error["file"]).name
            lines.append(f"{i}. `{file_name}:{error['line']}`")
            lines.append(f"   ```")
            lines.append(f"   {error['message']}")
            lines.append(f"   ```\n")

        if len(error_list) > 3:
            lines.append(f"_... 还有 {len(error_list) - 3} 个类似错误_\n")
        lines.append("")

    # 按文件统计
    lines.append("## 按文件分类 (错误数 Top 15)\n")
    sorted_files = sorted(categorized["by_file"].items(), key=lambda x: len(x[1]), reverse=True)

    lines.append("| 文件 | 错误数 | 占比 |")
    lines.append("|------|--------|------|")
    for file_name, error_list in sorted_files[:15]:
        count = len(error_list)
        percentage = (count / categorized["total"] * 100) if categorized["total"] > 0 else 0
        lines.append(f"| {file_name} | {count} | {percentage:.1f}% |")

    if len(sorted_files) > 15:
        remaining = sum(len(errors) for _, errors in sorted_files[15:])
        lines.append(f"| _其他 {len(sorted_files) - 15} 个文件_ | {remaining} | ... |")

    lines.append("")

    # 错误类型说明
    lines.append("## 常见错误类型说明\n")
    lines.append("- **attr-defined**: 属性不存在（通常是模型字段缺失或类型存根问题）")
    lines.append("- **no-any-return**: 函数返回 Any 类型但声明了具体返回类型")
    lines.append("- **assignment**: 类型不兼容的赋值操作")
    lines.append("- **arg-type**: 函数参数类型不匹配")
    lines.append("- **type-arg**: 缺少泛型类型参数（如 dict, list）")
    lines.append("- **no-untyped-def**: 函数缺少类型注解")
    lines.append("- **name-defined**: 名称未定义")
    lines.append("- **misc**: 其他杂项类型错误")
    lines.append("- **return-value**: 返回值类型不匹配")
    lines.append("")

    return "\n".join(lines)


def main():
    print("正在运行 mypy 扫描...")
    output = run_mypy()

    print("正在解析错误...")
    errors = parse_errors(output)

    if not errors:
        print("未找到 SMS 模块的类型错误")
        return

    print(f"找到 {len(errors)} 个错误")

    print("正在分类统计...")
    categorized = categorize_errors(errors)

    print("正在生成报告...")
    report = generate_report(categorized)

    # 保存报告
    report_file = "sms_errors_analysis.md"
    with open(report_file, "w", encoding="utf-8") as f:
        f.write(report)

    print(f"\n✅ 分析完成！")
    print(f"- 总错误数: {categorized['total']}")
    print(f"- 错误类型数: {len(categorized['by_code'])}")
    print(f"- 涉及文件数: {len(categorized['by_file'])}")
    print(f"- 报告已保存到: {report_file}")

    # 显示 Top 5 错误类型
    print(f"\nTop 5 错误类型:")
    sorted_codes = sorted(categorized["by_code"].items(), key=lambda x: len(x[1]), reverse=True)
    for error_code, error_list in sorted_codes[:5]:
        print(f"  {error_code}: {len(error_list)} 个")


if __name__ == "__main__":
    main()
