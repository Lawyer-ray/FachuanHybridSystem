from __future__ import annotations

import argparse
import re
import subprocess
import sys
from pathlib import Path
from typing import Iterable, List, Sequence

TODO_PATTERN = re.compile(r"(^|\s)#\s*(TODO|FIXME)\b")


def _run(cmd: Sequence[str]) -> str:
    completed = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    if completed.returncode != 0:
        raise RuntimeError(completed.stderr.strip() or "command failed")
    return completed.stdout


def _iter_added_lines_for_files(files: Sequence[str]) -> Iterable[tuple[str, int, str]]:
    if not files:
        return
    git_root = _run(["git", "rev-parse", "--show-toplevel"]).strip()
    cmd = ["git", "-C", git_root, "diff", "--cached", "-U0", "--no-color", "--"] + list(files)
    diff = _run(cmd)

    current_file: str | None = None
    new_line_no: int | None = None
    for raw in diff.splitlines():
        if raw.startswith("+++ b/"):
            current_file = raw[len("+++ b/") :].strip()
            continue
        if raw.startswith("@@ "):
            try:
                hunk = raw.split(" ")[2]
                plus_part = hunk.split(",")[0]
                new_line_no = int(plus_part[1:])
            except Exception:
                new_line_no = None
            continue
        if current_file is None or new_line_no is None:
            continue

        if raw.startswith("+") and not raw.startswith("+++"):
            yield current_file, new_line_no, raw[1:]
            new_line_no += 1
            continue
        if raw.startswith("-") and not raw.startswith("---"):
            continue
        if raw.startswith(" "):
            new_line_no += 1


def _is_target_python_file(path: str) -> bool:
    if not path.endswith(".py"):
        return False
    if not path.startswith("backend/"):
        return False
    for banned in (
        "/migrations/",
        "/static/",
        "/staticfiles/",
        "/media/",
        "/venv311/",
        "/venv312/",
        "/.venv/",
        "/tests/",
        "/scripts/",
    ):
        if banned in path:
            return False
    return True


def _check_todo(files: Sequence[str]) -> List[str]:
    errors: List[str] = []
    for file, line_no, line in _iter_added_lines_for_files(files):
        if not _is_target_python_file(file):
            continue
        if TODO_PATTERN.search(line):
            errors.append(f"{file}:{line_no}: 新增 {line.strip()}")
    return errors


def _check_print(files: Sequence[str]) -> List[str]:
    errors: List[str] = []
    for file, line_no, line in _iter_added_lines_for_files(files):
        if not _is_target_python_file(file):
            continue
        stripped = line.strip()
        if "print(" in stripped or "pprint(" in stripped:
            errors.append(f"{file}:{line_no}: 新增 {stripped}")
    return errors


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--check", choices=("todo", "print"), required=True)
    parser.add_argument("files", nargs="*")
    args = parser.parse_args(argv)

    files = [str(Path(f)) for f in (args.files or [])]
    if args.check == "todo":
        errors = _check_todo(files)
        title = "禁止新增 TODO/FIXME/XXX/HACK（请改为任务单/issue，或直接完成并移除标记）"
    else:
        errors = _check_print(files)
        title = "禁止新增 print/pprint（请使用 logger，并按需带 extra 字段）"

    if not errors:
        return 0

    sys.stderr.write(title + "\n")
    for e in errors:
        sys.stderr.write("  " + e + "\n")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
