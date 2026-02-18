"""
修复所有 cast(Type, func() 的语法错误。
模式：cast(Type, func()     →  cast(Type, func(
         arg1,                      arg1,
         arg2,                      arg2,
       )                          ))
"""

from __future__ import annotations

import re
from pathlib import Path


def fix_file(filepath: Path) -> int:
    """修复单个文件"""
    content = filepath.read_text(encoding="utf-8")
    if "cast(" not in content:
        return 0

    lines = content.split("\n")
    fixed = 0
    i = 0

    while i < len(lines):
        line = lines[i]

        # 查找 "cast(Type, expr()" 模式 — 函数调用后面紧跟 ()
        # 但实际参数在后续行中
        # 匹配: return cast(SomeType, some_func()
        # 或: x = cast(SomeType, some_func()
        m = re.search(r"cast\((.+?),\s*(.+?)\(\)\s*(#.*)?$", line)
        if m:
            # 检查下一行是否有参数（缩进的关键字参数）
            if i + 1 < len(lines):
                next_line = lines[i + 1].strip()
                # 如果下一行看起来像参数（keyword=value 或 value,）
                if (
                    (re.match(r"\w+=", next_line) or next_line.endswith(","))
                    and not next_line.startswith("def ")
                    and not next_line.startswith("class ")
                ):
                    cast_type = m.group(1)
                    func_call = m.group(2)
                    comment = m.group(3) or ""

                    # 找到闭合的 )
                    j = i + 1
                    paren_depth = 0
                    found_close = False
                    while j < len(lines):
                        for ch in lines[j]:
                            if ch == "(":
                                paren_depth += 1
                            elif ch == ")":
                                if paren_depth == 0:
                                    found_close = True
                                    break
                                paren_depth -= 1
                        if found_close:
                            break
                        j += 1

                    if found_close:
                        # 修复：把 func() 改为 func(
                        indent = re.match(r"(\s*)", line).group(1)
                        prefix = line[: m.start()]
                        comment_part = f"  {comment.strip()}" if comment and comment.strip() else ""
                        new_first = f"{prefix}cast({cast_type}, {func_call}({comment_part}"
                        lines[i] = new_first

                        # 在闭合的 ) 后面加一个 )
                        close_line = lines[j]
                        last_paren = close_line.rfind(")")
                        if last_paren >= 0:
                            lines[j] = close_line[: last_paren + 1] + ")" + close_line[last_paren + 1 :]

                        fixed += 1
                        i = j + 1
                        continue

        i += 1

    if fixed > 0:
        filepath.write_text("\n".join(lines), encoding="utf-8")

    return fixed


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

    print(f"\n共修复 {total} 处")


if __name__ == "__main__":
    main()
