"""
修复脚本生成的错误 cast() 调用。
模式：return cast(Type, func_call()  →  应该是 return cast(Type, func_call(
         arg1, arg2                              arg1, arg2
       )                                       ))
"""

from __future__ import annotations

import re
from pathlib import Path


def fix_file(filepath: Path) -> int:
    """修复单个文件中的错误 cast() 调用"""
    content = filepath.read_text(encoding="utf-8")
    if "cast(" not in content:
        return 0

    lines = content.split("\n")
    fixed = 0
    i = 0

    while i < len(lines):
        line = lines[i]

        # 查找 "return cast(Type, expr()" 模式 — 即 cast 的第二个参数是一个函数调用
        # 但函数调用的参数在下面的行中
        m = re.search(r"return cast\((.+?),\s*(.+?)\(\)\s*(#.*)?$", line)
        if m:
            cast_type = m.group(1)
            func_call = m.group(2)
            comment = m.group(3) or ""

            # 检查下面的行是否有参数和闭合括号
            # 收集后续行直到找到闭合的 )
            j = i + 1
            args_lines = []
            found_close = False
            while j < len(lines):
                next_line = lines[j]
                args_lines.append(next_line)
                if ")" in next_line:
                    found_close = True
                    break
                j += 1

            if found_close and args_lines:
                # 重建：return cast(Type, func_call(
                indent = re.match(r"(\s*)", line).group(1)
                comment_part = f"  {comment}" if comment.strip() else ""

                # 第一行：return cast(Type, func_call(
                new_first = f"{indent}return cast({cast_type}, {func_call}({comment_part}"
                lines[i] = new_first

                # 最后一行：需要多加一个 )
                last_line = args_lines[-1]
                # 找到最后一个 ) 并在后面加一个 )
                last_paren_idx = last_line.rfind(")")
                if last_paren_idx >= 0:
                    lines[j] = last_line[: last_paren_idx + 1] + ")" + last_line[last_paren_idx + 1 :]

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
