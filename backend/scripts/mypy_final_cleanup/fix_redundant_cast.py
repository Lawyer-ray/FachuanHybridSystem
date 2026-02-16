"""修复redundant-cast错误 - 移除冗余的cast()调用"""

from __future__ import annotations

import logging
import re
import subprocess
import sys
from pathlib import Path

backend_path = Path(__file__).parent.parent.parent
sys.path.insert(0, str(backend_path))

from scripts.mypy_final_cleanup.logger_config import setup_logger

logger = setup_logger(__name__)


def get_redundant_cast_errors() -> list[tuple[str, int]]:
    """获取所有redundant-cast错误"""
    try:
        result = subprocess.run(["mypy", "--strict", "apps/"], cwd=backend_path, capture_output=True, text=True)
        output = result.stdout + result.stderr

        errors = []
        lines = output.split("\n")

        for i, line in enumerate(lines):
            match = re.match(r"([^:]+):(\d+):\d+: error:", line)
            if match:
                if i + 1 < len(lines) and "[redundant-cast]" in lines[i + 1]:
                    file_path = match.group(1)
                    line_num = int(match.group(2))
                    errors.append((file_path, line_num))

        return errors
    except Exception as e:
        logger.error(f"获取错误失败: {e}")
        return []


def remove_redundant_cast(file_path: str, line_num: int) -> bool:
    """移除指定行的冗余cast()"""
    try:
        full_path = backend_path / file_path
        lines = full_path.read_text(encoding="utf-8").split("\n")

        if line_num < 1 or line_num > len(lines):
            return False

        target_line = lines[line_num - 1]
        original_line = target_line

        # 移除cast(type, value)，保留value
        # 匹配模式：cast(Type, expression)
        pattern = r"cast\([^,]+,\s*([^)]+)\)"

        # 替换所有cast调用
        modified_line = re.sub(pattern, r"\1", target_line)

        if modified_line != original_line:
            lines[line_num - 1] = modified_line
            full_path.write_text("\n".join(lines), encoding="utf-8")
            logger.info(f"  修复 {file_path}:{line_num}")
            logger.info(f"    原: {original_line.strip()}")
            logger.info(f"    新: {modified_line.strip()}")
            return True

        return False

    except Exception as e:
        logger.error(f"修复失败 {file_path}:{line_num}: {e}")
        return False


def main() -> None:
    """主函数"""
    logger.info("=" * 80)
    logger.info("修复redundant-cast错误")
    logger.info("=" * 80)

    errors = get_redundant_cast_errors()
    logger.info(f"找到 {len(errors)} 个redundant-cast错误")

    if not errors:
        logger.info("没有找到错误")
        return

    # 按文件分组
    from collections import defaultdict

    errors_by_file: dict[str, list[int]] = defaultdict(list)
    for file_path, line_num in errors:
        errors_by_file[file_path].append(line_num)

    logger.info(f"涉及 {len(errors_by_file)} 个文件\n")

    # 处理每个文件
    total_fixed = 0
    for file_path, line_nums in errors_by_file.items():
        logger.info(f"处理 {file_path}: {len(line_nums)} 个错误")

        # 按行号降序排序
        for line_num in sorted(line_nums, reverse=True):
            if remove_redundant_cast(file_path, line_num):
                total_fixed += 1

    logger.info(f"\n✅ 完成: 修复了 {total_fixed} 个redundant-cast错误")

    # 验证
    logger.info("\n验证修复结果...")
    remaining = get_redundant_cast_errors()
    logger.info(f"剩余redundant-cast错误: {len(remaining)}")


if __name__ == "__main__":
    main()
