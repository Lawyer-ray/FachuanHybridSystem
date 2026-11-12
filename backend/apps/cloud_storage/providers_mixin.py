"""Shared mixins for cloud storage providers."""

from __future__ import annotations

from collections.abc import Iterator
from typing import TYPE_CHECKING

from .protocols import CloudFileInfo

if TYPE_CHECKING:
    # 仅为类型检查声明子类契约；运行时子类由 protocols.CloudStorageProvider
    # 约束，此处不提供实现（mixin 不持有状态，也不做脚手架）。
    class _ListDirectoryContract:
        def list_directory(self, path: str) -> list[CloudFileInfo]:
            raise NotImplementedError

else:
    _ListDirectoryContract = object


class _RecursiveWalkMixin(_ListDirectoryContract):
    """Default ``walk()`` for providers whose ``list_directory`` handles every path.

    Subclasses must implement ``list_directory(path) -> list[CloudFileInfo]``.
    Yields ``(dirpath, subdir_names, files)`` for the given path, then recurses
    into each subdirectory. Paths are joined with ``/`` relative to the root
    argument, so a trailing slash on the argument is ignored.
    """

    def walk(self, path: str) -> Iterator[tuple[str, list[str], list[CloudFileInfo]]]:
        """Recursively walk a directory tree, yielding (dirpath, subdir_names, files)."""
        children = self.list_directory(path)
        subdirs = [c.name for c in children if c.is_dir]
        files = [c for c in children if not c.is_dir]
        yield (path, subdirs, files)
        for subdir in subdirs:
            sub_path = f"{path.rstrip('/')}/{subdir}"
            yield from self.walk(sub_path)
