"""Business logic services."""

from __future__ import annotations

from apps.core.filesystem.filesystem_service import FolderFilesystemService as _ImplFolderFilesystemService


class FolderFilesystemService(_ImplFolderFilesystemService):
    pass


__all__: list[str] = ["FolderFilesystemService"]
