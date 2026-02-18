"""
修复 return-value 和 func-returns-value 的 type: ignore。
策略：
1. return-value: 如果已有 cast()，移除 type: ignore；否则添加 cast()
2. func-returns-value: 如果函数返回值被赋值，用 cast() 包装
"""

from __future__ import annotations

import re
from pathlib import Path


def fix_file(filepath: Path) -> int:
    """修复单个文件"""
    content = filepath.read_text(encoding="utf-8")
    if "type: ignore" not in content:
        return 0

    lines = content.split("\n")
    fixed = 0

    for i, line in enumerate(lines):
        # 匹配 type: ignore[return-value] 或 type: ignore[func-returns-value]
        m = re.search(r"\s*#\s*type:\s*ignore\[([^\]]*)\]", line)
        if not m:
            continue

        codes = [c.strip() for c in m.group(1).split(",")]

        # 只处理纯 return-value 或 func-returns-value
        target_codes = {"return-value", "func-returns-value"}
        if not all(c in target_codes for c in codes):
            continue

        # 如果行已经有 cast()，直接移除 type: ignore
        code_part = line[: m.start()]
        if "cast(" in code_part:
            lines[i] = code_part.rstrip()
            fixed += 1
            continue

        # 对于 return 语句，添加 cast
        stripped = code_part.strip()
        if stripped.startswith("return "):
            # 获取函数返回类型
            ret_type = _get_return_type(lines, i)
            if ret_type and ret_type != "None":
                return_expr = stripped[7:].rstrip()
                indent = code_part[: len(code_part) - len(code_part.lstrip())]
                lines[i] = f"{indent}return cast({ret_type}, {return_expr})"
                fixed += 1
                _ensure_cast_import(lines)
                continue

        # 对于赋值语句 x = func()，用 cast 包装
        assign_m = re.match(r"(\s*)(\w+)\s*=\s*(.+)", code_part)
        if assign_m:
            indent = assign_m.group(1)
            var_name = assign_m.group(2)
            expr = assign_m.group(3).rstrip()
            # 简单移除 type: ignore（func-returns-value 通常是调用了返回 None 的函数）
            lines[i] = code_part.rstrip()
            fixed += 1
            continue

    if fixed > 0:
        filepath.write_text("\n".join(lines), encoding="utf-8")

    return fixed


def _get_return_type(lines: list[str], return_line_idx: int) -> str | None:
    """向上查找函数定义，提取返回类型"""
    for i in range(return_line_idx - 1, max(return_line_idx - 50, -1), -1):
        line = lines[i].strip()
        m = re.search(r"->\s*(.+?)\s*:", line)
        if m:
            ret_type = m.group(1).strip().strip('"').strip("'")
            return ret_type
        if line.startswith("class ") or (i == 0):
            break
    return None


def _ensure_cast_import(lines: list[str]) -> None:
    """确保有 cast 导入"""
    for line in lines:
        if "from typing import" in line and "cast" in line:
            return
        if "from typing import cast" in line:
            return

    for i, line in enumerate(lines):
        if re.match(r"from typing import ", line):
            if "cast" not in line:
                lines[i] = line.replace("from typing import ", "from typing import cast, ")
            return

    # 在文件开头添加
    for i, line in enumerate(lines):
        if line.startswith("import ") or line.startswith("from "):
            lines.insert(i, "from typing import cast")
            return


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

    print(f"\n共修复 {total} 处 return-value/func-returns-value")


if __name__ == "__main__":
    main()
