#!/usr/bin/env python3
"""生成mypy-remaining-errors spec的最终修复报告"""

from __future__ import annotations

import logging
import re
import subprocess
from collections import defaultdict
from datetime import datetime
from pathlib import Path

logger = logging.getLogger(__name__)


def run_mypy() -> tuple[int, str]:
    """运行mypy检查并返回错误数和输出"""
    backend_path = Path(__file__).parent.parent

    result = subprocess.run(
        ["python", "-m", "mypy", "apps/", "--strict"],
        capture_output=True,
        text=True,
        cwd=backend_path,
    )

    output = result.stdout + result.stderr

    # 提取错误总数
    match = re.search(r"Found (\d+) errors?", output)
    error_count = int(match.group(1)) if match else 0

    return error_count, output


def analyze_errors(mypy_output: str) -> dict[str, list[dict[str, str | int]]]:
    """分析mypy输出，按错误类型分类"""
    pattern = re.compile(r"^(apps/[^:]+):(\d+):\d+:\s+error:\s+(.+?)\s+\[([a-z-]+)\]", re.MULTILINE)

    errors_by_type: dict[str, list[dict[str, str | int]]] = defaultdict(list)

    for match in pattern.finditer(mypy_output):
        file_path, line_no, message, error_code = match.groups()
        errors_by_type[error_code].append(
            {"file": file_path, "line": int(line_no), "message": message, "code": error_code}
        )

    return dict(errors_by_type)


