#!/usr/bin/env python3
"""
快速修复 litigation_ai 模块的简单类型错误
- 修复泛型类型参数缺失（dict → dict[str, Any], list → list[Any]）
- 修复返回类型缺失（添加 -> None）
- 修复可选参数默认值
"""
from __future__ import annotations

import ast
import re
from pathlib import Path
from typing import Any


def fix_generic_types(content: str) -> tuple[str, int]:
    """修复泛型类型参数缺失"""
    fixes = 0

    # dict = None → dict[str, Any] | None = None
    pattern1 = r"(\w+):\s*dict\s*=\s*None"
    matches1 = re.findall(pattern1, content)
    if matches1:
        content = re.sub(pattern1, r"\1: dict[str, Any] | None = None", content)
        fixes += len(matches1)

    # list = None → list[Any] | None = None
    pattern2 = r"(\w+):\s*list\s*=\s*None"
    matches2 = re.findall(pattern2, content)
    if matches2:
        content = re.sub(pattern2, r"\1: list[Any] | None = None", content)
        fixes += len(matches2)

    # -> dict: → -> dict[str, Any]:
    pattern3 = r"->\s*dict\s*:"
    matches3 = re.findall(pattern3, content)
    if matches3:
        content = re.sub(pattern3, "-> dict[str, Any]:", content)
        fixes += len(matches3)

    # -> list: → -> list[Any]:
    pattern4 = r"->\s*list\s*:"
    matches4 = re.findall(pattern4, content)
    if matches4:
        content = re.sub(pattern4, "-> list[Any]:", content)
        fixes += len(matches4)

    # param: dict) → param: dict[str, Any])
    pattern5 = r"(\w+):\s*dict\s*\)"
    matches5 = re.findall(pattern5, content)
    if matches5:
        content = re.sub(pattern5, r"\1: dict[str, Any])", content)
        fixes += len(matches5)

    # param: list) → param: list[Any])
    pattern6 = r"(\w+):\s*list\s*\)"
    matches6 = re.findall(pattern6, content)
    if matches6:
        content = re.sub(pattern6, r"\1: list[Any])", content)
        fixes += len(matches6)

    # param: dict, → param: dict[str, Any],
    pattern7 = r"(\w+):\s*dict\s*,"
    matches7 = re.findall(pattern7, content)
    if matches7:
        content = re.sub(pattern7, r"\1: dict[str, Any],", content)
        fixes += len(matches7)

    # param: list, → param: list[Any],
    pattern8 = r"(\w+):\s*list\s*,"
    matches8 = re.findall(pattern8, content)
    if matches8:
        content = re.sub(pattern8, r"\1: list[Any],", content)
        fixes += len(matches8)

    return content, fixes


def fix_optional_defaults(content: str) -> tuple[str, int]:
    """修复可选参数默认值（= None 但类型不是 Optional）"""
    fixes = 0

    # param: str = None → param: str | None = None
    pattern1 = r"(\w+):\s*str\s*=\s*None"
    matches1 = re.findall(pattern1, content)
    if matches1:
        content = re.sub(pattern1, r"\1: str | None = None", content)
        fixes += len(matches1)

    # param: int = None → param: int | None = None
    pattern2 = r"(\w+):\s*int\s*=\s*None"
    matches2 = re.findall(pattern2, content)
    if matches2:
        content = re.sub(pattern2, r"\1: int | None = None", content)
        fixes += len(matches2)

    # param: Exception = None → param: Exception | None = None
    pattern3 = r"(\w+):\s*Exception\s*=\s*None"
    matches3 = re.findall(pattern3, content)
    if matches3:
        content = re.sub(pattern3, r"\1: Exception | None = None", content)
        fixes += len(matches3)

    return content, fixes


