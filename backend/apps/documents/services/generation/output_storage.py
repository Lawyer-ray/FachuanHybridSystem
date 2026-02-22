"""Business logic services."""

from __future__ import annotations

from apps.core.path import Path


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

    def save_bytes(self, *, relative_dir: str, filename: str, content: bytes) -> str:
        media_root = self.media_root
        target_dir = media_root / relative_dir
        target_dir.makedirs_p()

        file_path = target_dir / filename
        with file_path.open("wb") as f:
            f.write(content)

        return str(file_path.relative_to(media_root))

    def save_for_case(self, *, case_id: int, filename: str, content: bytes) -> str:
        return self.save_bytes(relative_dir=f"generated_documents/case_{case_id}", filename=filename, content=content)
