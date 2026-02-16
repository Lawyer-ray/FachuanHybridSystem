#!/usr/bin/env python3
import re
import sys
from typing import Iterable

from apps.core.path import Path

_PATTERN = re.compile(r"^(\s*)from\s+pathlib\s+import\s+Path(\s*(#.*)?)$")


def _iter_py_files(root: str) -> Iterable[str]:
    root_path = Path(root)
    for base in ["apps", "apiSystem", "scripts", "tests"]:
        d = root_path / base
        if d.isdir():
            for p in d.walkfiles("*.py"):
                parts = p.parts
                if "migrations" in parts or "__pycache__" in parts or ".pytest_cache" in parts:
                    continue
                yield str(p)


def main(argv: list[str]) -> int:
    root = Path(argv[1]) if len(argv) >= 2 else Path(__file__).parent.parent.parent
    root = root.abspath()

    exclude = {
        (root / "apiSystem" / "path.py").abspath(),
    }

    changed_files: list[str] = []
    changed_lines = 0

    for file_path in _iter_py_files(root):
        if Path(file_path).abspath() in exclude:
            continue

        try:
            content = Path(file_path).text(encoding="utf-8")
        except Exception:
            continue

        lines = content.splitlines(True)
        out: list[str] = []
        file_changed = False

        for line in lines:
            m = _PATTERN.match(line.rstrip("\n"))
            if m:
                indent, suffix = m.group(1), m.group(2) or ""
                out.append(f"{indent}from apps.core.path import Path{suffix}\n")
                file_changed = True
                changed_lines += 1
            else:
                out.append(line)

        if file_changed:
            try:
                Path(file_path).write_text("".join(out), encoding="utf-8")
            except Exception as e:
                print(f"failed to write: {file_path}: {e}", file=sys.stderr)
                return 2
            changed_files.append(str(file_path))

    print(f"updated_files={len(changed_files)} updated_lines={changed_lines}")
    for p in changed_files:
        print(p)
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
