#!/usr/bin/env python3
"""修复剩余的no-untyped-def错误"""

from __future__ import annotations

import ast
import logging
import re
import subprocess
from pathlib import Path

logging.basicConfig(level=logging.INFO, format="%(message)s")
logger = logging.getLogger(__name__)


def get_remaining_errors() -> list[tuple[str, int, str]]:
    """获取剩余的no-untyped-def错误"""
    result = subprocess.run(
        ["python", "-m", "mypy", "apps/", "--strict", "--no-pretty", "--no-error-summary"],
        capture_output=True,
        text=True,
        cwd=Path(__file__).parent.parent,
    )

    output = result.stdout + result.stderr
    errors = []

    pattern = re.compile(r"^(apps/[^:]+):(\d+):\d+:\s+error:\s+(.+?)\s+\[no-untyped-def\]")

    for line in output.split("\n"):
        match = pattern.match(line)
        if match:
            file_path, line_no, message = match.groups()
            errors.append((file_path, int(line_no), message))

    return errors


def fix_file(file_path: str, line_numbers: list[int]) -> bool:
    """修复文件中的错误"""
    full_path = Path(__file__).parent.parent / file_path

    if not full_path.exists():
        logger.warning(f"文件不存在: {file_path}")
        return False

    content = full_path.read_text()
    lines = content.split("\n")

    # 确保导入了Any
    has_any_import = False
    typing_import_line = -1

    for i, line in enumerate(lines):
        if "from typing import" in line:
            typing_import_line = i
            if "Any" in line:
                has_any_import = True
            break

    if not has_any_import:
        if typing_import_line >= 0:
            # 在现有的typing导入中添加Any
            lines[typing_import_line] = lines[typing_import_line].replace(
                "from typing import", "from typing import Any,"
            )
        else:
            # 找到第一个import后添加
            for i, line in enumerate(lines):
                if line.startswith("import ") or line.startswith("from "):
                    lines.insert(i + 1, "from typing import Any")
                    # 调整行号
                    line_numbers = [ln + 1 if ln > i else ln for ln in line_numbers]
                    break

    modified = False

    for line_no in sorted(line_numbers, reverse=True):
        if line_no > len(lines):
            continue

        line_idx = line_no - 1
        line = lines[line_idx]

        # 修复**kwargs
        if "**kwargs" in line and "**kwargs: Any" not in line:
            lines[line_idx] = line.replace("**kwargs", "**kwargs: Any")
            modified = True
            logger.info(f"  修复 {file_path}:{line_no} - 添加**kwargs类型注解")

        # 修复**options (Django commands)
        elif "**options" in line and "**options: Any" not in line:
            lines[line_idx] = line.replace("**options", "**options: Any")
            modified = True
            logger.info(f"  修复 {file_path}:{line_no} - 添加**options类型注解")

        # 修复*args
        elif "*args" in line and "*args: Any" not in line and "**" not in line:
            lines[line_idx] = line.replace("*args", "*args: Any")
            modified = True
            logger.info(f"  修复 {file_path}:{line_no} - 添加*args类型注解")

    if modified:
        full_path.write_text("\n".join(lines))
        return True

    return False


def main() -> None:
    """主函数"""
    logger.info("获取剩余的no-untyped-def错误...")
    errors = get_remaining_errors()

    logger.info(f"找到 {len(errors)} 个错误")

    # 按文件分组
    by_file: dict[str, list[int]] = {}
    for file_path, line_no, message in errors:
        if file_path not in by_file:
            by_file[file_path] = []
        by_file[file_path].append(line_no)

    logger.info(f"涉及 {len(by_file)} 个文件\n")

    # 修复每个文件
    fixed_count = 0
    for file_path, line_numbers in by_file.items():
        logger.info(f"修复 {file_path} ({len(line_numbers)} 个错误)...")
        if fix_file(file_path, line_numbers):
            fixed_count += 1

    logger.info(f"\n修复了 {fixed_count} 个文件")

    # 再次检查
    logger.info("\n再次检查...")
    remaining = get_remaining_errors()
    logger.info(f"剩余 {len(remaining)} 个no-untyped-def错误")


if __name__ == "__main__":
    main()
