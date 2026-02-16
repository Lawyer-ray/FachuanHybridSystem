from __future__ import annotations

import argparse
import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, List, Sequence


@dataclass(frozen=True)
class GetterSpec:
    file_path: str
    getter_name: str
    builder_ref: str | None


DEF_RE = re.compile(r"^\s*def\s+(get_[a-zA-Z0-9_]+)\s*\(")
IMPORT_BUILDER_RE = re.compile(r"^\s*from\s+apps\.core\.dependencies\s+import\s+(?P<name>[a-zA-Z0-9_]+)")
GET_OR_CREATE_RE = re.compile(r'get_or_create\(\s*"[^"]+"\s*,\s*(?P<factory>[a-zA-Z0-9_\.]+|\blambda\b)')


def iter_files(root: Path, *, patterns: Sequence[str]) -> Iterable[Path]:
    for pattern in patterns:
        yield from root.glob(pattern)


def parse_file(path: Path) -> List[GetterSpec]:
    lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
    imported_builders: List[str] = []
    out: List[GetterSpec] = []
    current_getter: str | None = None
    current_builder: str | None = None

    for line in lines:
        m_import = IMPORT_BUILDER_RE.match(line)
        if m_import:
            imported_builders.append(m_import.group("name"))
            continue

        m_def = DEF_RE.match(line)
        if m_def:
            if current_getter:
                out.append(GetterSpec(file_path=str(path), getter_name=current_getter, builder_ref=current_builder))
            current_getter = m_def.group(1)
            current_builder = None
            continue

        if current_getter:
            m_factory = GET_OR_CREATE_RE.search(line)
            if m_factory:
                factory = m_factory.group("factory")
                if factory == "lambda":
                    current_builder = "lambda"
                else:
                    current_builder = factory

    if current_getter:
        out.append(GetterSpec(file_path=str(path), getter_name=current_getter, builder_ref=current_builder))
    return out


def main(argv: List[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", default=str(Path(__file__).resolve().parents[1] / "apps" / "core"))
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args(argv)

    root = Path(args.root).resolve()
    specs: List[GetterSpec] = []
    for p in iter_files(root, patterns=("service_locator_mixins/*.py",)):
        specs.extend(parse_file(p))

    specs.sort(key=lambda s: (s.getter_name, s.file_path))

    if args.json:
        print(json.dumps([s.__dict__ for s in specs], ensure_ascii=False, indent=2))
        return 0

    for s in specs:
        builder = s.builder_ref or "-"
        print(f"{s.getter_name:40s}  {builder:30s}  {s.file_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

