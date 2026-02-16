"""为字典变量添加类型注解"""

from __future__ import annotations

import logging
import re
from pathlib import Path

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


def fix_dict_annotations(file_path: Path) -> int:
    """为需要类型注解的字典变量添加注解"""

    content = file_path.read_text(encoding="utf-8")
    lines = content.split("\n")

    modified = False
    fixed_count = 0

    for i in range(len(lines)):
        line = lines[i]

        # 查找 result = { 或 data = { 等模式
        # 匹配: 变量名 = {
        match = re.match(r"^(\s+)(result|data|config|info|response|params|options|settings|context)\s*=\s*\{", line)
        if match:
            indent = match.group(1)
            var_name = match.group(2)

            # 检查是否已有类型注解
            if ":" not in line.split("=")[0]:
                # 添加类型注解
                lines[i] = f"{indent}{var_name}: Dict[str, Any] = {{"
                modified = True
                fixed_count += 1
                logger.info(f"  添加类型注解: {var_name}")

    if modified:
        file_path.write_text("\n".join(lines), encoding="utf-8")

    return fixed_count


def main() -> None:
    backend_path = Path(__file__).parent.parent.parent

    logger.info("=" * 60)
    logger.info("为字典变量添加类型注解")
    logger.info("=" * 60)

    total_fixed = 0

    # 只处理有"object" has no attribute错误的文件
    files_to_fix = [
        "apps/core/config/environment.py",
        "apps/core/config/migrator.py",
        "apps/core/config/migration_tracker.py",
    ]

    for file_path_str in files_to_fix:
        file_path = backend_path / file_path_str
        if file_path.exists():
            logger.info(f"\n处理 {file_path_str}")
            fixed = fix_dict_annotations(file_path)
            total_fixed += fixed

    logger.info("\n" + "=" * 60)
    logger.info(f"修复完成,共添加{total_fixed}个类型注解")
    logger.info("=" * 60)


if __name__ == "__main__":
    main()
