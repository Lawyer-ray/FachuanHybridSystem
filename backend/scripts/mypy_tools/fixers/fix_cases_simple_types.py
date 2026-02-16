#!/usr/bin/env python3
"""
Cases 模块简单类型错误批量修复脚本

批量修复 cases 模块的：
1. 泛型类型参数缺失（dict, list, QuerySet）
2. 函数返回类型缺失（-> None）

Requirements: 3.1
"""
from __future__ import annotations

import ast
import logging
import re
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)


def fix_generic_types(content: str) -> tuple[str, int]:
    """修复泛型类型参数缺失"""
    fixes = 0

    # 1. 修复 -> dict
    pattern = r"->\s*dict\s*(?=:|\n)"
    matches = list(re.finditer(pattern, content))
    fixes += len(matches)
    content = re.sub(pattern, "-> dict[str, Any]", content)

    # 2. 修复 -> list
    pattern = r"->\s*list\s*(?=:|\n)"
    matches = list(re.finditer(pattern, content))
    fixes += len(matches)
    content = re.sub(pattern, "-> list[Any]", content)

    # 3. 修复参数类型 : dict =
    pattern = r":\s*dict\s*="
    matches = list(re.finditer(pattern, content))
    fixes += len(matches)
    content = re.sub(pattern, ": dict[str, Any] =", content)

    # 4. 修复参数类型 : list =
    pattern = r":\s*list\s*="
    matches = list(re.finditer(pattern, content))
    fixes += len(matches)
    content = re.sub(pattern, ": list[Any] =", content)

    # 5. 修复变量注解 : dict (不带 =)
    pattern = r":\s*dict\s*(?=\n|;|\|)"
    matches = list(re.finditer(pattern, content))
    fixes += len(matches)
    content = re.sub(pattern, ": dict[str, Any]", content)

    # 6. 修复变量注解 : list (不带 =)
    pattern = r":\s*list\s*(?=\n|;|\|)"
    matches = list(re.finditer(pattern, content))
    fixes += len(matches)
    content = re.sub(pattern, ": list[Any]", content)

    # 7. 修复 Optional[Dict] 和 Optional[List]
    pattern = r"Optional\[Dict\]"
    matches = list(re.finditer(pattern, content))
    fixes += len(matches)
    content = re.sub(pattern, "Optional[Dict[str, Any]]", content)

    pattern = r"Optional\[List\]"
    matches = list(re.finditer(pattern, content))
    fixes += len(matches)
    content = re.sub(pattern, "Optional[List[Any]]", content)

    # 8. 修复 Dict (不在 Optional 中)
    pattern = r":\s*Dict\s*(?=\]|\)|,|=|\n)"
    matches = list(re.finditer(pattern, content))
    fixes += len(matches)
    content = re.sub(pattern, ": Dict[str, Any]", content)

    # 9. 修复 List (不在 Optional 中)
    pattern = r":\s*List\s*(?=\]|\)|,|=|\n)"
    matches = list(re.finditer(pattern, content))
    fixes += len(matches)
    content = re.sub(pattern, ": List[Any]", content)

    return content, fixes


def ensure_any_import(content: str) -> str:
    """确保导入 Any, Dict, List"""
    needs_any = "Any" in content
    needs_dict = "Dict[" in content
    needs_list = "List[" in content

    if not (needs_any or needs_dict or needs_list):
        return content

    # 检查是否已导入
    has_any = bool(re.search(r"from typing import.*\bAny\b", content))
    has_dict = bool(re.search(r"from typing import.*\bDict\b", content))
    has_list = bool(re.search(r"from typing import.*\bList\b", content))

    types_to_add = []
    if needs_any and not has_any:
        types_to_add.append("Any")
    if needs_dict and not has_dict:
        types_to_add.append("Dict")
    if needs_list and not has_list:
        types_to_add.append("List")

    if not types_to_add:
        return content

    lines = content.split("\n")

    # 查找 from typing import 行
    typing_import_idx = -1
    for i, line in enumerate(lines):
        if line.startswith("from typing import"):
            typing_import_idx = i
            break

    if typing_import_idx >= 0:
        line = lines[typing_import_idx]

        if "(" in line:
            # 多行导入
            if line.endswith(")"):
                line = line[:-1] + ", " + ", ".join(types_to_add) + ")"
                lines[typing_import_idx] = line
            else:
                # 找到结束括号
                for j in range(typing_import_idx + 1, len(lines)):
                    if ")" in lines[j]:
                        lines[j] = lines[j].replace(")", ", " + ", ".join(types_to_add) + ")")
                        break
        else:
            # 单行导入
            lines[typing_import_idx] = line.rstrip() + ", " + ", ".join(types_to_add)
    else:
        # 添加新导入
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

        lines.insert(insert_idx, "from typing import " + ", ".join(types_to_add))
        if insert_idx + 1 < len(lines) and lines[insert_idx + 1].strip():
            lines.insert(insert_idx + 1, "")

    return "\n".join(lines)