def main() -> None:
    """主函数"""
    backend_path = Path(__file__).parent.parent

    logger.info("运行mypy检查...")
    total_errors, mypy_output = run_mypy()

    logger.info(f"当前错误总数: {total_errors}")

    # 分析错误分布
    errors_by_type = analyze_errors(mypy_output)

    # 生成报告
    report_path = backend_path / "mypy_final_report.md"

    with open(report_path, "w", encoding="utf-8") as f:
        f.write("# Mypy剩余错误修复最终报告\n\n")
        f.write(f"生成时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n\n")

        # 1. 总体统计
        f.write("## 1. 总体统计\n\n")
        f.write(f"- **当前错误总数**: {total_errors}\n")
        f.write(f"- **初始错误总数**: 2549 (spec开始时)\n")
        f.write(f"- **已修复错误数**: {2549 - total_errors}\n")
        f.write(f"- **修复进度**: {((2549 - total_errors) / 2549 * 100):.1f}%\n\n")

        # 2. 错误类型分布
        f.write("## 2. 错误类型分布\n\n")
        f.write("| 错误类型 | 数量 | 占比 |\n")
        f.write("|---------|------|------|\n")

        sorted_types = sorted(errors_by_type.items(), key=lambda x: len(x[1]), reverse=True)
        for error_type, error_list in sorted_types[:15]:
            percentage = len(error_list) / total_errors * 100 if total_errors > 0 else 0
            f.write(f"| {error_type} | {len(error_list)} | {percentage:.1f}% |\n")

        f.write("\n")

        # 3. 已完成的修复工作
        f.write("## 3. 已完成的修复工作\n\n")
        f.write("### 3.1 基础设施建设\n\n")
        f.write("- ✅ 实现ErrorAnalyzer类 - 错误分析和分类\n")
        f.write("- ✅ 实现ValidationSystem类 - 验证和回归检测\n")
        f.write("- ✅ 实现BatchFixer基类 - 批量修复框架\n\n")

        f.write("### 3.2 attr-defined错误修复\n\n")
        f.write("- ✅ 实现AttrDefinedFixer修复器\n")
        f.write("- ✅ 修复Django Model动态属性（id, objects等）\n")
        f.write("- ✅ 修复字典动态访问问题\n")
        f.write(f"- **当前剩余**: {len(errors_by_type.get('attr-defined', []))} 个\n\n")

        f.write("### 3.3 no-untyped-def错误修复\n\n")
        f.write("- ✅ 实现UntypedDefFixer修复器\n")
        f.write("- ✅ 批量修复简单函数类型注解\n")
        f.write("- ✅ 修复复杂函数和泛型函数\n")
        no_untyped_def_initial = 801
        no_untyped_def_current = len(errors_by_type.get("no-untyped-def", []))
        no_untyped_def_fixed = no_untyped_def_initial - no_untyped_def_current
        f.write(f"- **初始数量**: {no_untyped_def_initial} 个\n")
        f.write(f"- **当前剩余**: {no_untyped_def_current} 个\n")
        f.write(
            f"- **已修复**: {no_untyped_def_fixed} 个 ({no_untyped_def_fixed / no_untyped_def_initial * 100:.1f}%)\n\n"
        )

        f.write("### 3.4 其他已完成的修复\n\n")
        f.write("- ✅ 修复了大量的arg-type、assignment、return-value等错误\n")
        f.write("- ✅ 优化了类型注解的准确性和完整性\n")
        f.write("- ✅ 建立了完整的修复工作流程和验证机制\n\n")

        # 4. 修复经验总结
        f.write("## 4. 修复经验总结\n\n")

        f.write("### 4.1 成功的修复模式\n\n")
        f.write("1. **Django Model动态属性**\n")
        f.write("   - 为Model类添加显式类型注解（id, objects, DoesNotExist等）\n")
        f.write("   - 使用typing_helpers.py统一管理常用类型\n\n")

        f.write("2. **函数类型注解**\n")
        f.write("   - 使用AST分析推断参数和返回值类型\n")
        f.write("   - 优先使用具体类型，避免过度使用Any\n")
        f.write("   - 对于复杂类型使用Union和Optional\n\n")

        f.write("3. **批量修复策略**\n")
        f.write("   - 先修复简单重复的模式\n")
        f.write("   - 使用AST保持代码格式\n")
        f.write("   - 每次修复后立即验证\n\n")

        f.write("### 4.2 遇到的挑战\n\n")
        f.write("1. **复杂的类型推断**\n")
        f.write("   - 动态生成的属性难以静态分析\n")
        f.write("   - 第三方库缺少类型注解\n\n")

        f.write("2. **代码格式保持**\n")
        f.write("   - AST重建代码时可能改变格式\n")
        f.write("   - 需要careful处理注释和空行\n\n")

        # 5. 剩余工作
        f.write("## 5. 剩余工作\n\n")
        f.write("### 5.1 优先级高的错误类型\n\n")

        priority_types = ["attr-defined", "name-defined", "no-any-return", "type-arg", "no-untyped-def"]
        for error_type in priority_types:
            count = len(errors_by_type.get(error_type, []))
            if count > 0:
                f.write(f"- **{error_type}**: {count} 个\n")

        f.write("\n### 5.2 建议的修复顺序\n\n")
        f.write("1. name-defined (缺少导入) - 相对简单\n")
        f.write("2. type-arg (泛型参数) - 可批量修复\n")
        f.write("3. attr-defined (属性定义) - 需要分析\n")
        f.write("4. no-any-return (Any返回值) - 需要类型推断\n")
        f.write("5. 其他错误类型 - 逐个分析\n\n")

        # 6. 工具和脚本
        f.write("## 6. 可用的工具和脚本\n\n")
        f.write("- `scripts/mypy_tools/error_analyzer.py` - 错误分析工具\n")
        f.write("- `scripts/mypy_tools/validation_system.py` - 验证系统\n")
        f.write("- `scripts/mypy_tools/batch_fixer.py` - 批量修复框架\n")
        f.write("- `scripts/mypy_tools/attr_defined_fixer.py` - attr-defined修复器\n")
        f.write("- `scripts/mypy_tools/untyped_def_fixer.py` - no-untyped-def修复器\n")
        f.write("- `scripts/analyze_attr_defined.py` - attr-defined错误分析\n")
        f.write("- `scripts/analyze_no_untyped_def.py` - no-untyped-def错误分析\n\n")

        # 7. 结论
        f.write("## 7. 结论\n\n")
        progress = (2549 - total_errors) / 2549 * 100
        f.write(f"本spec已完成 {progress:.1f}% 的错误修复工作，")
        f.write(f"从初始的2549个错误减少到{total_errors}个。")
        f.write("建立了完整的错误分析和批量修复基础设施，")
        f.write("为后续修复工作奠定了良好基础。\n\n")

        if total_errors > 0:
            f.write(f"剩余{total_errors}个错误需要继续修复，")
            f.write("建议按照上述优先级顺序逐步处理。\n")

    logger.info(f"报告已保存到: {report_path}")


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    main()
