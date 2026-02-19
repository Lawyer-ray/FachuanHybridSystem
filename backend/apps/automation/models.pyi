"""Type stubs for automation models - Django ORM dynamic attributes"""

from datetime import datetime
from typing import Any

from django.db import models
from django.db.models import Manager

class ScraperTask(models.Model):
    id: int
    task_type: str
    status: str
    priority: int
    url: str
    case_id: int | None
    config: dict[str, Any]
    result: dict[str, Any] | None
    error_message: str | None
    retry_count: int
    max_retries: int
    created_at: datetime
    updated_at: datetime
    started_at: datetime | None
    finished_at: datetime | None
    scheduled_at: datetime | None

    documents: Manager[CourtDocument]
    court_sms_records: Manager[CourtSMS]

    pk: int

class CourtSMS(models.Model):
    id: int
    content: str
    received_at: datetime
    sms_type: str | None
    download_links: list[str]
    case_numbers: list[str]
    party_names: list[str]
    status: str
    error_message: str | None
    retry_count: int
    scraper_task_id: int | None
    case_id: int | None
    case_log_id: int | None
    feishu_sent_at: datetime | None
    feishu_error: str | None
    created_at: datetime
    updated_at: datetime

    pk: int

class CourtDocument(models.Model):
    id: int
    scraper_task_id: int
    case_id: int | None
    c_sdbh: str
    c_stbh: str
    wjlj: str
    c_wsbh: str
    c_wsmc: str
    c_fybh: str
    c_fymc: str
    c_wjgs: str
    dt_cjsj: datetime
    download_status: str
    local_file_path: str | None
    file_size: int | None
    error_message: str | None
    created_at: datetime
    updated_at: datetime
    downloaded_at: datetime | None

    pk: int

class DocumentRecognitionTask(models.Model):
    id: int
    file_path: str
    original_filename: str
    status: str
    document_type: str | None
    case_number: str | None
    key_time: datetime | None
    confidence: float | None
    extraction_method: str | None
    raw_text: str | None
    renamed_file_path: str | None
    binding_success: bool | None
    case_id: int | None
    case_log_id: int | None
    binding_message: str | None
    binding_error_code: str | None
    error_message: str | None
    notification_sent: bool
    notification_sent_at: datetime | None
    notification_error: str | None
    notification_file_sent: bool
    created_at: datetime
    started_at: datetime | None
    finished_at: datetime | None

    pk: int
