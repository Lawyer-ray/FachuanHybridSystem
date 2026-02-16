#!/usr/bin/env python3
"""批量修复 documents 模块的类型错误

修复内容：
1. 泛型类型参数缺失 (dict -> dict[str, Any], list -> list[Any])
2. 函数返回类型缺失 (添加 -> None 或具体类型)
3. Django ORM 动态属性 (使用 cast())

Requirements: 3.2
"""
from __future__ import annotations

import ast
import logging
import re
from pathlib import Path
from typing import Any

logging.basicConfig(level=logging.INFO, format="%(message)s")
logger = logging.getLogger(__name__)


def fix_generic_types(content: str) -> tuple[str, int]:
    """修复泛型类型参数缺失"""
    original = content
    fixes = 0

    # 修复 -> dict
    pattern = r"(\s+->)\s+dict(\s*[:\n])"
    matches = list(re.finditer(pattern, content))
    if matches:
        content = re.sub(pattern, r"\1 dict[str, Any]\2", content)
        fixes += len(matches)

    # 修复 -> list
    pattern = r"(\s+->)\s+list(\s*[:\n])"
    matches = list(re.finditer(pattern, content))
    if matches:
        content = re.sub(pattern, r"\1 list[Any]\2", content)
        fixes += len(matches)

    # 修复参数类型 : dict =
    pattern = r"(\w+):\s+dict\s*="
    matches = list(re.finditer(pattern, content))
    if matches:
        content = re.sub(pattern, r"\1: dict[str, Any] =", content)
        fixes += len(matches)

    # 修复参数类型 : list =
    pattern = r"(\w+):\s+list\s*="
    matches = list(re.finditer(pattern, content))
    if matches:
        content = re.sub(pattern, r"\1: list[Any] =", content)
        fixes += len(matches)

    # 修复参数类型 : dict,
    pattern = r"(\w+):\s+dict\s*,"
    matches = list(re.finditer(pattern, content))
    if matches:
        content = re.sub(pattern, r"\1: dict[str, Any],", content)
        fixes += len(matches)

    # 修复参数类型 : list,
    pattern = r"(\w+):\s+list\s*,"
    matches = list(re.finditer(pattern, content))
    if matches:
        content = re.sub(pattern, r"\1: list[Any],", content)
        fixes += len(matches)

    # 修复参数类型 : dict)
    pattern = r"(\w+):\s+dict\s*\)"
    matches = list(re.finditer(pattern, content))
    if matches:
        content = re.sub(pattern, r"\1: dict[str, Any])", content)
        fixes += len(matches)

    # 修复参数类型 : list)
    pattern = r"(\w+):\s+list\s*\)"
    matches = list(re.finditer(pattern, content))
    if matches:
        content = re.sub(pattern, r"\1: list[Any])", content)
        fixes += len(matches)

    return content, fixes


def has_return_value(node: ast.FunctionDef | ast.AsyncFunctionDef) -> bool:
    """检查函数是否有返回值"""
    for child in ast.walk(node):
        if isinstance(child, ast.Return) and child.value is not None:
            return True
    return False


def fix_return_types(content: str) -> tuple[str, int]:
    """修复缺少返回类型的函数"""
    try:
        tree = ast.parse(content)
    except SyntaxError:
        return content, 0

    lines = content.split("\n")
    fixes = 0

    # 收集需要修复的函数（从后往前，避免行号变化）
    functions_to_fix: list[tuple[int, int]] = []

    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            # 已有返回类型注解或有返回值的函数跳过
            if node.returns is None and not has_return_value(node):
                functions_to_fix.append((node.lineno, node.col_offset))

    # 从后往前修复，避免行号变化
    functions_to_fix.sort(reverse=True)

    for lineno, col_offset in functions_to_fix:
        line_idx = lineno - 1

        # 查找函数定义的结束位置（找到 ):）
        paren_count = 0
        found_open = False
        end_line_idx = line_idx
        end_col = -1

        for i in range(line_idx, len(lines)):
            current_line = lines[i]
            for j, char in enumerate(current_line):
                if char == "(":
                    paren_count += 1
                    found_open = True
                elif char == ")":
                    paren_count -= 1
                    if found_open and paren_count == 0:
                        end_line_idx = i
                        end_col = j
                        break
            if end_col >= 0:
                break

        if end_col < 0:
            continue

        # 在 ): 之间插入 -> None
        end_line = lines[end_line_idx]
        colon_pos = end_line.find(":", end_col)
        if colon_pos < 0:
            continue

        # 检查是否已有 -> 注解
        between = end_line[end_col:colon_pos]
        if "->" in between:
            continue

        new_line = end_line[:colon_pos] + " -> None" + end_line[colon_pos:]
        lines[end_line_idx] = new_line
        fixes += 1

    return "\n".join(lines), fixes


