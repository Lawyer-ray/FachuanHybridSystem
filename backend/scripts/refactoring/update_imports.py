#!/usr/bin/env python3
"""Import path updater utilities.

This module keeps a lightweight implementation of the updater API expected by
the structure tests and developer tooling.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class ImportUpdate:
    file_path: Path
    line_no: int
    original_line: str
    updated_line: str


class ImportPathUpdater:
    """Scans python files and computes import-path rewrite candidates."""

    def __init__(self, project_root: Path, dry_run: bool = True) -> None:
        self.project_root = project_root
        self.dry_run = dry_run
        self.import_patterns: list[tuple[str, str, str]] = [
            ("tests_factories", r"\btests\.factories\b", "tests.factories"),
            ("tests_unit", r"\btests\.unit\b", "tests.unit"),
            ("tests_mocks", r"\btests\.mocks\b", "tests.mocks"),
        ]
        self._updates: dict[Path, list[ImportUpdate]] = {}

    def scan_python_files(self) -> list[Path]:
        python_files: list[Path] = []
        for py_file in self.project_root.rglob("*.py"):
            parts = set(py_file.parts)
            if "__pycache__" in parts or "migrations" in parts:
                continue
            if ".venv" in parts or "venv" in parts or ".git" in parts:
                continue
            python_files.append(py_file)
        return python_files

    def analyze_file(self, file_path: Path) -> list[ImportUpdate]:
        try:
            content = file_path.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            return []

        updates: list[ImportUpdate] = []
        for idx, line in enumerate(content.splitlines(keepends=True), start=1):
            updated_line = line
            for _, old_pattern, new_pattern in self.import_patterns:
                updated_line = re.sub(old_pattern, new_pattern, updated_line)
            if updated_line != line:
                updates.append(
                    ImportUpdate(
                        file_path=file_path,
                        line_no=idx,
                        original_line=line,
                        updated_line=updated_line,
                    )
                )
        return updates

    def scan_all_files(self) -> list[ImportUpdate]:
        all_updates: list[ImportUpdate] = []
        self._updates = {}
        for py_file in self.scan_python_files():
            updates = self.analyze_file(py_file)
            if updates:
                self._updates[py_file] = updates
                all_updates.extend(updates)
        return all_updates

    def apply_updates(self) -> int:
        if self.dry_run:
            return sum(len(items) for items in self._updates.values())

        updated_count = 0
        for file_path, updates in self._updates.items():
            if not updates:
                continue
            lines = file_path.read_text(encoding="utf-8").splitlines(keepends=True)
            for item in updates:
                index = item.line_no - 1
                if 0 <= index < len(lines):
                    lines[index] = item.updated_line
            file_path.write_text("".join(lines), encoding="utf-8")
            updated_count += len(updates)
        return updated_count
