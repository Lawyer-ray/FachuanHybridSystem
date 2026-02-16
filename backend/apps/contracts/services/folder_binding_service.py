"""Business logic services."""

from __future__ import annotations

from .folder.folder_binding_service import FolderBindingService as _ImplFolderBindingService


class FolderBindingService(_ImplFolderBindingService):
    pass


__all__: list[str] = ["FolderBindingService"]
