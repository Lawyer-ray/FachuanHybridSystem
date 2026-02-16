#!/usr/bin/env python3
"""批量修复 documents 模块的简单类型错误"""

import re
from pathlib import Path
from typing import Any


def fix_missing_type_parameters(file_path: Path) -> int:
    """修复泛型类型参数缺失"""
    content = file_path.read_text(encoding="utf-8")
    original = content
    fixes = 0

    # 修复 -> dict
    if re.search(r"-> dict[:\s]", content):
        content = re.sub(r"-> dict:", r"-> dict[str, Any]:", content)
        content = re.sub(r"-> dict\s*\n", r"-> dict[str, Any]\n", content)
        fixes += 1

    # 修复 -> list (不带泛型参数)
    if re.search(r"-> list[:\s]", content):
        content = re.sub(r"-> list:", r"-> list[Any]:", content)
        content = re.sub(r"-> list\s*\n", r"-> list[Any]\n", content)
        fixes += 1

    # 修复参数类型 : dict =
    if re.search(r": dict\s*=", content):
        content = re.sub(r": dict\s*=", r": dict[str, Any] =", content)
        fixes += 1

    # 修复参数类型 : list =
    if re.search(r": list\s*=", content):
        content = re.sub(r": list\s*=", r": list[Any] =", content)
        fixes += 1

    # 修复参数类型 principals: list)
    if re.search(r":\s*list\)", content):
        content = re.sub(r":\s*list\)", r": list[Any])", content)
        fixes += 1

    # 修复 dict[str, list] -> dict[str, list[Any]]
    if re.search(r"dict\[str,\s*list\]", content):
        content = re.sub(r"dict\[str,\s*list\]", r"dict[str, list[Any]]", content)
        fixes += 1

    # 修复 -> tuple 缺少泛型参数
    if re.search(r"-> tuple:", content):
        content = re.sub(r"-> tuple:", r"-> tuple[Any, ...]:", content)
        fixes += 1

    # 确保导入 Any
    if fixes > 0 and "Any" in content:
        if "from typing import" in content:
            # 检查是否已导入 Any
            if not re.search(r"from typing import.*\bAny\b", content):
                # 在第一个 from typing import 行添加 Any
                content = re.sub(r"(from typing import [^)]+)", r"\1, Any", content, count=1)

    if content != original:
        file_path.write_text(content, encoding="utf-8")
        return fixes
    return 0


def fix_missing_return_types(file_path: Path) -> int:
    """修复缺少返回类型的函数"""
    content = file_path.read_text(encoding="utf-8")
    original = content
    fixes = 0

    # 修复 def xxx() : (缺少返回类型)
    # 注意：这个比较复杂，需要分析函数体，这里只处理简单情况

    if content != original:
        file_path.write_text(content, encoding="utf-8")
        return fixes
    return 0


def fix_optional_defaults(file_path: Path) -> int:
    """修复可选参数默认值问题"""
    content = file_path.read_text(encoding="utf-8")
    original = content
    fixes = 0

    # 修复 xxx: Type = None -> xxx: Type | None = None
    # 查找模式：参数名: 类型 = None，但类型不包含 None 或 Optional
    pattern = r"(\w+):\s*([A-Z]\w+(?:\[[^\]]+\])?)\s*=\s*None"

    def replace_optional(match: re.Match[str]) -> str:
        param_name = match.group(1)
        param_type = match.group(2)
        # 检查类型是否已经包含 None 或 Optional
        if "None" in param_type or "Optional" in param_type:
            return match.group(0)
        return f"{param_name}: {param_type} | None = None"

    new_content = re.sub(pattern, replace_optional, content)
    if new_content != content:
        content = new_content
        fixes += 1

    if content != original:
        file_path.write_text(content, encoding="utf-8")
        return fixes
    return 0


def main() -> None:
    """主函数"""
    backend_path = Path(__file__).parent.parent
    documents_path = backend_path / "apps" / "documents"

    total_fixes = 0
    files_fixed = 0

    print("开始修复 documents 模块的简单类型错误...")
    print("=" * 80)

    for py_file in documents_path.rglob("*.py"):
        if py_file.name == "__init__.py":
            continue

        file_fixes = 0
        file_fixes += fix_missing_type_parameters(py_file)
        file_fixes += fix_optional_defaults(py_file)

        if file_fixes > 0:
            files_fixed += 1
            total_fixes += file_fixes
            rel_path = py_file.relative_to(backend_path)
            print(f"✓ {rel_path}: {file_fixes} 处修复")

    print("=" * 80)
    print(f"完成！共修复 {files_fixed} 个文件，{total_fixes} 处错误")


if __name__ == "__main__":
    main()
