from __future__ import annotations

import json
import shutil
from pathlib import Path
from uuid import UUID

from django.conf import settings


class PdfSplitStorage:
    def __init__(self, job_id: UUID | str) -> None:
        self._job_id = str(job_id)

    @property
    def job_root(self) -> Path:
        return Path(settings.MEDIA_ROOT) / "pdf_splitting" / "jobs" / self._job_id

    @property
    def source_dir(self) -> Path:
        return self.job_root / "source"

    @property
    def analysis_dir(self) -> Path:
        return self.job_root / "analysis"

    @property
    def previews_dir(self) -> Path:
        return self.job_root / "previews"

    @property
    def exports_dir(self) -> Path:
        return self.job_root / "exports"

    @property
    def source_pdf_path(self) -> Path:
        return self.source_dir / "original.pdf"

    @property
    def pages_json_path(self) -> Path:
        return self.analysis_dir / "pages.json"

    @property
    def segments_json_path(self) -> Path:
        return self.analysis_dir / "segments.json"

    @property
    def export_zip_path(self) -> Path:
        return self.exports_dir / "split_result.zip"

    def ensure_dirs(self) -> None:
        for path in (self.source_dir, self.analysis_dir, self.previews_dir, self.exports_dir):
            path.mkdir(parents=True, exist_ok=True)

    def cleanup(self) -> None:
        shutil.rmtree(self.job_root, ignore_errors=True)

    def write_json(self, path: Path, payload: object) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")

    def read_json(self, path: Path, default: object) -> object:
        if not path.exists():
            return default
        return json.loads(path.read_text(encoding="utf-8"))

    def preview_path(self, page_no: int) -> Path:
        return self.previews_dir / f"page_{page_no:03d}.png"

    def export_pdf_path(self, filename: str) -> Path:
        return self.exports_dir / filename
