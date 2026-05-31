"""批量分析任务 Schema"""

from __future__ import annotations

from datetime import datetime
from typing import Any
from uuid import UUID

from pydantic import BaseModel, field_validator

from apps.core.api.schemas import SchemaMixin

class BatchItemOut(BaseModel):
    id: UUID
    file_name: str
    status: str
    result: str
    error: str
    duration_ms: float | None

    model_config = {"from_attributes": True}

class BatchJobOut(SchemaMixin, BaseModel):
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
    detail_zip_file: str = ""
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

    @field_validator("summary_file", "detail_zip_file", mode="before")
    @classmethod
    def _resolve_file_field(cls, v: Any) -> str:
        if v is None:
            return ""
        result = SchemaMixin._get_file_url(v)
        return result or ""

    @staticmethod
    def resolve_created_at(obj: object) -> datetime | None:
        return SchemaMixin._resolve_datetime(getattr(obj, "created_at", None))

    @staticmethod
    def resolve_updated_at(obj: object) -> datetime | None:
        return SchemaMixin._resolve_datetime(getattr(obj, "updated_at", None))

    @staticmethod
    def resolve_started_at(obj: object) -> datetime | None:
        return SchemaMixin._resolve_datetime(getattr(obj, "started_at", None))

    @staticmethod
    def resolve_finished_at(obj: object) -> datetime | None:
        return SchemaMixin._resolve_datetime(getattr(obj, "finished_at", None))

    @staticmethod
    def resolve_started_processing_at(obj: object) -> datetime | None:
        return SchemaMixin._resolve_datetime(getattr(obj, "started_processing_at", None))

class BatchProgressOut(BaseModel):
    job: BatchJobOut
    items: list[BatchItemOut]
    failed_items_detail: list[dict[str, Any]] = []
