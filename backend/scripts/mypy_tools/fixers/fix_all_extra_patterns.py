#!/usr/bin/env python3
"""修复所有 extra: Dict[str, Any] = 模式"""
from __future__ import annotations

import logging
import re
from pathlib import Path

logging.basicConfig(level=logging.INFO, format="%(message)s")
logger = logging.getLogger(__name__)


def fix_file(file_path: Path) -> int:
    """修复单个文件"""
    try:
        content = file_path.read_text(encoding="utf-8")
        original = content

        # 修复所有 extra: Dict[str, Any] = 模式
        # 使用正则表达式来匹配所有情况
        pattern = r"extra:\s*Dict\[str,\s*Any\]\s*="
        matches = list(re.finditer(pattern, content))
        fixes = len(matches)

        if fixes > 0:
            content = re.sub(pattern, "extra=", content)
            file_path.write_text(content, encoding="utf-8")
            return fixes

        return 0

    except Exception as e:
        logger.error(f"错误处理文件 {file_path}: {e}")
        return 0


def main() -> None:
    """主函数"""
    backend_path = Path(__file__).parent.parent
    automation_path = backend_path / "apps" / "automation"

    logger.info("开始修复所有 extra: Dict[str, Any] = 模式...")

    total_fixes = 0
    total_files = 0

    # 遍历所有 Python 文件（排除已修复的模块）
    py_files = []
    for py_file in automation_path.rglob("*.py"):
        rel_path = py_file.relative_to(automation_path)
        if any(part in str(rel_path) for part in ["document_delivery", "/sms/", "/scraper/"]):
            continue
        py_files.append(py_file)

    for py_file in py_files:
        fixes = fix_file(py_file)
        if fixes > 0:
            total_files += 1
            total_fixes += fixes
            rel_path = py_file.relative_to(backend_path)
            logger.info(f"✓ {rel_path}: {fixes} 处修复")

    logger.info(f"\n修复完成:")
    logger.info(f"  修复文件数: {total_files}")
    logger.info(f"  总修复数: {total_fixes}")


if __name__ == "__main__":
    main()
