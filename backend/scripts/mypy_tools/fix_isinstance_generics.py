"""修复isinstance中使用泛型类型的问题"""

from __future__ import annotations

import logging
import re
from pathlib import Path

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


def fix_isinstance_generics(file_path: Path) -> int:
    """修复文件中isinstance使用泛型的问题"""

    content = file_path.read_text(encoding="utf-8")
    original = content

    # 修复 isinstance(x, dict[...]) -> isinstance(x, dict)
    content = re.sub(r"isinstance\(([^,]+),\s*dict\[[^\]]+\]\)", r"isinstance(\1, dict)", content)

    # 修复 isinstance(x, list[...]) -> isinstance(x, list)
    content = re.sub(r"isinstance\(([^,]+),\s*list\[[^\]]+\]\)", r"isinstance(\1, list)", content)

    # 修复 isinstance(x, set[...]) -> isinstance(x, set)
    content = re.sub(r"isinstance\(([^,]+),\s*set\[[^\]]+\]\)", r"isinstance(\1, set)", content)

    # 修复 isinstance(x, tuple[...]) -> isinstance(x, tuple)
    content = re.sub(r"isinstance\(([^,]+),\s*tuple\[[^\]]+\]\)", r"isinstance(\1, tuple)", content)

    if content != original:
        file_path.write_text(content, encoding="utf-8")
        # 统计修复数量
        count = (
            len(re.findall(r"isinstance\([^,]+,\s*dict\[[^\]]+\]\)", original))
            + len(re.findall(r"isinstance\([^,]+,\s*list\[[^\]]+\]\)", original))
            + len(re.findall(r"isinstance\([^,]+,\s*set\[[^\]]+\]\)", original))
            + len(re.findall(r"isinstance\([^,]+,\s*tuple\[[^\]]+\]\)", original))
        )
        logger.info(f"修复 {file_path.relative_to(file_path.parent.parent.parent)}: {count}处")
        return count

    return 0


def main() -> None:
    backend_path = Path(__file__).parent.parent.parent

    logger.info("=" * 60)
    logger.info("修复isinstance中的泛型类型")
    logger.info("=" * 60)

    total_fixed = 0

    # 查找所有Python文件
    for py_file in backend_path.glob("apps/**/*.py"):
        fixed = fix_isinstance_generics(py_file)
        total_fixed += fixed

    logger.info("=" * 60)
    logger.info(f"修复完成,共修复{total_fixed}处")
    logger.info("=" * 60)


if __name__ == "__main__":
    main()
