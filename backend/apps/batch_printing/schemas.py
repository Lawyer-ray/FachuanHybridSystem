from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field


class CapabilityOut(BaseModel):
    docx_supported: bool
    docx_converter: str


class PresetSyncOut(BaseModel):
    discovered: int
    upserted: int


class PrintPresetSnapshotOut(BaseModel):
    id: int
    printer_name: str
    printer_display_name: str
    preset_name: str
    preset_source: str
    raw_settings_payload: dict[str, Any] = Field(default_factory=dict)
    executable_options_payload: dict[str, Any] = Field(default_factory=dict)
    supported_option_names: list[str] = Field(default_factory=list)
    rule_count: int = 0
    last_synced_at: datetime
    created_at: datetime
    updated_at: datetime


class PrintKeywordRuleIn(BaseModel):
    keyword: str
    priority: int = 100
    enabled: bool = True
    preset_snapshot_id: int
    notes: str = ""


class PrintKeywordRuleUpdateIn(BaseModel):
    keyword: str | None = None
    priority: int | None = None
    enabled: bool | None = None
    preset_snapshot_id: int | None = None
    notes: str | None = None


class PrintKeywordRuleOut(BaseModel):
    id: int
    keyword: str
    priority: int
    enabled: bool
    printer_name: str
    preset_snapshot_id: int
    preset_snapshot_name: str
    preset_printer_name: str
    notes: str
    created_at: datetime
    updated_at: datetime


class BatchPrintSubmitOut(BaseModel):
    job_id: str
    status: str


class BatchPrintItemOut(BaseModel):
    id: int
    order: int
    filename: str
    source_relpath: str
    prepared_relpath: str
    file_type: str
    status: str
    matched_rule_id: int | None = None
    matched_keyword: str
    target_preset_id: int | None = None
    target_printer_name: str
    target_preset_name: str
    cups_job_id: str
    error_message: str
    started_at: datetime | None = None
    finished_at: datetime | None = None


class BatchPrintJobSummaryOut(BaseModel):
    job_id: str
    status: str
    total_count: int
    processed_count: int
    success_count: int
    failed_count: int
    progress: int
    cancel_requested: bool
    task_id: str
    created_by_id: int | None = None
    created_by_name: str
    capability_payload: dict[str, Any] = Field(default_factory=dict)
    summary_payload: dict[str, Any] = Field(default_factory=dict)
    error_message: str
    created_at: datetime
    started_at: datetime | None = None
    finished_at: datetime | None = None


class BatchPrintJobOut(BatchPrintJobSummaryOut):
    items: list[BatchPrintItemOut] = Field(default_factory=list)
