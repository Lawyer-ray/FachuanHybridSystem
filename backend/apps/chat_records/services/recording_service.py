"""Business logic services."""

from __future__ import annotations

import contextlib
import logging
import mimetypes
from typing import Any, cast

from django.conf import settings
from django.db import transaction
from django.db.models import QuerySet

from apps.chat_records.models import ChatRecordProject, ChatRecordRecording, ChatRecordScreenshot, ExtractStatus
from apps.core.exceptions import NotFoundError, ValidationException

from .access_policy import ensure_can_access_project

logger = logging.getLogger(__name__)


class RecordingService:
    DEFAULT_MAX_VIDEO_SIZE_BYTES = 2 * 1024 * 1024 * 1024

    def list_recordings(self, *, user: Any, project_id: int) -> QuerySet[ChatRecordRecording, ChatRecordRecording]:
        self._get_project(user=user, project_id=project_id)
        return ChatRecordRecording.objects.filter(project_id=project_id).order_by("-created_at")

    def get_recording(self, *, user: Any, recording_id: str) -> ChatRecordRecording:
        try:
            recording = cast(
                ChatRecordRecording,
                ChatRecordRecording.objects.select_related("project").get(id=recording_id),
            )
        except ChatRecordRecording.DoesNotExist:
            raise NotFoundError(f"录屏 {recording_id} 不存在") from None
        ensure_can_access_project(user=user, project=recording.project)
        return recording

    @transaction.atomic
    def upload_recording(self, *, user: Any, project_id: int, file: Any) -> ChatRecordRecording:
        project = self._get_project(user=user, project_id=project_id)
        if not file:
            raise ValidationException("请上传录屏文件")

        if ChatRecordRecording.objects.filter(project_id=project_id).exists():
            raise ValidationException("一个项目仅支持 1 个录屏,请先删除旧录屏后再上传")
        if ChatRecordScreenshot.objects.filter(project_id=project_id).exists():
            raise ValidationException("该项目已上传图片,不能再上传录屏")

        content_type = (getattr(file, "content_type", "") or "").lower()
        original_name = str(getattr(file, "name", "") or "")
        if not content_type and original_name:
            guessed, _ = mimetypes.guess_type(original_name)
            content_type = (guessed or "").lower()
        if not content_type.startswith("video/"):
            raise ValidationException("仅支持上传视频文件")

        size = int(getattr(file, "size", 0) or 0)
        max_size = self._get_max_video_size_bytes()
        if size > max_size:
            raise ValidationException(f"视频过大(最大 {max_size // (1024 * 1024)}MB)")

        recording = ChatRecordRecording.objects.create(
            project=project,
            video=file,
            original_name=original_name,
            size_bytes=size,
            extract_status=ExtractStatus.PENDING,
            extract_progress=0,
            extract_current=0,
            extract_total=0,
            extract_message="等待抽帧",
            extract_error="",
        )
        return recording

    @transaction.atomic
    def delete_recording(self, *, user: Any, recording_id: str) -> dict[str, bool]:
        recording = self.get_recording(user=user, recording_id=recording_id)
        if recording.extract_status == ExtractStatus.RUNNING:
            raise ValidationException("抽帧处理中,无法删除")
        if recording.video:
            with contextlib.suppress(Exception):
                recording.video.delete(save=False)
        recording.delete()
        return {"success": True}

    @transaction.atomic
    def update_duration(self, *, user: Any, recording_id: str, duration_seconds: float | None) -> ChatRecordRecording:
        recording = self.get_recording(user=user, recording_id=recording_id)
        recording.duration_seconds = duration_seconds
        recording.save(update_fields=["duration_seconds"])
        return recording

    def _get_project(self, *, user: Any, project_id: int) -> ChatRecordProject:
        try:
            project = ChatRecordProject.objects.get(id=project_id)
        except ChatRecordProject.DoesNotExist:
            raise NotFoundError(f"项目 {project_id} 不存在") from None
        ensure_can_access_project(user=user, project=project)
        return project

    def _get_max_video_size_bytes(self) -> int:
        v = getattr(settings, "CHAT_RECORDS_MAX_VIDEO_SIZE_BYTES", None)
        if v is None:
            return self.DEFAULT_MAX_VIDEO_SIZE_BYTES
        try:
            return int(v)
        except Exception:
            logger.exception("操作失败")
            return self.DEFAULT_MAX_VIDEO_SIZE_BYTES
