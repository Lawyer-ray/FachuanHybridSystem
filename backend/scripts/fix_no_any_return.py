"""
修复 no-any-return 错误。
策略：在 return 语句中用 cast() 包装返回值。

例如：
  return queryset.first()  # type: ignore[no-any-return]
变为：
  return cast(Client, queryset.first())
"""

from __future__ import annotations

import re
from pathlib import Path


def get_function_return_type(lines: list[str], return_line_idx: int) -> str | None:
    """向上查找函数定义，提取返回类型"""
    for i in range(return_line_idx - 1, max(return_line_idx - 50, -1), -1):
        line = lines[i].strip()
        # 匹配 def xxx(...) -> ReturnType:
        m = re.search(r"->\s*(.+?)\s*:", line)
        if m:
            ret_type = m.group(1).strip()
            # 去掉引号
            ret_type = ret_type.strip('"').strip("'")
            return ret_type
        # 如果遇到 class 定义或文件开头，停止
        if line.startswith("class ") or (i == 0):
            break
    return None


def fix_file(filepath: Path) -> int:
    """修复单个文件的 no-any-return 错误"""
    content = filepath.read_text(encoding="utf-8")
    if "no-any-return" not in content:
        return 0

    lines = content.split("\n")
    fixed = 0
    needs_cast_import = False

    for i, line in enumerate(lines):
        # 匹配包含 no-any-return 的 type: ignore
        m = re.search(r"(\s*)(.+?)\s*#\s*type:\s*ignore\[([^\]]*no-any-return[^\]]*)\]", line)
        if not m:
            continue

        indent = m.group(1)
        code_part = m.group(2).rstrip()
        error_codes = [c.strip() for c in m.group(3).split(",")]

        # 只处理纯 no-any-return（不混合其他错误码）
        remaining_codes = [c for c in error_codes if c != "no-any-return"]

        # 检查是否是 return 语句
        stripped = code_part.strip()
        if not stripped.startswith("return "):
            continue

        # 提取返回值表达式
        return_expr = stripped[7:].strip()
        if not return_expr:
            continue

        # 获取函数返回类型
        ret_type = get_function_return_type(lines, i)
        if not ret_type:
            continue

        # 跳过复杂的返回类型
        if "|" in ret_type and "None" in ret_type:
            # Optional 类型，不好 cast
            continue

        # 构建 cast 表达式
        new_return = f"{indent}return cast({ret_type}, {return_expr})"
        if remaining_codes:
            codes_str = ", ".join(remaining_codes)
            new_return += f"  # type: ignore[{codes_str}]"

        lines[i] = new_return
        needs_cast_import = True
        fixed += 1

    if fixed > 0:
        # 添加 cast 导入
        if needs_cast_import:
            lines = add_cast_import(lines)
        filepath.write_text("\n".join(lines), encoding="utf-8")

    return fixed


def add_cast_import(lines: list[str]) -> list[str]:
    """确保文件有 cast 导入"""
    # 检查是否已有 cast 导入
    for line in lines:
        if "from typing import" in line and "cast" in line:
            return lines
        if "from typing import cast" in line:
            return lines

    # 查找 typing 导入行并添加 cast
    for i, line in enumerate(lines):
        m = re.match(r"from typing import (.+)", line)
        if m:
            imports = m.group(1).strip()
            if "cast" not in imports:
                # 添加 cast 到导入列表
                if imports.startswith("("):
                    # 多行导入，在第一行后添加
                    lines[i] = line.rstrip()
                    # 找到闭合括号
                    for j in range(i, min(i + 10, len(lines))):
                        if ")" in lines[j]:
                            lines[j] = lines[j].replace(")", ", cast)")
                            break
                else:
                    lines[i] = f"from typing import cast, {imports}"
            return lines

    # 没有 typing 导入，在文件开头添加
    insert_idx = 0
    for i, line in enumerate(lines):
        if line.startswith("import ") or line.startswith("from "):
            insert_idx = i
            break

    lines.insert(insert_idx, "from typing import cast")
    return lines


def main() -> None:
    apps_dir = Path("apps")
    total = 0

    for py_file in sorted(apps_dir.rglob("*.py")):
        if "migrations" in str(py_file) or "__pycache__" in str(py_file):
            continue
        fixed = fix_file(py_file)
        if fixed > 0:
            print(f"  {py_file}: {fixed} 处")
            total += fixed

    print(f"\n共修复 {total} 处 no-any-return")


if __name__ == "__main__":
    main()
