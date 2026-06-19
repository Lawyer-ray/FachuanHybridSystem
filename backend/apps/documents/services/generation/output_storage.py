"""Business logic services."""

from __future__ import annotations

from django.core.files.base import ContentFile
from django.core.files.storage import default_storage

from apps.core.utils.path import Path


class GeneratedDocumentStorage:
    def __init__(self, media_root: str | None = None) -> None:
        self._media_root = media_root

    @property
    def media_root(self) -> Path:
        if self._media_root:
            return Path(self._media_root)
        from apps.core.config import get_config

        value = get_config("django.media_root", None)
        if not value:
            raise RuntimeError("GeneratedDocumentStorage.media_root 未配置")
        return Path(str(value))

    def save_bytes(self, *, relative_dir: str, filename: str, content: bytes) -> str:  # pragma: no cover
        rel_path = f"{relative_dir}/{filename}"
        saved_name = default_storage.save(rel_path, ContentFile(content))
        return saved_name

    def save_for_case(self, *, case_id: int, filename: str, content: bytes) -> str:
        return self.save_bytes(relative_dir=f"generated_documents/case_{case_id}", filename=filename, content=content)