def add_return_none(content: str) -> tuple[str, int]:
    """为缺少返回类型的函数添加 -> None"""
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
            # 检查是否缺少返回类型注解
            if node.returns is None:
                # 检查函数是否有返回值
                has_return_value = any(isinstance(n, ast.Return) and n.value is not None for n in ast.walk(node))

                if not has_return_value:
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

        # 插入 -> None
        new_line = end_line[:colon_pos] + " -> None" + end_line[colon_pos:]
        lines[end_line_idx] = new_line
        fixes += 1

    return "\n".join(lines), fixes


def ensure_typing_imports(content: str) -> str:
    """确保必要的 typing 导入存在"""
    # 检查是否需要 Any
    needs_any = "dict[str, Any]" in content or "list[Any]" in content
    if not needs_any:
        return content

    # 检查是否已导入 Any
    if re.search(r"from typing import.*\bAny\b", content):
        return content

    lines = content.split("\n")

    # 查找 from typing import 行
    typing_import_line = -1
    for i, line in enumerate(lines):
        if line.startswith("from typing import"):
            typing_import_line = i
            break

    if typing_import_line >= 0:
        # 在现有导入中添加 Any
        line = lines[typing_import_line]
        if "Any" not in line:
            line = line.rstrip()
            if line.endswith(")"):
                line = line[:-1] + ", Any)"
            else:
                line = line + ", Any"
            lines[typing_import_line] = line
    else:
        # 添加新的导入行
        insert_pos = 0
        for i, line in enumerate(lines):
            if line.startswith("from __future__"):
                insert_pos = i + 1
                break
            elif line.startswith("import ") or line.startswith("from "):
                insert_pos = i
                break

        lines.insert(insert_pos, "from typing import Any")
        if insert_pos > 0 and lines[insert_pos - 1].strip():
            lines.insert(insert_pos, "")

    return "\n".join(lines)


def process_file(file_path: Path) -> dict[str, Any]:
    """处理单个文件"""
    try:
        content = file_path.read_text(encoding="utf-8")
        original_content = content
        total_fixes = 0

        # 应用修复
        content, n1 = fix_generic_types(content)
        total_fixes += n1

        content, n2 = fix_optional_defaults(content)
        total_fixes += n2

        content, n3 = add_return_none(content)
        total_fixes += n3

        # 如果有修复，确保导入 Any
        if total_fixes > 0:
            content = ensure_typing_imports(content)

        # 只有内容变化时才写入
        if content != original_content:
            file_path.write_text(content, encoding="utf-8")
            return {"file": str(file_path), "fixes": total_fixes, "success": True}

        return {"file": str(file_path), "fixes": 0, "success": True}

    except Exception as e:
        return {"file": str(file_path), "fixes": 0, "success": False, "error": str(e)}


def main() -> None:
    """主函数"""
    backend_path = Path(__file__).parent.parent
    litigation_ai_path = backend_path / "apps" / "litigation_ai"

    print("开始批量修复 litigation_ai 模块的简单类型错误...")
    print(f"扫描目录: {litigation_ai_path}")

    # 收集所有 Python 文件
    py_files = list(litigation_ai_path.rglob("*.py"))
    print(f"找到 {len(py_files)} 个 Python 文件")

    # 处理文件
    results: list[dict[str, Any]] = []
    modified_files: list[Path] = []
    total_fixes = 0

    for py_file in py_files:
        result = process_file(py_file)
        results.append(result)

        if result["success"] and result["fixes"] > 0:
            modified_files.append(py_file)
            total_fixes += result["fixes"]
            rel_path = py_file.relative_to(backend_path)
            print(f"  ✓ {rel_path}: {result['fixes']} 处修复")

    # 输出统计
    print(f"\n修复完成:")
    print(f"  - 修改文件数: {len(modified_files)}")
    print(f"  - 总修复数: {total_fixes}")

    # 输出失败的文件
    failed = [r for r in results if not r["success"]]
    if failed:
        print(f"\n失败文件 ({len(failed)}):")
        for r in failed:
            print(f"  ✗ {r['file']}: {r.get('error', 'Unknown error')}")


if __name__ == "__main__":
    main()
