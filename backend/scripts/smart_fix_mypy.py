#!/usr/bin/env python3
"""智能修复常见mypy错误"""
import ast
import re
import subprocess
from pathlib import Path
from typing import Dict, List, Tuple


def run_mypy() -> Tuple[str, int]:
    """运行mypy并返回输出和错误数"""
    result = subprocess.run(
        ["python", "-m", "mypy", "apps/", "--strict", "--no-error-summary"], capture_output=True, text=True
    )
    output = result.stdout + result.stderr

    # 提取错误数
    match = re.search(r"Found (\d+) errors", output)
    error_count = int(match.group(1)) if match else 0

    return output, error_count


def fix_optional_none_defaults(file_path: Path) -> bool:
    """修复 param: Type = None 模式"""
    try:
        content = file_path.read_text()
        original = content

        # 修复函数参数中的 Type = None
        # 匹配: param: SomeType = None (不包含 | None 或 Optional)
        pattern = r"(\w+):\s*([A-Za-z_][\w\[\], ]*?)(\s*=\s*None)"

        def replace_func(match):
            param, type_hint, equals_none = match.groups()
            # 如果已经有 | None 或 Optional，不修改
            if "| None" in type_hint or "Optional" in type_hint or "None" in type_hint:
                return match.group(0)
            return f"{param}: {type_hint.strip()} | None{equals_none}"

        content = re.sub(pattern, replace_func, content)

        if content != original:
            file_path.write_text(content)
            return True
    except Exception as e:
        print(f"  错误: {e}")
    return False


def add_missing_any_import(file_path: Path) -> bool:
    """添加缺失的Any导入"""
    try:
        content = file_path.read_text()

        # 检查是否使用了Any但没有导入
        if "Any" in content and "from typing import" in content:
            # 查找typing导入行
            lines = content.splitlines()
            for i, line in enumerate(lines):
                if line.startswith("from typing import") and "Any" not in line:
                    # 添加Any到导入
                    if line.endswith(")"):
                        # 多行导入
                        lines[i] = line[:-1] + ", Any)"
                    else:
                        # 单行导入
                        lines[i] = line + ", Any"

                    new_content = "\n".join(lines)
                    file_path.write_text(new_content)
                    return True

        # 如果没有typing导入但使用了Any，添加导入
        if "Any" in content and "from typing import" not in content:
            lines = content.splitlines()
            # 在from __future__ import之后或文件开头添加
            insert_pos = 0
            for i, line in enumerate(lines):
                if line.startswith("from __future__"):
                    insert_pos = i + 1
                    break
                elif line.strip() and not line.startswith("#") and not line.startswith('"""'):
                    insert_pos = i
                    break

            lines.insert(insert_pos, "from typing import Any")
            file_path.write_text("\n".join(lines))
            return True

    except Exception:
        pass
    return False


def fix_type_arg_dict_list(file_path: Path) -> bool:
    """修复缺失类型参数的dict和list"""
    try:
        content = file_path.read_text()
        original = content

        # 修复 -> dict 为 -> dict[str, Any]
        content = re.sub(r"-> dict\b", "-> dict[str, Any]", content)
        content = re.sub(r"-> list\b", "-> list[Any]", content)
        content = re.sub(r": dict\b", ": dict[str, Any]", content)
        content = re.sub(r": list\b", ": list[Any]", content)

        # 修复 Optional[dict] 为 Optional[dict[str, Any]]
        content = re.sub(r"Optional\[dict\]", "Optional[dict[str, Any]]", content)
        content = re.sub(r"Optional\[list\]", "Optional[list[Any]]", content)

        # 修复 list[dict] 为 list[dict[str, Any]]
        content = re.sub(r"list\[dict\]", "list[dict[str, Any]]", content)

        if content != original:
            file_path.write_text(content)
            return True
    except Exception:
        pass
    return False


def add_return_none_annotation(file_path: Path) -> bool:
    """为缺少返回类型的函数添加 -> None"""
    try:
        content = file_path.read_text()
        lines = content.splitlines()
        modified = False

        for i, line in enumerate(lines):
            # 匹配 def function_name(...): 但没有 ->
            if re.match(r"\s*def \w+\([^)]*\):\s*$", line) and "->" not in line:
                # 在冒号前添加 -> None
                lines[i] = line.replace("):", ") -> None:")
                modified = True

        if modified:
            file_path.write_text("\n".join(lines))
            return True
    except Exception:
        pass
    return False


def main():
    print("开始智能修复mypy错误...")
    print("=" * 60)

    # 获取初始错误数
    print("运行初始mypy检查...")
    _, initial_errors = run_mypy()
    print(f"初始错误数: {initial_errors}")
    print()

    # 收集所有Python文件
    py_files = list(Path("apps").rglob("*.py"))
    print(f"找到 {len(py_files)} 个Python文件")
    print()

    # 应用各种修复
    fixes = [
        ("修复Optional默认值", fix_optional_none_defaults),
        ("添加Any导入", add_missing_any_import),
        ("修复dict/list类型参数", fix_type_arg_dict_list),
        ("添加-> None注解", add_return_none_annotation),
    ]

    for fix_name, fix_func in fixes:
        print(f"应用修复: {fix_name}")
        fixed_count = 0
        for py_file in py_files:
            if fix_func(py_file):
                fixed_count += 1
        print(f"  修复了 {fixed_count} 个文件")

    print()
    print("=" * 60)
    print("运行最终mypy检查...")
    _, final_errors = run_mypy()
    print(f"最终错误数: {final_errors}")
    print(f"减少了 {initial_errors - final_errors} 个错误")


if __name__ == "__main__":
    main()
