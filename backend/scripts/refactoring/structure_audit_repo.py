from __future__ import annotations

import argparse
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, List, Optional, Sequence, Tuple


DEFAULT_EXCLUDE_DIR_NAMES = {
    ".git",
    ".mypy_cache",
    ".pytest_cache",
    ".hypothesis",
    ".tox",
    ".venv",
    "venv311",
    "venv312",
    "migrations",
    "static",
    "staticfiles",
    "media",
    "htmlcov",
    "__pycache__",
}


@dataclass(frozen=True)
class Finding:
    file: str
    line: int
    match: str


def _iter_files(root: Path, *, include_globs: Sequence[str], exclude_dir_names: set[str]) -> Iterable[Path]:
    includes = list(include_globs) or ["**/*.py"]
    seen: set[Path] = set()
    for pattern in includes:
        for p in root.glob(pattern):
            if not p.is_file():
                continue
            parts = set(p.parts)
            if parts & exclude_dir_names:
                continue
            if p in seen:
                continue
            seen.add(p)
            yield p


def _scan_file(path: Path, *, patterns: Sequence[re.Pattern[str]]) -> List[Finding]:
    try:
        text = path.read_text(encoding="utf-8", errors="ignore")
    except Exception:
        return []

    findings: List[Finding] = []
    for idx, line in enumerate(text.splitlines(), start=1):
        for pat in patterns:
            m = pat.search(line)
            if not m:
                continue
            findings.append(Finding(file=str(path), line=idx, match=m.group(0)))
    return findings


def _guess_app_name(path: Path) -> Optional[str]:
    parts = list(path.parts)
    try:
        idx = parts.index("apps")
    except ValueError:
        return None
    if idx + 1 >= len(parts):
        return None
    return parts[idx + 1]


def _scan_cross_app_model_imports(path: Path, *, pattern: re.Pattern[str]) -> List[Finding]:
    try:
        text = path.read_text(encoding="utf-8", errors="ignore")
    except Exception:
        return []

    file_app = _guess_app_name(path)
    if not file_app:
        return []

    findings: List[Finding] = []
    for idx, line in enumerate(text.splitlines(), start=1):
        m = pattern.search(line)
        if not m:
            continue
        imported_app = m.group("app")
        if imported_app and imported_app != file_app:
            findings.append(Finding(file=str(path), line=idx, match=m.group(0)))
    return findings


def _count_by_file(findings: Sequence[Finding]) -> List[Tuple[str, int]]:
    counts: dict[str, int] = {}
    for f in findings:
        counts[f.file] = counts.get(f.file, 0) + 1
    return sorted(counts.items(), key=lambda x: (-x[1], x[0]))


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", default=".", help="repo root (default: current directory)")
    parser.add_argument(
        "--include",
        action="append",
        default=[],
        help="glob pattern to include (repeatable). default: **/*.py",
    )
    parser.add_argument(
        "--exclude-dir",
        action="append",
        default=[],
        help="directory name to exclude (repeatable)",
    )
    args = parser.parse_args(argv)

    root = Path(args.root).resolve()
    exclude = set(DEFAULT_EXCLUDE_DIR_NAMES) | set(args.exclude_dir or [])

    todo_patterns = [
        re.compile(r"\bTODO\b"),
        re.compile(r"\bFIXME\b"),
        re.compile(r"\bXXX\b"),
        re.compile(r"\bHACK\b"),
    ]
    print_patterns = [
        re.compile(r"\bprint\("),
        re.compile(r"\bpprint\("),
    ]
    model_import_any_app_pattern = re.compile(r"^\s*from\s+apps\.(?P<app>[a-zA-Z0-9_]+)\.models\s+import\s+")

    todo_findings: List[Finding] = []
    print_findings: List[Finding] = []
    cross_import_findings: List[Finding] = []
    model_import_findings: List[Finding] = []

    for file_path in _iter_files(root, include_globs=args.include, exclude_dir_names=exclude):
        todo_findings.extend(_scan_file(file_path, patterns=todo_patterns))
        print_findings.extend(_scan_file(file_path, patterns=print_patterns))
        model_import_findings.extend(_scan_file(file_path, patterns=[model_import_any_app_pattern]))
        cross_import_findings.extend(_scan_cross_app_model_imports(file_path, pattern=model_import_any_app_pattern))

    print("# Backend Repo Audit Report")
    print()
    print(f"- root: {root}")
    print(f"- include: {args.include or ['**/*.py']}")
    print(f"- excluded_dir_names: {sorted(exclude)}")
    print()

    def render_section(title: str, findings: Sequence[Finding]) -> None:
        by_file = _count_by_file(findings)
        print(f"## {title}")
        print()
        print(f"- total_occurrences: {len(findings)}")
        print(f"- files_with_matches: {len(by_file)}")
        print()
        if not by_file:
            return
        print("| file | count |")
        print("|---|---:|")
        for file, count in by_file[:50]:
            print(f"| {file} | {count} |")
        if len(by_file) > 50:
            print()
            print(f"- truncated_files: {len(by_file) - 50}")
        print()

    render_section("TODO/FIXME/XXX/HACK", todo_findings)
    render_section("print/pprint", print_findings)
    render_section("Model imports (from apps.<x>.models import ...)", model_import_findings)
    render_section("Cross-app model imports (from apps.<other>.models import ...)", cross_import_findings)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
