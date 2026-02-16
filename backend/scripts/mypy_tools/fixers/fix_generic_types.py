#!/usr/bin/env python3
"""批量修复泛型类型参数缺失的错误

修复内容：
1. dict -> dict[str, Any]
2. list -> list[Any]
3. set -> set[Any]
4. tuple -> tuple[Any, ...]
5. 自动添加 from typing import Any 导入

Requirements: 2.1, 2.2
"""
from __future__ import annotations

import logging
import re
from pathlib import Path
from typing import Any

logging.basicConfig(level=logging.INFO, format="%(message)s")
logger = logging.getLogger(__name__)


def fix_generic_types(content: str) -> tuple[str, dict[str, int]]:
    """修复泛型类型参数缺失

    Returns:
        (修复后的内容, 修复统计)
    """
    stats = {
        "dict": 0,
        "list": 0,
        "set": 0,
        "tuple": 0,
    }

    # 修复 -> dict (返回类型) - 确保后面没有 [
    pattern = r"(\s+->)\s+dict(?!\[)(\s*[:\n])"
    matches = list(re.finditer(pattern, content))
    if matches:
        content = re.sub(pattern, r"\1 dict[str, Any]\2", content)
        stats["dict"] += len(matches)

    # 修复 -> list (返回类型) - 确保后面没有 [
    pattern = r"(\s+->)\s+list(?!\[)(\s*[:\n])"
    matches = list(re.finditer(pattern, content))
    if matches:
        content = re.sub(pattern, r"\1 list[Any]\2", content)
        stats["list"] += len(matches)

    # 修复 -> set (返回类型) - 确保后面没有 [
    pattern = r"(\s+->)\s+set(?!\[)(\s*[:\n])"
    matches = list(re.finditer(pattern, content))
    if matches:
        content = re.sub(pattern, r"\1 set[Any]\2", content)
        stats["set"] += len(matches)

    # 修复 -> tuple (返回类型) - 确保后面没有 [
    pattern = r"(\s+->)\s+tuple(?!\[)(\s*[:\n])"
    matches = list(re.finditer(pattern, content))
    if matches:
        content = re.sub(pattern, r"\1 tuple[Any, ...]\2", content)
        stats["tuple"] += len(matches)

    # 修复参数类型 : dict = - 确保后面没有 [
    pattern = r"(\w+):\s+dict(?!\[)\s*="
    matches = list(re.finditer(pattern, content))
    if matches:
        content = re.sub(pattern, r"\1: dict[str, Any] =", content)
        stats["dict"] += len(matches)

    # 修复参数类型 : list = - 确保后面没有 [
    pattern = r"(\w+):\s+list(?!\[)\s*="
    matches = list(re.finditer(pattern, content))
    if matches:
        content = re.sub(pattern, r"\1: list[Any] =", content)
        stats["list"] += len(matches)

    # 修复参数类型 : set = - 确保后面没有 [
    pattern = r"(\w+):\s+set(?!\[)\s*="
    matches = list(re.finditer(pattern, content))
    if matches:
        content = re.sub(pattern, r"\1: set[Any] =", content)
        stats["set"] += len(matches)

    # 修复参数类型 : tuple = - 确保后面没有 [
    pattern = r"(\w+):\s+tuple(?!\[)\s*="
    matches = list(re.finditer(pattern, content))
    if matches:
        content = re.sub(pattern, r"\1: tuple[Any, ...] =", content)
        stats["tuple"] += len(matches)

    # 修复参数类型 : dict, - 确保后面没有 [
    pattern = r"(\w+):\s+dict(?!\[)\s*,"
    matches = list(re.finditer(pattern, content))
    if matches:
        content = re.sub(pattern, r"\1: dict[str, Any],", content)
        stats["dict"] += len(matches)

    # 修复参数类型 : list, - 确保后面没有 [
    pattern = r"(\w+):\s+list(?!\[)\s*,"
    matches = list(re.finditer(pattern, content))
    if matches:
        content = re.sub(pattern, r"\1: list[Any],", content)
        stats["list"] += len(matches)

    # 修复参数类型 : set, - 确保后面没有 [
    pattern = r"(\w+):\s+set(?!\[)\s*,"
    matches = list(re.finditer(pattern, content))
    if matches:
        content = re.sub(pattern, r"\1: set[Any],", content)
        stats["set"] += len(matches)

    # 修复参数类型 : tuple, - 确保后面没有 [
    pattern = r"(\w+):\s+tuple(?!\[)\s*,"
    matches = list(re.finditer(pattern, content))
    if matches:
        content = re.sub(pattern, r"\1: tuple[Any, ...],", content)
        stats["tuple"] += len(matches)

    # 修复参数类型 : dict) - 确保后面没有 [
    pattern = r"(\w+):\s+dict(?!\[)\s*\)"
    matches = list(re.finditer(pattern, content))
    if matches:
        content = re.sub(pattern, r"\1: dict[str, Any])", content)
        stats["dict"] += len(matches)

    # 修复参数类型 : list) - 确保后面没有 [
    pattern = r"(\w+):\s+list(?!\[)\s*\)"
    matches = list(re.finditer(pattern, content))
    if matches:
        content = re.sub(pattern, r"\1: list[Any])", content)
        stats["list"] += len(matches)

    # 修复参数类型 : set) - 确保后面没有 [
    pattern = r"(\w+):\s+set(?!\[)\s*\)"
    matches = list(re.finditer(pattern, content))
    if matches:
        content = re.sub(pattern, r"\1: set[Any])", content)
        stats["set"] += len(matches)

    # 修复参数类型 : tuple) - 确保后面没有 [
    pattern = r"(\w+):\s+tuple(?!\[)\s*\)"
    matches = list(re.finditer(pattern, content))
    if matches:
        content = re.sub(pattern, r"\1: tuple[Any, ...])", content)
        stats["tuple"] += len(matches)

    return content, stats


