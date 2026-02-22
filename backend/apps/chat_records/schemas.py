"""API schemas and serializers."""

from __future__ import annotations

import logging
from typing import Any, ClassVar

from ninja import ModelSchema, Schema

from apps.core.schemas import SchemaMixin

from .models import (
    ChatRecordExportTask,
    ChatRecordProject,
    ChatRecordRecording,
    ChatRecordScreenshot,
    ExportStatus,
    ExportType,
)

logger = logging.getLogger("apps.chat_records")


class ProjectIn(Schema):
    name: str
    description: str | None = ""


class ProjectOut(ModelSchema, SchemaMixin):
    created_at: str | None
    updated_at: str | None

    class Meta:
        model = ChatRecordProject
        fields: ClassVar = ["id", "name", "description", "created_by", "created_at", "updated_at"]

    @staticmethod
    def resolve_created_at(obj: ChatRecordProject) -> Any:
        return SchemaMixin._resolve_datetime_iso(getattr(obj, "created_at", None))

    @staticmethod
    def resolve_updated_at(obj: ChatRecordProject) -> Any:
        return SchemaMixin._resolve_datetime_iso(getattr(obj, "updated_at", None))


class ScreenshotOut(ModelSchema, SchemaMixin):
    image_url: str
    capture_time_seconds: float | None
    created_at: str | None

    class Meta:
        model = ChatRecordScreenshot
        fields: ClassVar = [
            "id",
            "project",
            "ordering",
            "title",
            "note",
            "capture_time_seconds",
            "sha256",
            "created_at",
        ]

    @staticmethod
    def resolve_image_url(obj: ChatRecordScreenshot) -> str:
        image = getattr(obj, "image", None)
        if not image:
            return ""
        try:
            return str(image.url)
        except Exception:
            logger.exception(
                "截图 URL 解析失败",
                extra={"screenshot_id": getattr(obj, "id", None)},
            )
            return ""

    @staticmethod
    def resolve_created_at(obj: ChatRecordScreenshot) -> Any:
        return SchemaMixin._resolve_datetime_iso(getattr(obj, "created_at", None))


class ScreenshotUpdate(Schema):
    title: str | None = None
    note: str | None = None


class ScreenshotReorderIn(Schema):
    screenshot_ids: list[str]


class RecordingUpdate(Schema):
    duration_seconds: float | None = None


class RecordingOut(ModelSchema, SchemaMixin):
    video_url: str
    stream_url: str
    extract_status_label: str
    created_at: str | None
    updated_at: str | None
    extract_started_at: str | None
    extract_finished_at: str | None

    class Meta:
        model = ChatRecordRecording
        fields: ClassVar = [
            "id",
            "project",
            "original_name",
            "size_bytes",
            "duration_seconds",
            "extract_status",
            "extract_progress",
            "extract_current",
            "extract_total",
            "extract_message",
            "extract_error",
            "extract_started_at",
            "extract_finished_at",
            "created_at",
            "updated_at",
        ]

    @staticmethod
    def resolve_video_url(obj: ChatRecordRecording) -> str:
        video = getattr(obj, "video", None)
        if not video:
            return ""
        try:
            return str(video.url)
        except Exception:
            logger.exception(
                "录屏 URL 解析失败",
                extra={"recording_id": getattr(obj, "id", None)},
            )
            return ""

    @staticmethod
    def resolve_stream_url(obj: ChatRecordRecording) -> str:
        return f"/api/v1/chat-records/recordings/{obj.id}/stream"

    @staticmethod
    def resolve_extract_status_label(obj: ChatRecordRecording) -> str:
        return SchemaMixin._get_display(obj, "extract_status") or ""

    @staticmethod
    def resolve_created_at(obj: ChatRecordRecording) -> Any:
        return SchemaMixin._resolve_datetime_iso(getattr(obj, "created_at", None))

    @staticmethod
    def resolve_updated_at(obj: ChatRecordRecording) -> Any:
        return SchemaMixin._resolve_datetime_iso(getattr(obj, "updated_at", None))

    @staticmethod
    def resolve_extract_started_at(obj: ChatRecordRecording) -> Any:
        return SchemaMixin._resolve_datetime_iso(getattr(obj, "extract_started_at", None))

    @staticmethod
    def resolve_extract_finished_at(obj: ChatRecordRecording) -> Any:
        return SchemaMixin._resolve_datetime_iso(getattr(obj, "extract_finished_at", None))


class ExportCreateIn(Schema):
    export_type: str
    layout: dict[str, Any] | None = None


class ExportTaskOut(ModelSchema, SchemaMixin):
    status_label: str
    export_type_label: str
    started_at: str | None
    finished_at: str | None
    created_at: str | None
    updated_at: str | None
    download_url: str | None

    class Meta:
        model = ChatRecordExportTask
        fields: ClassVar = [
            "id",
            "project",
            "export_type",
            "layout",
            "status",
            "progress",
            "current",
            "total",
            "message",
            "error",
            "started_at",
            "finished_at",
            "created_at",
            "updated_at",
        ]

    @staticmethod
    def resolve_status_label(obj: ChatRecordExportTask) -> str:
        return SchemaMixin._get_display(obj, "status") or ""

    @staticmethod
    def resolve_export_type_label(obj: ChatRecordExportTask) -> str:
        return SchemaMixin._get_display(obj, "export_type") or ""

    @staticmethod
    def resolve_started_at(obj: ChatRecordExportTask) -> Any:
        return SchemaMixin._resolve_datetime_iso(getattr(obj, "started_at", None))

    @staticmethod
    def resolve_finished_at(obj: ChatRecordExportTask) -> Any:
        return SchemaMixin._resolve_datetime_iso(getattr(obj, "finished_at", None))

    @staticmethod
    def resolve_created_at(obj: ChatRecordExportTask) -> Any:
        return SchemaMixin._resolve_datetime_iso(getattr(obj, "created_at", None))

    @staticmethod
    def resolve_updated_at(obj: ChatRecordExportTask) -> Any:
        return SchemaMixin._resolve_datetime_iso(getattr(obj, "updated_at", None))

    @staticmethod
    def resolve_download_url(obj: ChatRecordExportTask) -> Any:
        if not getattr(obj, "output_file", None):
            return None
        return f"/api/v1/chat-records/exports/{obj.id}/download"


class ExportTypeItem(Schema):
    value: str
    label: str


class ExportStatusItem(Schema):
    value: str
    label: str


def list_export_types() -> list[ExportTypeItem]:
    return [ExportTypeItem(value=value, label=str(label)) for value, label in ExportType.choices]


def list_export_statuses() -> list[ExportStatusItem]:
    return [ExportStatusItem(value=value, label=str(label)) for value, label in ExportStatus.choices]
