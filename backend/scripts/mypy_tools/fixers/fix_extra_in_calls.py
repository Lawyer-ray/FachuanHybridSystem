#!/usr/bin/env python3
"""修复函数调用中的 extra: Dict[str, Any] = 语法错误

这种语法在函数调用参数中是无效的，应该改为 extra=
但要保留变量定义中的类型注解
"""
from __future__ import annotations

import logging
import re
from pathlib import Path

logging.basicConfig(level=logging.INFO, format="%(message)s")
logger = logging.getLogger(__name__)


def fix_extra_in_calls(content: str) -> tuple[str, int]:
    """修复函数调用中的 extra 参数

    只修复函数调用中的 extra: Dict[str, Any] =，不修复变量定义
    函数调用的特征是前面有 logger.info(, logger.error( 等
    """
    fixes = 0

    # 修复 logger.xxx(..., extra: Dict[str, Any] = {...})
    # 使用更精确的模式，确保是在函数调用中
    pattern = r"(logger\.\w+\([^)]*\n\s+extra):\s*Dict\[str,\s*Any\]\s*="
    matches = list(re.finditer(pattern, content, re.MULTILINE))
    if matches:
        content = re.sub(pattern, r"\1=", content, flags=re.MULTILINE)
        fixes += len(matches)

    return content, fixes


def fix_file(file_path: Path) -> dict[str, int]:
    """修复单个文件"""
    try:
        content = file_path.read_text(encoding="utf-8")
        original = content

        content, fixes = fix_extra_in_calls(content)

        if content != original:
            file_path.write_text(content, encoding="utf-8")
            return {"success": True, "fixes": fixes}

        return {"success": True, "fixes": 0}

    except Exception as e:
        logger.error(f"错误处理文件 {file_path}: {e}")
        return {"success": False, "fixes": 0}


def main() -> None:
    """主函数"""
    backend_path = Path(__file__).parent.parent
    automation_path = backend_path / "apps" / "automation"

    if not automation_path.exists():
        logger.error(f"automation 目录不存在: {automation_path}")
        return

    logger.info("开始修复函数调用中的 extra 参数...")

    total_fixes = 0
    total_files = 0

    # 遍历所有 Python 文件（排除已修复的模块）
    py_files = []
    for py_file in automation_path.rglob("*.py"):
        rel_path = py_file.relative_to(automation_path)
        if any(part in str(rel_path) for part in ["document_delivery", "/sms/", "/scraper/"]):
            continue
        py_files.append(py_file)

    logger.info(f"找到 {len(py_files)} 个 Python 文件\n")

    for py_file in py_files:
        result = fix_file(py_file)
        if result["success"] and result["fixes"] > 0:
            total_files += 1
            total_fixes += result["fixes"]
            rel_path = py_file.relative_to(backend_path)
            logger.info(f"✓ {rel_path}: {result['fixes']} 处修复")

    logger.info(f"\n修复完成:")
    logger.info(f"  修复文件数: {total_files}")
    logger.info(f"  总修复数: {total_fixes}")


if __name__ == "__main__":
    main()