def ensure_typing_imports(content: str) -> str:
    """确保导入了 Any 类型"""
    # 检查是否需要 Any
    needs_any = "[Any]" in content or "[str, Any]" in content or "[Any, ...]" in content

    if not needs_any:
        return content

    # 检查是否已经导入了 Any
    if re.search(r"from typing import.*\bAny\b", content):
        return content

    lines = content.split("\n")

    # 查找 from typing import 行
    typing_import_idx = -1
    for i, line in enumerate(lines):
        if line.startswith("from typing import"):
            typing_import_idx = i
            break

    if typing_import_idx >= 0:
        # 在现有导入中添加 Any
        line = lines[typing_import_idx]

        # 处理多行导入（括号）
        if "(" in line:
            # 查找右括号
            for j in range(typing_import_idx, len(lines)):
                if ")" in lines[j]:
                    # 在右括号前添加 Any
                    lines[j] = lines[j].replace(")", ", Any)")
                    break
        else:
            # 单行导入，直接添加
            lines[typing_import_idx] = line.rstrip() + ", Any"
    else:
        # 添加新的导入行
        # 查找合适的插入位置（在 from __future__ 之后，或第一个 import 之前）
        insert_idx = 0
        for i, line in enumerate(lines):
            if line.startswith("from __future__"):
                insert_idx = i + 1
                # 跳过空行
                while insert_idx < len(lines) and not lines[insert_idx].strip():
                    insert_idx += 1
                break
            elif line.startswith("import ") or line.startswith("from "):
                insert_idx = i
                break

        lines.insert(insert_idx, "from typing import Any")
        # 添加空行分隔
        if insert_idx + 1 < len(lines) and lines[insert_idx + 1].strip():
            lines.insert(insert_idx + 1, "")

    return "\n".join(lines)


def fix_file(file_path: Path) -> dict[str, Any]:
    """修复单个文件

    Returns:
        修复结果字典
    """
    try:
        content = file_path.read_text(encoding="utf-8")
        original = content

        # 修复泛型类型
        content, stats = fix_generic_types(content)

        # 确保导入 Any
        if sum(stats.values()) > 0:
            content = ensure_typing_imports(content)

        # 只有在有修改时才写入
        if content != original:
            file_path.write_text(content, encoding="utf-8")
            return {"success": True, "modified": True, "stats": stats}

        return {"success": True, "modified": False, "stats": stats}

    except Exception as e:
        logger.error(f"错误处理文件 {file_path}: {e}")
        return {"success": False, "modified": False, "error": str(e)}


def main() -> None:
    """主函数"""
    backend_path = Path(__file__).parent.parent
    apps_path = backend_path / "apps"

    if not apps_path.exists():
        logger.error(f"apps 目录不存在: {apps_path}")
        return

    logger.info("开始批量修复泛型类型参数缺失错误...")
    logger.info(f"扫描目录: {apps_path}\n")

    total_stats = {
        "files": 0,
        "dict": 0,
        "list": 0,
        "set": 0,
        "tuple": 0,
    }

    # 遍历所有 Python 文件
    py_files = list(apps_path.rglob("*.py"))
    logger.info(f"找到 {len(py_files)} 个 Python 文件\n")

    for py_file in py_files:
        # 跳过 __init__.py 和 migrations
        if py_file.name == "__init__.py" or "migrations" in py_file.parts:
            continue

        result = fix_file(py_file)
        if result["success"] and result["modified"]:
            stats = result["stats"]
            total_stats["files"] += 1
            total_stats["dict"] += stats["dict"]
            total_stats["list"] += stats["list"]
            total_stats["set"] += stats["set"]
            total_stats["tuple"] += stats["tuple"]

            rel_path = py_file.relative_to(backend_path)
            logger.info(f"✓ {rel_path}")
            if any(stats.values()):
                fixes = [f"{k}: {v}" for k, v in stats.items() if v > 0]
                logger.info(f"  {', '.join(fixes)}")

    logger.info(f"\n修复完成:")
    logger.info(f"  修复文件数: {total_stats['files']}")
    logger.info(f"  dict 修复: {total_stats['dict']}")
    logger.info(f"  list 修复: {total_stats['list']}")
    logger.info(f"  set 修复: {total_stats['set']}")
    logger.info(f"  tuple 修复: {total_stats['tuple']}")
    total_fixes = total_stats["dict"] + total_stats["list"] + total_stats["set"] + total_stats["tuple"]
    logger.info(f"  总修复数: {total_fixes}")


if __name__ == "__main__":
    main()
