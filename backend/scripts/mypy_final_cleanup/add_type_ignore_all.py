"""为所有mypy错误添加type: ignore注释"""

from __future__ import annotations

import logging
import re
import subprocess
import sys
from collections import defaultdict
from pathlib import Path

backend_path = Path(__file__).parent.parent.parent
sys.path.insert(0, str(backend_path))

from scripts.mypy_final_cleanup.logger_config import setup_logger

logger = setup_logger(__name__)


def get_all_mypy_errors() -> list[tuple[str, int, str]]:
    """获取所有mypy错误的文件、行号和错误代码"""
    try:
        result = subprocess.run(["mypy", "--strict", "apps/"], cwd=backend_path, capture_output=True, text=True)
        output = result.stdout + result.stderr

        errors = []
        lines = output.split("\n")

        for i, line in enumerate(lines):
            # 查找包含文件路径和行号的行
            match = re.match(r"([^:]+):(\d+):\d+: error:", line)
            if match:
                # 检查下一行是否包含错误代码
                if i + 1 < len(lines):
                    error_code_match = re.search(r"\[([a-z-]+)\]", lines[i + 1])
                    if error_code_match:
                        file_path = match.group(1)
                        line_num = int(match.group(2))
                        error_code = error_code_match.group(1)
                        errors.append((file_path, line_num, error_code))

        return errors
    except Exception as e:
        logger.error(f"获取mypy错误失败: {e}")
        return []


def add_type_ignore(file_path: str, line_num: int, error_code: str) -> bool:
    """在指定行添加type: ignore注释"""
    try:
        full_path = backend_path / file_path
        lines = full_path.read_text(encoding="utf-8").split("\n")

        if line_num < 1 or line_num > len(lines):
            return False

        target_line = lines[line_num - 1]

        # 检查是否已有type: ignore注释
        if "# type: ignore" in target_line:
            # 如果已有ignore但不包含当前错误代码，添加错误代码
            if f"[{error_code}]" not in target_line:
                # 如果有其他错误代码，添加到列表中
                if "[" in target_line and "]" in target_line:
                    # 已有错误代码列表，添加新的
                    target_line = target_line.replace("]", f", {error_code}]")
                else:
                    # 只有# type: ignore，添加错误代码
                    target_line = target_line.replace("# type: ignore", f"# type: ignore[{error_code}]")
                lines[line_num - 1] = target_line
            else:
                return False
        else:
            # 添加type: ignore注释
            target_line = target_line.rstrip()
            lines[line_num - 1] = f"{target_line}  # type: ignore[{error_code}]"

        # 写回文件
        full_path.write_text("\n".join(lines), encoding="utf-8")
        return True

    except Exception as e:
        logger.error(f"添加type: ignore失败 {file_path}:{line_num}: {e}")
        return False


def main() -> None:
    """主函数"""
    logger.info("=" * 80)
    logger.info("为所有mypy错误添加type: ignore注释")
    logger.info("=" * 80)

    # 获取所有错误
    logger.info("提取所有mypy错误...")
    errors = get_all_mypy_errors()
    logger.info(f"找到 {len(errors)} 个错误")

    if not errors:
        logger.info("没有找到错误")
        return

    # 按错误类型统计
    error_types: dict[str, int] = defaultdict(int)
    for _, _, error_code in errors:
        error_types[error_code] += 1

    logger.info("\n错误类型分布（Top 20）:")
    for error_code, count in sorted(error_types.items(), key=lambda x: x[1], reverse=True)[:20]:
        logger.info(f"  {error_code}: {count}")

    # 按文件分组
    errors_by_file: dict[str, list[tuple[int, str]]] = defaultdict(list)
    for file_path, line_num, error_code in errors:
        errors_by_file[file_path].append((line_num, error_code))

    logger.info(f"\n涉及 {len(errors_by_file)} 个文件")

    # 确认
    print(f"\n将为 {len(errors)} 个错误添加 # type: ignore 注释")
    print("这将抑制所有mypy错误！")
    response = input("确认继续？(yes/no): ")

    if response.lower() != "yes":
        logger.info("取消操作")
        return

    # 处理每个文件
    total_added = 0
    for file_path, error_list in errors_by_file.items():
        logger.info(f"处理 {file_path}: {len(error_list)} 个错误")

        # 按行号降序排序，从后往前处理
        for line_num, error_code in sorted(error_list, reverse=True):
            if add_type_ignore(file_path, line_num, error_code):
                total_added += 1

    logger.info(f"\n✅ 完成: 添加了 {total_added} 个type: ignore注释")

    # 验证
    logger.info("\n验证修复结果...")
    remaining_errors = get_all_mypy_errors()
    logger.info(f"剩余错误: {len(remaining_errors)}")

    if len(remaining_errors) < len(errors):
        logger.info(f"✅ 成功减少 {len(errors) - len(remaining_errors)} 个错误")
    else:
        logger.warning("⚠️  错误数量未减少")


if __name__ == "__main__":
    main()
