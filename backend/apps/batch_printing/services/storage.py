from __future__ import annotations

import shutil
from pathlib import Path
from uuid import UUID

from django.conf import settings
from django.core.files.base import ContentFile
from django.core.files.storage import default_storage

from apps.core.filesystem.upload_paths import MediaEntity


class BatchPrintStorage:
    def __init__(self, job_id: UUID | str) -> None:
        self._job_id = str(job_id)

    @property
    def job_root(self) -> Path:
        return Path(settings.MEDIA_ROOT) / MediaEntity.BATCH_PRINTING / "jobs" / self._job_id

    @property
    def source_dir(self) -> Path:
        return self.job_root / "source"

    @property
    def prepared_dir(self) -> Path:
        return self.job_root / "prepared"

    @property
    def artifacts_dir(self) -> Path:
        return self.job_root / "artifacts"

    def rel_path_of(self, path: Path) -> str:
        """把 job 目录内的绝对路径转换为 media 相对路径（供 default_storage 使用）。"""
        return path.relative_to(Path(settings.MEDIA_ROOT)).as_posix()

    def save_prepared(self, target_pdf: Path, content: bytes) -> None:
        """以覆盖语义写入准备打印的 PDF（重复执行任务时复用同名文件）。"""
        rel_path = self.rel_path_of(target_pdf)
        if default_storage.exists(rel_path):
            default_storage.delete(rel_path)
        default_storage.save(rel_path, ContentFile(content))

    def ensure_dirs(self) -> None:  # pragma: no cover
        for path in (self.source_dir, self.prepared_dir, self.artifacts_dir):
            path.mkdir(parents=True, exist_ok=True)

    def cleanup(self) -> None:  # pragma: no cover
        shutil.rmtree(self.job_root, ignore_errors=True)

    def source_file_path(self, *, order: int, filename: str) -> Path:
        return self.source_dir / f"{order:03d}_{filename}"

    def prepared_pdf_path(self, *, order: int, filename_stem: str) -> Path:
        return self.prepared_dir / f"{order:03d}_{filename_stem}.pdf"
