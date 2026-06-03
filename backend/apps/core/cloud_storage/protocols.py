"""Cloud storage provider protocol and shared data types."""

from __future__ import annotations

from collections.abc import Iterator
from dataclasses import dataclass
from typing import Protocol, runtime_checkable


@dataclass(frozen=True)
class CloudFileInfo:
    """Unified file/directory metadata returned by all providers."""

    name: str
    path: str
    is_dir: bool
    size: int
    modified_at: float


@runtime_checkable
class CloudStorageProvider(Protocol):
    """Protocol that all storage providers (local, WebDAV, OneDrive) must implement."""

    def list_directory(self, path: str) -> list[CloudFileInfo]:
        """List immediate children of a directory."""
        ...

    def read_file(self, path: str) -> bytes:
        """Read entire file content."""
        ...

    def write_file(self, path: str, content: bytes) -> None:
        """Write bytes to a file, creating parent directories as needed."""
        ...

    def mkdir(self, path: str) -> None:
        """Create a directory (including intermediate parents)."""
        ...

    def exists(self, path: str) -> bool:
        """Check whether a path exists."""
        ...

    def is_dir(self, path: str) -> bool:
        """Check whether a path is a directory."""
        ...

    def delete_file(self, path: str) -> None:
        """Delete a file."""
        ...

    def get_file_info(self, path: str) -> CloudFileInfo | None:
        """Return metadata for a single path, or None if not found."""
        ...

    def walk(self, path: str) -> Iterator[tuple[str, list[str], list[CloudFileInfo]]]:
        """Recursively walk a directory tree, yielding (dirpath, subdir_names, files)."""
        ...
