from __future__ import annotations

import argparse
import json
import os
import re
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Iterable, List, Sequence


@dataclass(frozen=True)
class FileMetrics:
    path: str
    line_count: int
    service_locator_hits: int
    cross_app_import_hits: int
    filesystem_io_hits: int

    @property
    def score(self) -> int:
        return (
            self.line_count
            + (self.service_locator_hits * 40)
            + (self.cross_app_import_hits * 80)
            + (self.filesystem_io_hits * 20)
        )


SERVICE_LOCATOR_RE = re.compile(r"\bServiceLocator\.")
APPS_IMPORT_RE = re.compile(r"^\s*(from|import)\s+apps\.(?P<app>[a-zA-Z0-9_]+)\b")
FILESYSTEM_IO_RE = re.compile(r"\b(open|Path|os\.path|shutil\.)\b")


def iter_python_files(root: Path, *, exclude_dirs: Sequence[str]) -> Iterable[Path]:
    exclude_set = set(exclude_dirs)
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = [d for d in dirnames if d not in exclude_set]
        for filename in filenames:
            if filename.endswith(".py"):
                yield Path(dirpath) / filename


def read_text(path: Path) -> str:
    return path.read_text(encoding="utf-8", errors="replace")


def compute_metrics(path: Path) -> FileMetrics:
    text = read_text(path)
    line_count = text.count("\n") + 1 if text else 0
    service_locator_hits = len(SERVICE_LOCATOR_RE.findall(text))
    cross_app_import_hits = 0
    for line in text.splitlines():
        m = APPS_IMPORT_RE.match(line)
        if not m:
            continue
        if m.group("app") != "core":
            cross_app_import_hits += 1
    filesystem_io_hits = len(FILESYSTEM_IO_RE.findall(text))
    return FileMetrics(
        path=str(path),
        line_count=line_count,
        service_locator_hits=service_locator_hits,
        cross_app_import_hits=cross_app_import_hits,
        filesystem_io_hits=filesystem_io_hits,
    )


def main(argv: List[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", default=str(Path(__file__).resolve().parents[1] / "apps"))
    parser.add_argument("--top", type=int, default=40)
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args(argv)

    root = Path(args.root).resolve()
    metrics = [
        compute_metrics(p)
        for p in iter_python_files(
            root,
            exclude_dirs=(
                "__pycache__",
                "migrations",
                ".venv",
                "venv",
                "venv311",
                "venv312",
            ),
        )
    ]
    metrics.sort(key=lambda m: (m.score, m.line_count), reverse=True)
    top = metrics[: max(args.top, 1)]

    if args.json:
        print(json.dumps([asdict(m) | {"score": m.score} for m in top], ensure_ascii=False, indent=2))
        return 0

    for m in top:
        print(
            f"{m.score:6d}  {m.line_count:5d}  sl={m.service_locator_hits:3d}  xapp={m.cross_app_import_hits:3d}  io={m.filesystem_io_hits:3d}  {m.path}"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
