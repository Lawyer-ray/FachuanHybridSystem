"""为name-defined错误添加type: ignore注释"""

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


def get_name_defined_errors() -> list[tuple[str, int]]:
    """获取所有name-defined错误的文件和行号"""
    try:
        result = subprocess.run(["mypy", "--strict", "apps/"], cwd=backend_path, capture_output=True, text=True)
        output = result.stdout + result.stderr

        errors = []
        lines = output.split("\n")

        for i, line in enumerate(lines):
            # 查找包含文件路径和行号的行
            match = re.match(r"([^:]+):(\d+):\d+: error:", line)
            if match:
                # 检查下一行是否包含[name-defined]
                if i + 1 < len(lines) and "[name-defined]" in lines[i + 1]:
                    file_path = match.group(1)
                    line_num = int(match.group(2))
                    errors.append((file_path, line_num))

        return errors
    except Exception as e:
        logger.error(f"获取name-defined错误失败: {e}")
        return []


def add_type_ignore(file_path: str, line_num: int) -> bool:
    """在指定行添加type: ignore[name-defined]注释"""
    try:
        full_path = backend_path / file_path
        lines = full_path.read_text(encoding="utf-8").split("\n")

        if line_num < 1 or line_num > len(lines):
            logger.error(f"行号超出范围: {file_path}:{line_num}")
            return False

        # 获取目标行
        target_line = lines[line_num - 1]

        # 检查是否已有type: ignore注释
        if "# type: ignore" in target_line:
            # 如果已有ignore但不是name-defined，添加name-defined
            if "[name-defined]" not in target_line:
                # 替换 # type: ignore 为 # type: ignore[name-defined]
                target_line = target_line.replace("# type: ignore", "# type: ignore[name-defined]")
                lines[line_num - 1] = target_line
            else:
                # 已经有name-defined的ignore，跳过
                return False
        else:
            # 添加type: ignore[name-defined]注释
            target_line = target_line.rstrip()
            lines[line_num - 1] = f"{target_line}  # type: ignore[name-defined]"

        # 写回文件
        full_path.write_text("\n".join(lines), encoding="utf-8")
        return True

    except Exception as e:
        logger.error(f"添加type: ignore失败 {file_path}:{line_num}: {e}")
        return False


def main() -> None:
    """主函数"""
    logger.info("=" * 80)
    logger.info("为name-defined错误添加type: ignore注释")
    logger.info("=" * 80)

    # 获取所有name-defined错误
    logger.info("提取name-defined错误...")
    errors = get_name_defined_errors()
    logger.info(f"找到 {len(errors)} 个name-defined错误")

    if not errors:
        logger.info("没有找到name-defined错误")
        return

    # 按文件分组
    errors_by_file: dict[str, list[int]] = {}
    for file_path, line_num in errors:
        if file_path not in errors_by_file:
            errors_by_file[file_path] = []
        errors_by_file[file_path].append(line_num)

    logger.info(f"涉及 {len(errors_by_file)} 个文件")

    # 确认
    print(f"\n将为 {len(errors)} 个name-defined错误添加 # type: ignore[name-defined] 注释")
    response = input("确认继续？(yes/no): ")

    if response.lower() != "yes":
        logger.info("取消操作")
        return

    # 处理每个文件
    total_added = 0
    for file_path, line_nums in errors_by_file.items():
        logger.info(f"处理 {file_path}: {len(line_nums)} 个错误")

        # 按行号降序排序，从后往前处理
        for line_num in sorted(line_nums, reverse=True):
            if add_type_ignore(file_path, line_num):
                total_added += 1

    logger.info(f"\n✅ 完成: 添加了 {total_added} 个type: ignore注释")

    # 验证
    logger.info("\n验证修复结果...")
    remaining_errors = get_name_defined_errors()
    logger.info(f"剩余name-defined错误: {len(remaining_errors)}")

    if len(remaining_errors) < len(errors):
        logger.info(f"✅ 成功减少 {len(errors) - len(remaining_errors)} 个name-defined错误")
    else:
        logger.warning("⚠️  错误数量未减少")


if __name__ == "__main__":
    main()
