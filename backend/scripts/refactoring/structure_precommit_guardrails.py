"""Pre-commit guardrail: 检查新增的 TODO 标记或 print/pprint 调用。"""

from __future__ import annotations

import argparse
import ast
import subprocess
import sys
from pathlib import Path


def get_added_lines(filepath: str) -> list[tuple[int, str]]:
    """返回 git diff 中新增的行 (行号, 内容)。"""
    result = subprocess.run(
        ["git", "diff", "--cached", "-U0", "--", filepath],
        capture_output=True,
        text=True,
    )
    lines: list[tuple[int, str]] = []
    current_line = 0
    for line in result.stdout.splitlines():
        if line.startswith("@@"):
            # @@ -a,b +c,d @@
            parts = line.split("+")
            if len(parts) >= 2:
                try:
                    current_line = int(parts[1].split(",")[0].split()[0]) - 1
                except ValueError:
                    pass
        elif line.startswith("+") and not line.startswith("+++"):
            current_line += 1
            lines.append((current_line, line[1:]))
        elif not line.startswith("-"):
            current_line += 1
    return lines


def check_todo(filepath: str) -> list[str]:
    errors: list[str] = []
    for lineno, content in get_added_lines(filepath):
        if "TODO" in content or "FIXME" in content:
            errors.append(f"{filepath}:{lineno}: 新增了 TODO/FIXME 标记")
    return errors


def check_print(filepath: str) -> list[str]:
    errors: list[str] = []
    try:
        source = Path(filepath).read_text(encoding="utf-8")
        tree = ast.parse(source, filename=filepath)
    except (SyntaxError, OSError):
        return errors

    added_linenos = {ln for ln, _ in get_added_lines(filepath)}
    for node in ast.walk(tree):
        if isinstance(node, ast.Call):
            func = node.func
            name = ""
            if isinstance(func, ast.Name):
                name = func.id
            elif isinstance(func, ast.Attribute):
                name = func.attr
            if name in ("print", "pprint") and node.lineno in added_linenos:
                errors.append(f"{filepath}:{node.lineno}: 新增了 {name}() 调用，请改用 logger")
    return errors


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--check", choices=["todo", "print"], required=True)
    parser.add_argument("files", nargs="*")
    args = parser.parse_args()

    all_errors: list[str] = []
    for filepath in args.files:
        if args.check == "todo":
            all_errors.extend(check_todo(filepath))
        else:
            all_errors.extend(check_print(filepath))

    if all_errors:
        for err in all_errors:
            print(err)
        sys.exit(1)


if __name__ == "__main__":
    main()
