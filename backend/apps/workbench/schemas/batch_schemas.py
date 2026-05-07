"""批量分析任务 Schema"""

from __future__ import annotations

from datetime import datetime
from typing import Any
from uuid import UUID

from pydantic import BaseModel, field_validator


class BatchItemOut(BaseModel):
    id: UUID
    file_name: str
    status: str
    result: str
    error: str
    duration_ms: float | None

    model_config = {"from_attributes": True}


class BatchJobOut(BaseModel):
    id: UUID
    session_id: int
    job_type: str
    status: str
    prompt: str
    llm_model: str
    total_items: int
    completed_items: int
    failed_items: int
    progress: int
    summary: str
    summary_file: str = ""
    error_message: str
    created_at: datetime | None = None
    updated_at: datetime | None = None
    started_at: datetime | None = None
    finished_at: datetime | None = None
    started_processing_at: datetime | None = None

    # 计算字段
    eta_seconds: float | None = None
    speed_per_minute: float = 0.0

    model_config = {"from_attributes": True}

    @field_validator("summary_file", mode="before")
    @classmethod
    def _resolve_summary_file(cls, v: object) -> str:
        if v and hasattr(v, "url"):
            try:
                return str(v.url)
            except ValueError:
                return ""
        return ""


class BatchProgressOut(BaseModel):
    job: BatchJobOut
    items: list[BatchItemOut]
    failed_items_detail: list[dict[str, Any]] = []