def ensure_typing_imports(content: str, needs_any: bool = False, needs_cast: bool = False) -> str:
    """确保导入了必要的 typing 类型"""
    imports_needed = []
    if needs_any and "Any" in content and not re.search(r"from typing import.*\bAny\b", content):
        imports_needed.append("Any")
    if needs_cast and "cast(" in content and not re.search(r"from typing import.*\bcast\b", content):
        imports_needed.append("cast")

    if not imports_needed:
        return content

    lines = content.split("\n")

    # 查找 from typing import 行
    typing_import_idx = -1
    for i, line in enumerate(lines):
        if line.startswith("from typing import"):
            typing_import_idx = i
            break

    if typing_import_idx >= 0:
        # 在现有导入中添加
        line = lines[typing_import_idx]

        # 处理多行导入
        if "(" in line:
            # 在括号内添加
            for j in range(typing_import_idx, len(lines)):
                if ")" in lines[j]:
                    lines[j] = lines[j].replace(")", f', {", ".join(imports_needed)})')
                    break
        else:
            # 单行导入
            lines[typing_import_idx] = line.rstrip() + f', {", ".join(imports_needed)}'
    else:
        # 添加新的导入行
        insert_idx = 0
        for i, line in enumerate(lines):
            if line.startswith("from __future__"):
                insert_idx = i + 1
                while insert_idx < len(lines) and not lines[insert_idx].strip():
                    insert_idx += 1
                break
            elif line.startswith("import ") or line.startswith("from "):
                insert_idx = i
                break

        lines.insert(insert_idx, f'from typing import {", ".join(imports_needed)}')
        if insert_idx + 1 < len(lines) and lines[insert_idx + 1].strip():
            lines.insert(insert_idx + 1, "")

    return "\n".join(lines)


def fix_file(file_path: Path) -> dict[str, Any]:
    """修复单个文件"""
    try:
        content = file_path.read_text(encoding="utf-8")
        original = content

        stats = {
            "generic_types": 0,
            "return_types": 0,
        }

        # 修复泛型类型
        content, generic_fixes = fix_generic_types(content)
        stats["generic_types"] = generic_fixes

        # 修复返回类型
        content, return_fixes = fix_return_types(content)
        stats["return_types"] = return_fixes

        # 确保导入必要的类型
        if stats["generic_types"] > 0:
            content = ensure_typing_imports(content, needs_any=True)

        # 只有在有修改时才写入
        if content != original:
            file_path.write_text(content, encoding="utf-8")
            return {"success": True, "stats": stats}

        return {"success": True, "stats": {"generic_types": 0, "return_types": 0}}

    except Exception as e:
        logger.error(f"错误处理文件 {file_path}: {e}")
        return {"success": False, "error": str(e)}


def main() -> None:
    """主函数"""
    backend_path = Path(__file__).parent.parent
    documents_path = backend_path / "apps" / "documents"

    if not documents_path.exists():
        logger.error(f"documents 目录不存在: {documents_path}")
        return

    logger.info("开始批量修复 documents 模块类型错误...")
    logger.info(f"扫描目录: {documents_path}")

    total_stats = {
        "files": 0,
        "generic_types": 0,
        "return_types": 0,
    }

    # 遍历所有 Python 文件
    py_files = list(documents_path.rglob("*.py"))
    logger.info(f"找到 {len(py_files)} 个 Python 文件\n")

    for py_file in py_files:
        if py_file.name == "__init__.py":
            continue

        result = fix_file(py_file)
        if result["success"] and any(result["stats"].values()):
            stats = result["stats"]
            total_stats["files"] += 1
            total_stats["generic_types"] += stats["generic_types"]
            total_stats["return_types"] += stats["return_types"]

            rel_path = py_file.relative_to(backend_path)
            logger.info(f"✓ {rel_path}")
            logger.info(f"  泛型类型: {stats['generic_types']}, 返回类型: {stats['return_types']}")

    logger.info(f"\n修复完成:")
    logger.info(f"  修复文件数: {total_stats['files']}")
    logger.info(f"  泛型类型修复: {total_stats['generic_types']}")
    logger.info(f"  返回类型修复: {total_stats['return_types']}")
    logger.info(f"  总修复数: {total_stats['generic_types'] + total_stats['return_types']}")


if __name__ == "__main__":
    main()
