from __future__ import annotations

import argparse
import os
import subprocess
import sys
from pathlib import Path


def _find_backend_root(start: Path) -> Path:
    for candidate in [start, *start.parents]:
        if (candidate / "apps").is_dir() and (candidate / "apiSystem" / "manage.py").is_file():
            return candidate
    raise RuntimeError("Cannot locate backend root (expected apps/ and apiSystem/manage.py)")


def _archive_dir(backend_root: Path) -> Path:
    return backend_root / "devtools" / "_archive" / "mypy_fix_20260210"


def _iter_archive_files(archive_dir: Path) -> list[Path]:
    if not archive_dir.is_dir():
        return []
    files = [p for p in archive_dir.iterdir() if p.is_file()]
    files.sort(key=lambda p: p.name)
    return files


def cmd_list(archive_dir: Path) -> int:
    files = _iter_archive_files(archive_dir)
    if not files:
        print("No archived fix scripts found.")
        return 0
    for p in files:
        print(p.name)
    return 0


def cmd_path(archive_dir: Path, name: str) -> int:
    target = archive_dir / name
    if not target.exists():
        print(f"Not found: {name}", file=sys.stderr)
        return 2
    print(str(target.resolve()))
    return 0


def cmd_run(backend_root: Path, archive_dir: Path, name: str, dangerously_run: bool, passthrough: list[str]) -> int:
    if not dangerously_run:
        print("Refusing to run archived fix scripts without --dangerously-run.", file=sys.stderr)
        return 2

    target = archive_dir / name
    if not target.exists():
        print(f"Not found: {name}", file=sys.stderr)
        return 2

    env = os.environ.copy()
    env.setdefault("PYTHONPATH", "apiSystem:.")  # consistent with Makefile typecheck gate

    if target.suffix == ".py":
        argv = [sys.executable, str(target), *passthrough]
    elif target.suffix == ".sh":
        argv = ["bash", str(target), *passthrough]
    else:
        print(f"Unsupported script type: {name}", file=sys.stderr)
        return 2

    completed = subprocess.run(argv, cwd=str(backend_root), env=env, check=False)
    return completed.returncode


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="devtools.mypy_fixes", add_help=True)
    subparsers = parser.add_subparsers(dest="command", required=True)

    subparsers.add_parser("list")

    p_path = subparsers.add_parser("path")
    p_path.add_argument("name")

    p_run = subparsers.add_parser("run")
    p_run.add_argument("name")
    p_run.add_argument("--dangerously-run", action="store_true")
    p_run.add_argument("args", nargs=argparse.REMAINDER)

    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    ns = parser.parse_args(argv)

    backend_root = _find_backend_root(Path(__file__).resolve())
    archive_dir = _archive_dir(backend_root)

    if ns.command == "list":
        return cmd_list(archive_dir)
    if ns.command == "path":
        return cmd_path(archive_dir, ns.name)
    if ns.command == "run":
        passthrough = ns.args
        if passthrough and passthrough[0] == "--":
            passthrough = passthrough[1:]
        return cmd_run(backend_root, archive_dir, ns.name, ns.dangerously_run, passthrough)

    print(f"Unknown command: {ns.command}", file=sys.stderr)
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
