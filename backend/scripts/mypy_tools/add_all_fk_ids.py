"""扫描所有Django Model并添加缺失的外键_id字段注解"""

from __future__ import annotations

import logging
import re
from pathlib import Path

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


def process_model_file(file_path: Path) -> int:
    """处理一个models.py文件,添加缺失的外键_id注解"""

    content = file_path.read_text(encoding="utf-8")
    lines = content.split("\n")

    modified = False
    added_count = 0
    i = 0

    while i < len(lines):
        line = lines[i]

        # 查找Model类定义
        if re.match(r"\s*class\s+\w+\s*\(.*Model.*\):", line):
            class_match = re.match(r"(\s*)class\s+(\w+)", line)
            if class_match:
                indent = class_match.group(1)
                class_name = class_match.group(2)

                # 跳过docstring和id字段
                j = i + 1
                while j < len(lines):
                    stripped = lines[j].strip()
                    if stripped.startswith('"""') or stripped.startswith("'''"):
                        j += 1
                        # 跳过整个docstring
                        while j < len(lines) and ('"""' not in lines[j] and "'''" not in lines[j]):
                            j += 1
                        j += 1
                    elif stripped.startswith("id:") or stripped == "":
                        j += 1
                    else:
                        break

                # 收集所有ForeignKey字段
                fk_fields: list[str] = []
                k = j
                while k < len(lines):
                    # 如果遇到下一个类定义,停止
                    if re.match(r"\s*class\s+\w+", lines[k]) and k > i:
                        break

                    # 查找ForeignKey定义
                    if "models.ForeignKey" in lines[k] or "ForeignKey(" in lines[k]:
                        # 向前查找字段名
                        for m in range(max(j, k - 3), k + 1):
                            field_match = re.match(r"\s*(\w+)\s*=\s*models\.ForeignKey", lines[m])
                            if field_match:
                                field_name = field_match.group(1)
                                fk_fields.append(field_name)
                                break

                    k += 1

                # 检查哪些外键缺少_id注解
                for field_name in fk_fields:
                    fk_id_name = f"{field_name}_id"

                    # 检查是否已有_id注解
                    has_annotation = False
                    for m in range(j, k):
                        if f"{fk_id_name}:" in lines[m] or f"{fk_id_name} :" in lines[m]:
                            has_annotation = True
                            break

                    if not has_annotation:
                        # 添加_id注解
                        lines.insert(j, f"{indent}    {fk_id_name}: int  # 外键ID字段")
                        j += 1
                        k += 1
                        modified = True
                        added_count += 1
                        logger.info(f"  添加 {class_name}.{fk_id_name}")

        i += 1

    if modified:
        file_path.write_text("\n".join(lines), encoding="utf-8")

    return added_count


def main() -> None:
    backend_path = Path(__file__).parent.parent.parent

    logger.info("=" * 60)
    logger.info("扫描所有Model并添加缺失的外键_id注解")
    logger.info("=" * 60)

    total_added = 0

    # 查找所有models.py文件
    for model_file in backend_path.glob("apps/**/models.py"):
        logger.info(f"\n处理 {model_file.relative_to(backend_path)}")
        added = process_model_file(model_file)
        total_added += added

    # 也处理models目录下的文件
    for model_file in backend_path.glob("apps/**/models/*.py"):
        if model_file.name != "__init__.py":
            logger.info(f"\n处理 {model_file.relative_to(backend_path)}")
            added = process_model_file(model_file)
            total_added += added

    logger.info("\n" + "=" * 60)
    logger.info(f"完成,共添加{total_added}个外键_id注解")
    logger.info("=" * 60)


if __name__ == "__main__":
    main()
