from __future__ import annotations

from datetime import datetime
from uuid import UUID

from ninja import Schema

class JobSubmitOut(Schema):
    job_id: str
    status: str
    total_files: int

class ItemOut(Schema):
    id: UUID
    original_name: str
    status: str
    error: str
    duration_ms: float | None = None

class JobOut(Schema):
    id: UUID
    status: str
    total_files: int
    converted_files: int
    failed_files: int
    progress: int
    error_message: str
    download_url: str = ""
    created_at: datetime | None = None
    finished_at: datetime | None = None

class JobProgressOut(Schema):
    job: JobOut
    items: list[ItemOut]

class HealthOut(Schema):
    libreoffice_available: bool
    libreoffice_path: str | None = None

class SaveToDirIn(Schema):
    target_dir: str

class SaveToDirOut(Schema):
    saved_files: list[str]
    total_saved: int
    target_dir: str
