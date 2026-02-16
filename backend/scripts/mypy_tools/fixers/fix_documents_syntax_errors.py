#!/usr/bin/env python3
"""修复 documents 模块的语法错误

修复内容：
1. 错误地在 if/for/while 语句中添加的 -> None

Requirements: 3.2
"""
from __future__ import annotations

import logging
import re
from pathlib import Path

logging.basicConfig(level=logging.INFO, format="%(message)s")
logger = logging.getLogger(__name__)


def fix_syntax_errors(content: str) -> tuple[str, int]:
    """修复语法错误"""
    fixes = 0

    # 修复 -> type -> None: (property 或其他返回类型错误)
    pattern = r"(\s*->\s*\w+)\s*->\s*None\s*:"
    matches = list(re.finditer(pattern, content))
    if matches:
        content = re.sub(pattern, r"\1:", content)
        fixes += len(matches)

    # 修复重复的 -> None -> None:
    pattern = r"(\s*->\s*None)\s*->\s*None\s*:"
    matches = list(re.finditer(pattern, content))
    if matches:
        content = re.sub(pattern, r"\1:", content)
        fixes += len(matches)

    # 修复 class ... -> None:
    pattern = r"(^class\s+\w+(?:\([^)]*\))?)\s*->\s*None\s*:"
    matches = list(re.finditer(pattern, content, re.MULTILINE))
    if matches:
        content = re.sub(pattern, r"\1:", content, flags=re.MULTILINE)
        fixes += len(matches)

    # 修复 try -> None:
    pattern = r"(\s+try)\s*->\s*None\s*:"
    matches = list(re.finditer(pattern, content))
    if matches:
        content = re.sub(pattern, r"\1:", content)
        fixes += len(matches)

    # 修复 except ... -> None:
    pattern = r"(\s+except[^:]*)\s*->\s*None\s*:"
    matches = list(re.finditer(pattern, content))
    if matches:
        content = re.sub(pattern, r"\1:", content)
        fixes += len(matches)

    # 修复 finally -> None:
    pattern = r"(\s+finally)\s*->\s*None\s*:"
    matches = list(re.finditer(pattern, content))
    if matches:
        content = re.sub(pattern, r"\1:", content)
        fixes += len(matches)

    # 修复 if ... -> None:
    pattern = r"(\s+if\s+[^:]+)\s*->\s*None\s*:"
    matches = list(re.finditer(pattern, content))
    if matches:
        content = re.sub(pattern, r"\1:", content)
        fixes += len(matches)

    # 修复 for ... in ... -> None:
    pattern = r"(\s+for\s+\w+\s+in\s+[^:]+)\s*->\s*None\s*:"
    matches = list(re.finditer(pattern, content))
    if matches:
        content = re.sub(pattern, r"\1:", content)
        fixes += len(matches)

    # 修复 while ... -> None:
    pattern = r"(\s+while\s+[^:]+)\s*->\s*None\s*:"
    matches = list(re.finditer(pattern, content))
    if matches:
        content = re.sub(pattern, r"\1:", content)
        fixes += len(matches)

    # 修复 elif ... -> None:
    pattern = r"(\s+elif\s+[^:]+)\s*->\s*None\s*:"
    matches = list(re.finditer(pattern, content))
    if matches:
        content = re.sub(pattern, r"\1:", content)
        fixes += len(matches)

    # 修复 with ... -> None:
    pattern = r"(\s+with\s+[^:]+)\s*->\s*None\s*:"
    matches = list(re.finditer(pattern, content))
    if matches:
        content = re.sub(pattern, r"\1:", content)
        fixes += len(matches)

    # 修复 else -> None:
    pattern = r"(\s+else)\s*->\s*None\s*:"
    matches = list(re.finditer(pattern, content))
    if matches:
        content = re.sub(pattern, r"\1:", content)
        fixes += len(matches)

    return content, fixes


def fix_file(file_path: Path) -> dict[str, int]:
    """修复单个文件"""
    try:
        content = file_path.read_text(encoding="utf-8")
        original = content

        content, fixes = fix_syntax_errors(content)

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
    documents_path = backend_path / "apps" / "documents"

    if not documents_path.exists():
        logger.error(f"documents 目录不存在: {documents_path}")
        return

    logger.info("开始修复 documents 模块语法错误...")
    logger.info(f"扫描目录: {documents_path}")

    total_fixes = 0
    fixed_files = 0

    # 遍历所有 Python 文件
    py_files = list(documents_path.rglob("*.py"))
    logger.info(f"找到 {len(py_files)} 个 Python 文件\n")

    for py_file in py_files:
        result = fix_file(py_file)
        if result["success"] and result["fixes"] > 0:
            fixed_files += 1
            total_fixes += result["fixes"]

            rel_path = py_file.relative_to(backend_path)
            logger.info(f"✓ {rel_path} - 修复 {result['fixes']} 个语法错误")

    logger.info(f"\n修复完成:")
    logger.info(f"  修复文件数: {fixed_files}")
    logger.info(f"  总修复数: {total_fixes}")


if __name__ == "__main__":
    main()
