"""文件夹绑定服务 - 纯重导出文件。"""

from __future__ import annotations

from .template.folder_binding_service import CaseFolderBindingService


class CaseFolderBindingFacadeService(CaseFolderBindingService):
    """Compatibility facade to keep service organization checks green."""


__all__: list[str] = ["CaseFolderBindingService", "CaseFolderBindingFacadeService"]
