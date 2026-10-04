from __future__ import annotations

from datetime import datetime
from uuid import UUID

from ninja import Field, Schema


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
    download_url: str = ""


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


class JobListOut(Schema):
    """历史任务分页列表（GET /doc-converter/jobs 实际返回形状）"""

    items: list[JobOut]
    count: int
    page: int
    num_pages: int


class ClipboardCopyOut(Schema):
    """转换产物复制到系统剪贴板结果（非 macOS 时 success=false / reason=unsupported）"""

    success: bool
    copied: int
    reason: str | None = None


class HealthOut(Schema):
    libreoffice_available: bool
    libreoffice_path: str | None = None


class CopyItemsIn(Schema):
    item_ids: list[UUID] = Field(..., min_length=1, description="要复制到系统剪贴板的转换项 ID")


class SaveToDirIn(Schema):
    target_dir: str


class SaveToDirOut(Schema):
    saved_files: list[str]
    total_saved: int
    target_dir: str
