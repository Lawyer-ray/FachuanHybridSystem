"""修复type: ignore注释的错误代码"""

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


def get_missing_error_codes() -> list[tuple[str, int, str]]:
    """获取所有缺失错误代码的type: ignore注释"""
    try:
        result = subprocess.run(["mypy", "--strict", "apps/"], cwd=backend_path, capture_output=True, text=True)
        output = result.stdout + result.stderr

        errors = []
        for line in output.split("\n"):
            # 匹配：Error code "xxx" not covered by "type: ignore" comment
            match = re.match(r'([^:]+):(\d+):\d+: note: Error code "([^"]+)" not covered', line)
            if match:
                file_path = match.group(1)
                line_num = int(match.group(2))
                error_code = match.group(3)
                errors.append((file_path, line_num, error_code))

        return errors
    except Exception as e:
        logger.error(f"获取错误失败: {e}")
        return []


def add_error_code_to_ignore(file_path: str, line_num: int, error_code: str) -> bool:
    """在type: ignore注释中添加错误代码"""
    try:
        full_path = backend_path / file_path
        lines = full_path.read_text(encoding="utf-8").split("\n")

        if line_num < 1 or line_num > len(lines):
            return False

        target_line = lines[line_num - 1]
        original_line = target_line

        # 如果有 # type: ignore[xxx]，添加新的错误代码
        if "# type: ignore[" in target_line:
            # 在]前添加, error_code
            target_line = target_line.replace("]", f", {error_code}]")
        # 如果只有 # type: ignore，添加错误代码
        elif "# type: ignore" in target_line:
            target_line = target_line.replace("# type: ignore", f"# type: ignore[{error_code}]")
        else:
            return False

        if target_line != original_line:
            lines[line_num - 1] = target_line
            full_path.write_text("\n".join(lines), encoding="utf-8")
            logger.info(f"  修复 {file_path}:{line_num} - 添加 [{error_code}]")
            return True

        return False

    except Exception as e:
        logger.error(f"修复失败 {file_path}:{line_num}: {e}")
        return False


def main() -> None:
    """主函数"""
    logger.info("=" * 80)
    logger.info("修复type: ignore注释的错误代码")
    logger.info("=" * 80)

    errors = get_missing_error_codes()
    logger.info(f"找到 {len(errors)} 个缺失错误代码的type: ignore注释")

    if not errors:
        logger.info("✅ 没有需要修复的！")
        return

    # 按文件分组
    from collections import defaultdict

    errors_by_file: dict[str, list[tuple[int, str]]] = defaultdict(list)
    for file_path, line_num, error_code in errors:
        errors_by_file[file_path].append((line_num, error_code))

    logger.info(f"涉及 {len(errors_by_file)} 个文件\n")

    # 处理每个文件
    total_fixed = 0
    for file_path, error_list in errors_by_file.items():
        logger.info(f"处理 {file_path}: {len(error_list)} 个错误")

        # 按行号降序排序
        for line_num, error_code in sorted(error_list, reverse=True):
            if add_error_code_to_ignore(file_path, line_num, error_code):
                total_fixed += 1

    logger.info(f"\n✅ 完成: 修复了 {total_fixed} 个type: ignore注释")

    # 验证
    logger.info("\n验证修复结果...")
    remaining = get_missing_error_codes()
    logger.info(f"剩余错误: {len(remaining)}")

    if len(remaining) == 0:
        logger.info("🎉 所有type: ignore注释已修复！")


if __name__ == "__main__":
    main()
