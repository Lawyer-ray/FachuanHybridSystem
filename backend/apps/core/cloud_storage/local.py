"""Local filesystem provider — wraps pathlib, zero behavior change."""

from __future__ import annotations

import os
from collections.abc import Iterator
from pathlib import Path

from .protocols import CloudFileInfo


class LocalProvider:
    """Read/write files on the local filesystem via pathlib."""

    def __init__(self, root: str = "/") -> None:
        self._root = Path(root)

    def _resolve(self, path: str) -> Path:
        resolved = (self._root / path).resolve()
        if not resolved.is_relative_to(self._root):
            raise OSError(f"路径逃逸: {path} 不在根目录 {self._root} 内")
        return resolved

    def list_directory(self, path: str) -> list[CloudFileInfo]:
        target = self._resolve(path)
        results: list[CloudFileInfo] = []
        try:
            for child in target.iterdir():
                try:
                    stat = child.stat()
                    results.append(
                        CloudFileInfo(
                            name=child.name,
                            path=str(child.relative_to(self._root)),
                            is_dir=child.is_dir(),
                            size=stat.st_size if child.is_file() else 0,
                            modified_at=stat.st_mtime,
                        )
                    )
                except (OSError, PermissionError):
                    continue
        except (OSError, PermissionError):
            return []
        results.sort(key=lambda x: x.name.lower())
        return results

    def read_file(self, path: str) -> bytes:
        target = self._resolve(path)
        return target.read_bytes()

    def write_file(self, path: str, content: bytes) -> None:
        target = self._resolve(path)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(content)

    def mkdir(self, path: str) -> None:
        target = self._resolve(path)
        target.mkdir(parents=True, exist_ok=True)

    def exists(self, path: str) -> bool:
        return self._resolve(path).exists()

    def is_dir(self, path: str) -> bool:
        return self._resolve(path).is_dir()

    def delete_file(self, path: str) -> None:
        target = self._resolve(path)
        if target.exists() and target.is_file():
            target.unlink()

    def get_file_info(self, path: str) -> CloudFileInfo | None:
        target = self._resolve(path)
        if not target.exists():
            return None
        try:
            stat = target.stat()
            return CloudFileInfo(
                name=target.name,
                path=str(target.relative_to(self._root)),
                is_dir=target.is_dir(),
                size=stat.st_size if target.is_file() else 0,
                modified_at=stat.st_mtime,
            )
        except (OSError, PermissionError):
            return None

    def walk(self, path: str) -> Iterator[tuple[str, list[str], list[CloudFileInfo]]]:
        target = self._resolve(path)
        for abs_root, dirs, files in os.walk(target):
            root_path = Path(abs_root)
            if not root_path.is_relative_to(self._root):
                break
            rel_root = str(root_path.relative_to(self._root))
            file_infos = []
            for f in files:
                fp = root_path / f
                try:
                    stat = fp.stat()
                    if not fp.is_relative_to(self._root):
                        continue
                    file_infos.append(
                        CloudFileInfo(
                            name=f,
                            path=str(fp.relative_to(self._root)),
                            is_dir=False,
                            size=stat.st_size,
                            modified_at=stat.st_mtime,
                        )
                    )
                except (OSError, PermissionError):
                    continue
            yield (rel_root, dirs, file_infos)