def has_return_value(node: ast.FunctionDef | ast.AsyncFunctionDef) -> bool:
    """检查函数是否有返回值"""
    for child in ast.walk(node):
        if isinstance(child, ast.Return) and child.value is not None:
            return True
    return False


def fix_return_types(content: str) -> tuple[str, int]:
    """为缺少返回类型的函数添加 -> None"""
    try:
        tree = ast.parse(content)
    except SyntaxError:
        return content, 0

    lines = content.split("\n")
    fixes = 0

    # 收集需要修复的函数
    functions_to_fix: list[tuple[int, int]] = []

    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            if node.returns is None and not has_return_value(node):
                functions_to_fix.append((node.lineno, node.col_offset))

    # 从后往前修复
    functions_to_fix.sort(reverse=True)

    for lineno, col_offset in functions_to_fix:
        line_idx = lineno - 1

        # 查找函数定义的结束位置
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

        end_line = lines[end_line_idx]
        colon_pos = end_line.find(":", end_col)
        if colon_pos < 0:
            continue

        # 插入 -> None
        new_line = end_line[:colon_pos] + " -> None" + end_line[colon_pos:]
        lines[end_line_idx] = new_line
        fixes += 1

    return "\n".join(lines), fixes


def process_file(file_path: Path) -> dict[str, Any]:
    """处理单个文件"""
    try:
        content = file_path.read_text(encoding="utf-8")
        original_content = content

        generic_fixes = 0
        return_fixes = 0

        # 1. 修复泛型类型
        content, generic_fixes = fix_generic_types(content)

        # 2. 修复返回类型
        content, return_fixes = fix_return_types(content)

        total_fixes = generic_fixes + return_fixes

        # 3. 确保导入 Any
        if total_fixes > 0:
            content = ensure_any_import(content)

        # 只有内容变化时才写入
        if content != original_content:
            file_path.write_text(content, encoding="utf-8")
            return {
                "file": str(file_path),
                "generic_fixes": generic_fixes,
                "return_fixes": return_fixes,
                "total_fixes": total_fixes,
                "success": True,
            }

        return {"file": str(file_path), "generic_fixes": 0, "return_fixes": 0, "total_fixes": 0, "success": True}

    except Exception as e:
        return {
            "file": str(file_path),
            "generic_fixes": 0,
            "return_fixes": 0,
            "total_fixes": 0,
            "success": False,
            "error": str(e),
        }


def main() -> None:
    """主函数"""
    backend_path = Path(__file__).parent.parent
    cases_path = backend_path / "apps" / "cases"

    logger.info("开始批量修复 cases 模块简单类型错误...")
    logger.info(f"扫描目录: {cases_path}")

    # 收集所有 Python 文件
    py_files = [f for f in cases_path.rglob("*.py") if f.name != "__init__.py"]
    logger.info(f"找到 {len(py_files)} 个 Python 文件\n")

    # 处理文件
    results: list[dict[str, Any]] = []
    modified_files: list[Path] = []
    total_generic_fixes = 0
    total_return_fixes = 0

    for py_file in py_files:
        result = process_file(py_file)
        results.append(result)

        if result["success"] and result["total_fixes"] > 0:
            modified_files.append(py_file)
            total_generic_fixes += result["generic_fixes"]
            total_return_fixes += result["return_fixes"]
            rel_path = py_file.relative_to(backend_path)
            logger.info(f"  ✓ {rel_path}: " f"泛型 {result['generic_fixes']}, " f"返回类型 {result['return_fixes']}")

    # 输出统计
    logger.info(f"\n修复完成:")
    logger.info(f"  - 修改文件数: {len(modified_files)}")
    logger.info(f"  - 泛型类型修复: {total_generic_fixes}")
    logger.info(f"  - 返回类型修复: {total_return_fixes}")
    logger.info(f"  - 总修复数: {total_generic_fixes + total_return_fixes}")

    # 输出失败的文件
    failed = [r for r in results if not r["success"]]
    if failed:
        logger.info(f"\n失败文件 ({len(failed)}):")
        for r in failed:
            logger.info(f"  ✗ {r['file']}: {r.get('error', 'Unknown error')}")


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    main()
