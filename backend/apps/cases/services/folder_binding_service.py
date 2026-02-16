"""Business logic services."""

from __future__ import annotations

from .template.folder_binding_service import CaseFolderBindingService as _ImplCaseFolderBindingService


class CaseFolderBindingService(_ImplCaseFolderBindingService):
    pass


__all__: list[str] = ["CaseFolderBindingService"]
