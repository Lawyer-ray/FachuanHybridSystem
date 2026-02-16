"""修复错误插入的 id: int 注解"""

from __future__ import annotations

import logging
import re
from pathlib import Path

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")

logger = logging.getLogger(__name__)


def fix_file(file_path: Path) -> bool:
    """修复单个文件中错误插入的 id: int 注解"""
    try:
        content = file_path.read_text(encoding="utf-8")
        original_content = content

        # 模式1: 修复在 ForeignKey 等字段定义中间插入的 id: int
        # 例如: field = models.ForeignKey(\n    id: int\n        Model, ...
        pattern1 = re.compile(r"(\s+\w+\s*=\s*models\.\w+\()\n(\s+)id: int\n(\s+)", re.MULTILINE)
        content = pattern1.sub(r"\1\n\3", content)

        # 模式2: 修复重复的 id: int
        # 例如: id: int\n    id: int
        pattern2 = re.compile(r"(\s+id: int)\n\s+id: int", re.MULTILINE)
        content = pattern2.sub(r"\1", content)

        # 模式3: 修复在类定义后错误位置的 id: int
        # 例如: class Foo:\n    id: int\n    CONSTANT = "value"
        # 应该移到类体开头
        pattern3 = re.compile(r"(class \w+\([^)]+\):)\n(\s+)id: int\n(\s+)([A-Z_]+\s*=)", re.MULTILINE)

        def move_id_annotation(match: re.Match[str]) -> str:
            class_def = match.group(1)
            indent = match.group(2)
            constant_indent = match.group(3)
            constant = match.group(4)
            return f"{class_def}\n{indent}id: int\n{constant_indent}{constant}"

        content = pattern3.sub(move_id_annotation, content)

        # 模式4: 修复在字段定义后面的 id: int
        # 例如: field = models.CharField(...)\n    id: int\n    other_field = ...
        pattern4 = re.compile(r"(\s+\w+\s*=\s*models\.\w+\([^)]+\))\n(\s+)id: int\n(\s+)(\w+\s*[=:])", re.MULTILINE)
        content = pattern4.sub(r"\1\n\3\4", content)

        if content != original_content:
            file_path.write_text(content, encoding="utf-8")
            logger.info(f"修复文件: {file_path}")
            return True

        return False

    except Exception as e:
        logger.error(f"处理文件失败 {file_path}: {e}")
        return False


def main() -> None:
    """主函数"""
    backend_path = Path(__file__).parent.parent
    apps_dir = backend_path / "apps"

    if not apps_dir.exists():
        logger.error(f"apps目录不存在: {apps_dir}")
        return

    logger.info("开始修复错误插入的 id: int 注解...")

    fixed_count = 0
    total_count = 0

    for py_file in apps_dir.rglob("*.py"):
        total_count += 1
        if fix_file(py_file):
            fixed_count += 1

    logger.info(f"修复完成: 检查了 {total_count} 个文件，修复了 {fixed_count} 个文件")


if __name__ == "__main__":
    main()
