#!/usr/bin/env python3
"""分析 arg-type 错误"""

from __future__ import annotations

import logging
import subprocess
import sys
from pathlib import Path

# 添加项目根目录到 Python 路径
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from scripts.mypy_tools.error_analyzer import ErrorAnalyzer

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)


def run_mypy() -> str:
    """运行 mypy 检查并返回输出"""
    logger.info("运行 mypy 检查...")
    try:
        result = subprocess.run(
            ["mypy", "apps/", "--strict", "--no-error-summary", "--show-column-numbers"],
            cwd=project_root,
            capture_output=True,
            text=True,
            timeout=300,
            env={**subprocess.os.environ, "COLUMNS": "200"},  # 设置终端宽度避免截断
        )
        output = result.stdout + result.stderr
        # 保存到文件以便调试
        output_file = project_root / "mypy_full_output.txt"
        output_file.write_text(output)
        logger.info(f"mypy 输出已保存到: {output_file}")
        return output
    except subprocess.TimeoutExpired:
        logger.error("mypy 运行超时")
        return ""
    except Exception as e:
        logger.error(f"运行 mypy 失败: {e}")
        return ""


def main() -> None:
    """主函数"""
    # 运行 mypy
    mypy_output = run_mypy()
    if not mypy_output:
        logger.error("无法获取 mypy 输出")
        return

    # 分析错误
    analyzer = ErrorAnalyzer()
    all_errors = analyzer.analyze(mypy_output)
    logger.info(f"总错误数: {len(all_errors)}")

    # 按类型分类
    by_type = analyzer.categorize_by_type(all_errors)

    # 提取 arg-type 错误
    arg_type_errors = by_type.get("arg-type", [])
    logger.info(f"arg-type 错误数: {len(arg_type_errors)}")

    if not arg_type_errors:
        logger.info("没有 arg-type 错误")
        return

    # 按文件分组
    by_file = analyzer.categorize_by_module(arg_type_errors)

    # 输出详细信息
    print("\n" + "=" * 80)
    print(f"arg-type 错误分析报告")
    print("=" * 80)
    print(f"\n总计: {len(arg_type_errors)} 个错误")
    print(f"涉及模块: {len(by_file)} 个\n")

    # 按模块统计
    print("按模块统计:")
    print("-" * 80)
    module_stats = sorted(
        [(module, len(errors)) for module, errors in by_file.items()], key=lambda x: x[1], reverse=True
    )
    for module, count in module_stats:
        print(f"  {module:30s} {count:4d} 个错误")

    # 详细错误列表
    print("\n详细错误列表:")
    print("-" * 80)

    for error in sorted(arg_type_errors, key=lambda e: (e.file_path, e.line)):
        print(f"\n文件: {error.file_path}:{error.line}:{error.column}")
        print(f"消息: {error.message}")
        print(f"严重程度: {error.severity}")

    print("\n" + "=" * 80)
    print("分析完成")
    print("=" * 80)

    # 保存详细报告到文件
    report_file = project_root / "arg_type_errors_report.txt"
    with open(report_file, "w", encoding="utf-8") as f:
        f.write("=" * 80 + "\n")
        f.write("arg-type 错误分析报告\n")
        f.write("=" * 80 + "\n\n")
        f.write(f"总计: {len(arg_type_errors)} 个错误\n")
        f.write(f"涉及模块: {len(by_file)} 个\n\n")

        f.write("按模块统计:\n")
        f.write("-" * 80 + "\n")
        for module, count in module_stats:
            f.write(f"  {module:30s} {count:4d} 个错误\n")

        f.write("\n详细错误列表:\n")
        f.write("-" * 80 + "\n")
        for error in sorted(arg_type_errors, key=lambda e: (e.file_path, e.line)):
            f.write(f"\n文件: {error.file_path}:{error.line}:{error.column}\n")
            f.write(f"消息: {error.message}\n")
            f.write(f"严重程度: {error.severity}\n")

        f.write("\n" + "=" * 80 + "\n")
        f.write("分析完成\n")
        f.write("=" * 80 + "\n")

    logger.info(f"详细报告已保存到: {report_file}")


if __name__ == "__main__":
    main()
