from __future__ import annotations

import shutil
from pathlib import Path
from uuid import UUID

from django.conf import settings

class DocConverterStorage:
    def __init__(self, job_id: UUID | str) -> None:
        self._job_id = str(job_id)

    @property
    def job_root(self) -> Path:
        return Path(settings.MEDIA_ROOT) / "doc_converter" / "jobs" / self._job_id

    @property
    def source_dir(self) -> Path:
        return self.job_root / "source"

    @property
    def output_dir(self) -> Path:
        return self.job_root / "output"

    @property
    def exports_dir(self) -> Path:
        return self.job_root / "exports"

    @property
    def export_zip_path(self) -> Path:
        return self.exports_dir / "converted.zip"

    def ensure_dirs(self) -> None:
        for path in (self.source_dir, self.output_dir, self.exports_dir):
            path.mkdir(parents=True, exist_ok=True)

    def cleanup(self) -> None:
        shutil.rmtree(self.job_root, ignore_errors=True)
