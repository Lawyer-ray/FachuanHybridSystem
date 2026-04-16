from __future__ import annotations

import shutil
from pathlib import Path
from uuid import UUID

from django.conf import settings


class BatchPrintStorage:
    def __init__(self, job_id: UUID | str) -> None:
        self._job_id = str(job_id)

    @property
    def job_root(self) -> Path:
        return Path(settings.MEDIA_ROOT) / "batch_printing" / "jobs" / self._job_id

    @property
    def source_dir(self) -> Path:
        return self.job_root / "source"

    @property
    def prepared_dir(self) -> Path:
        return self.job_root / "prepared"

    @property
    def artifacts_dir(self) -> Path:
        return self.job_root / "artifacts"

    def ensure_dirs(self) -> None:
        for path in (self.source_dir, self.prepared_dir, self.artifacts_dir):
            path.mkdir(parents=True, exist_ok=True)

    def cleanup(self) -> None:
        shutil.rmtree(self.job_root, ignore_errors=True)

    def source_file_path(self, *, order: int, filename: str) -> Path:
        return self.source_dir / f"{order:03d}_{filename}"

    def prepared_pdf_path(self, *, order: int, filename_stem: str) -> Path:
        return self.prepared_dir / f"{order:03d}_{filename_stem}.pdf"
