#!/usr/bin/env python3
"""批量修复no-untyped-def错误"""

from __future__ import annotations

import logging
import subprocess
import sys
from collections import defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from mypy_tools.error_analyzer import ErrorAnalyzer, ErrorRecord
from mypy_tools.untyped_def_fixer import UntypedDefFixer

logging.basicConfig(level=logging.INFO, format="%(message)s")
logger = logging.getLogger(__name__)


def parse_mypy_output_manually(output: str) -> list[ErrorRecord]:
    """手动解析mypy输出"""
    import re

    errors = []
    lines = output.split("\n")

    # 匹配错误行的模式
    pattern = re.compile(r"^(apps/[^:]+):(\d+):(\d+):\s+error:\s+(.+?)\s+\[no-untyped-def\]")

    for line in lines:
        match = pattern.match(line)
        if match:
            file_path, line_no, col, message = match.groups()
            error = ErrorRecord(
                file_path=file_path,
                line=int(line_no),
                column=int(col),
                error_code="no-untyped-def",
                message=message,
                severity="high",
                fixable=True,
                fix_pattern="add_type_annotations",
            )
            errors.append(error)

    return errors


def main() -> None:
    """主函数"""
    backend_path = Path(__file__).parent.parent

    logger.info("运行mypy检查...")
    result = subprocess.run(
        ["python", "-m", "mypy", "apps/", "--strict", "--no-pretty", "--no-error-summary"],
        capture_output=True,
        text=True,
        cwd=backend_path,
    )

    output = result.stdout + result.stderr

    # 手动解析错误
    logger.info("解析错误...")
    errors = parse_mypy_output_manually(output)

    logger.info(f"找到 {len(errors)} 个no-untyped-def错误")

    if not errors:
        logger.info("没有找到no-untyped-def错误")
        return

    # 按文件分组
    by_file: dict[str, list[ErrorRecord]] = defaultdict(list)
    for error in errors:
        by_file[error.file_path].append(error)

    logger.info(f"涉及 {len(by_file)} 个文件")

    # 显示错误最多的前10个文件
    sorted_files = sorted(by_file.items(), key=lambda x: len(x[1]), reverse=True)
    logger.info("\n错误最多的前10个文件:")
    for file_path, file_errors in sorted_files[:10]:
        logger.info(f"  {file_path}: {len(file_errors)}")

    # 创建修复器
    fixer = UntypedDefFixer(backend_path=backend_path)

    # 批量修复
    total_fixed = 0
    total_remaining = 0
    failed_files = []

    logger.info("\n开始批量修复...")
    for i, (file_path, file_errors) in enumerate(sorted_files, 1):
        logger.info(f"\n[{i}/{len(by_file)}] 修复 {file_path} ({len(file_errors)} 个错误)...")

        # 备份文件
        fixer.backup_file(file_path)

        # 修复文件
        result = fixer.fix_file(file_path, file_errors)

        if result.success:
            total_fixed += result.errors_fixed
            total_remaining += result.errors_remaining
            logger.info(f"  ✓ 修复了 {result.errors_fixed} 个错误，剩余 {result.errors_remaining} 个")
        else:
            failed_files.append((file_path, result.error_message))
            logger.info(f"  ✗ 修复失败: {result.error_message}")

    # 生成报告
    logger.info("\n" + "=" * 80)
    logger.info("修复完成")
    logger.info("=" * 80)
    logger.info(f"总错误数: {len(errors)}")
    logger.info(f"已修复: {total_fixed}")
    logger.info(f"剩余: {total_remaining}")
    logger.info(f"失败文件数: {len(failed_files)}")

    if failed_files:
        logger.info("\n失败的文件:")
        for file_path, error_msg in failed_files:
            logger.info(f"  {file_path}: {error_msg}")

    # 保存报告
    report_path = backend_path / "no_untyped_def_fix_report.txt"
    with open(report_path, "w") as f:
        f.write("no-untyped-def错误修复报告\n")
        f.write("=" * 80 + "\n\n")
        f.write(f"总错误数: {len(errors)}\n")
        f.write(f"已修复: {total_fixed}\n")
        f.write(f"剩余: {total_remaining}\n")
        f.write(f"失败文件数: {len(failed_files)}\n\n")

        if failed_files:
            f.write("失败的文件:\n")
            for file_path, error_msg in failed_files:
                f.write(f"  {file_path}: {error_msg}\n")

    logger.info(f"\n报告已保存到: {report_path}")


if __name__ == "__main__":
    main()
