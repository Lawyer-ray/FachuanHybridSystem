#!/usr/bin/env python3
"""为Django Model添加id属性注解 - 简单文本方式"""

from __future__ import annotations

import logging
import re
from pathlib import Path

# 配置日志
logging.basicConfig(level=logging.INFO, format="%(message)s")
logger = logging.getLogger(__name__)


def add_id_to_model_file(file_path: Path) -> int:
    """
    为文件中的Django Model类添加id属性注解

    Returns:
        添加的注解数量
    """
    with open(file_path, "r", encoding="utf-8") as f:
        lines = f.readlines()

    new_lines = []
    added_count = 0
    i = 0

    while i < len(lines):
        line = lines[i]
        new_lines.append(line)

        # 检查是否是Model类定义
        class_match = re.match(r"^class\s+(\w+)\s*\([^)]*models\.Model[^)]*\):", line)
        if class_match:
            class_name = class_match.group(1)

            # 跳过docstring
            i += 1
            if i < len(lines):
                next_line = lines[i]
                new_lines.append(next_line)

                # 如果是docstring，继续跳过
                if '"""' in next_line or "'''" in next_line:
                    # 多行docstring
                    if next_line.count('"""') == 1 or next_line.count("'''") == 1:
                        i += 1
                        while i < len(lines):
                            new_lines.append(lines[i])
                            if '"""' in lines[i] or "'''" in lines[i]:
                                break
                            i += 1

                # 检查下一行是否已有id注解
                i += 1
                if i < len(lines):
                    next_line = lines[i]

                    # 跳过空行
                    while i < len(lines) and lines[i].strip() == "":
                        new_lines.append(lines[i])
                        i += 1
                        if i < len(lines):
                            next_line = lines[i]

                    # 检查是否已有id注解
                    if i < len(lines) and not re.match(r"\s+id:\s*int", next_line):
                        # 添加id注解
                        indent = "    "  # 4个空格缩进
                        new_lines.append(f"{indent}id: int\n")
                        logger.info(f"  为类 {class_name} 添加id注解")
                        added_count += 1

                    # 继续处理当前行
                    continue

        i += 1

    if added_count > 0:
        with open(file_path, "w", encoding="utf-8") as f:
            f.writelines(new_lines)

    return added_count


def main() -> None:
    """主函数"""
    backend_path = Path(__file__).parent.parent
    apps_dir = backend_path / "apps"

    logger.info("=" * 80)
    logger.info("开始为Django Model添加id属性注解")
    logger.info("=" * 80)

    # 查找所有models.py文件和models目录下的Python文件
    models_files = list(apps_dir.rglob("models.py"))
    models_files.extend(apps_dir.rglob("models/*.py"))
    # 排除__init__.py
    models_files = [f for f in models_files if f.name != "__init__.py"]
    logger.info(f"\n找到 {len(models_files)} 个model文件\n")

    total_added = 0
    modified_files = 0

    for models_file in models_files:
        rel_path = models_file.relative_to(backend_path)
        logger.info(f"处理: {rel_path}")

        added = add_id_to_model_file(models_file)
        if added > 0:
            total_added += added
            modified_files += 1

    logger.info("\n" + "=" * 80)
    logger.info(f"完成！修改了 {modified_files} 个文件，添加了 {total_added} 个id注解")
    logger.info("=" * 80)


if __name__ == "__main__":
    main()
