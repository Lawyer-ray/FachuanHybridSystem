"""提取redundant-cast和unused-ignore错误"""

from __future__ import annotations

import logging
import re
import subprocess
from pathlib import Path

from .error_analyzer import ErrorInfo
from .logger_config import setup_logger

logger = setup_logger(__name__)


def extract_cleanup_errors() -> list[ErrorInfo]:
    """
    运行mypy并提取redundant-cast和unused-ignore错误

    Returns:
        错误信息列表
    """
    logger.info("运行mypy提取cleanup错误...")

    # 运行mypy
    backend_path = Path(__file__).parent.parent.parent
    result = subprocess.run(["mypy", "apps/", "--strict"], cwd=backend_path, capture_output=True, text=True)

    # 合并输出(处理换行)
    output = result.stdout + result.stderr

    # 解析输出
    errors: list[ErrorInfo] = []
    lines = output.split("\n")

    i = 0
    while i < len(lines):
        line = lines[i]

        # 匹配错误行格式: apps/path/file.py:line:col: error: message
        match = re.match(r"^(apps/[^:]+):(\d+)(?::(\d+))?: error: (.+)", line)

        if match:
            file_path = match.group(1)
            line_number = int(match.group(2))
            message = match.group(4)

            # 检查是否包含 redundant-cast 或 unused-ignore
            # 可能在当前行或下一行
            full_message = message
            if i + 1 < len(lines):
                full_message += " " + lines[i + 1]

            if "[redundant-cast]" in full_message:
                errors.append(
                    ErrorInfo(
                        file_path=file_path,
                        line_number=line_number,
                        error_code="redundant-cast",
                        message=message,
                        context="",
                    )
                )
            elif "[unused-ignore]" in full_message:
                errors.append(
                    ErrorInfo(
                        file_path=file_path,
                        line_number=line_number,
                        error_code="unused-ignore",
                        message=message,
                        context="",
                    )
                )

        i += 1

    logger.info(f"提取到 {len(errors)} 个cleanup错误")
    logger.info(f"  - redundant-cast: {sum(1 for e in errors if e.error_code == 'redundant-cast')}")
    logger.info(f"  - unused-ignore: {sum(1 for e in errors if e.error_code == 'unused-ignore')}")

    return errors


def group_errors_by_file(errors: list[ErrorInfo]) -> dict[str, list[ErrorInfo]]:
    """
    按文件分组错误

    Args:
        errors: 错误列表

    Returns:
        文件路径到错误列表的映射
    """
    grouped: dict[str, list[ErrorInfo]] = {}

    for error in errors:
        if error.file_path not in grouped:
            grouped[error.file_path] = []
        grouped[error.file_path].append(error)

    # 按行号排序
    for file_errors in grouped.values():
        file_errors.sort(key=lambda e: e.line_number)

    return grouped


if __name__ == "__main__":
    errors = extract_cleanup_errors()
    grouped = group_errors_by_file(errors)

    print(f"\n总计: {len(errors)} 个错误，分布在 {len(grouped)} 个文件中\n")

    for file_path, file_errors in sorted(grouped.items()):
        print(f"{file_path}: {len(file_errors)} 个错误")
