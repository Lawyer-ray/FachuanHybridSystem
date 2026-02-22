"""Business logic services."""

from __future__ import annotations

import contextlib
import logging
import mimetypes
from typing import TYPE_CHECKING

from django.db import transaction
from django.db.models import QuerySet
from django.utils.translation import gettext_lazy as _

from apps.chat_records.models import ChatRecordRecording, ChatRecordScreenshot, ExtractStatus
from apps.core.exceptions import NotFoundError, ValidationException

from .access_policy import ensure_can_access_project
from .project_service import ProjectService

if TYPE_CHECKING:
    from django.contrib.auth.models import AbstractBaseUser as User
    from django.core.files.uploadedfile import UploadedFile

logger = logging.getLogger(__name__)


class RecordingService:
    DEFAULT_MAX_VIDEO_SIZE_BYTES = 2 * 1024 * 1024 * 1024

    def __init__(self, *, project_service: ProjectService) -> None:
        self._project_service = project_service

    def list_recordings(self, *, user: User, project_id: int) -> QuerySet[ChatRecordRecording, ChatRecordRecording]:
        self._project_service.get_project(user=user, project_id=project_id)
        return ChatRecordRecording.objects.filter(project_id=project_id).order_by("-created_at")

    def get_recording(self, *, user: User, recording_id: str) -> ChatRecordRecording:
        try:
            recording: ChatRecordRecording = (
                ChatRecordRecording.objects.select_related("project").get(id=recording_id)
            )
        except ChatRecordRecording.DoesNotExist:
            raise NotFoundError(f"录屏 {recording_id} 不存在") from None
        ensure_can_access_project(user=user, project=recording.project)
        return recording

    @transaction.atomic
    def upload_recording(self, *, user: User, project_id: int, file: UploadedFile) -> ChatRecordRecording:
        project = self._project_service.get_project(user=user, project_id=project_id)
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
            extract_message=_("等待抽帧"),
            extract_error="",
        )
        return recording

    @transaction.atomic
    def delete_recording(self, *, user: User, recording_id: str) -> dict[str, bool]:
        recording = self.get_recording(user=user, recording_id=recording_id)
        if recording.extract_status == ExtractStatus.RUNNING:
            raise ValidationException("抽帧处理中,无法删除")
        if recording.video:
            with contextlib.suppress(Exception):
                recording.video.delete(save=False)
        recording.delete()
        return {"success": True}

    @transaction.atomic
    def update_duration(self, *, user: User, recording_id: str, duration_seconds: float | None) -> ChatRecordRecording:
        recording = self.get_recording(user=user, recording_id=recording_id)
        recording.duration_seconds = duration_seconds
        recording.save(update_fields=["duration_seconds"])
        return recording

    def _get_max_video_size_bytes(self) -> int:
        from apps.core.services.system_config_service import SystemConfigService

        svc = SystemConfigService()
        raw = svc.get_value("CHAT_RECORDS_MAX_VIDEO_SIZE_BYTES", "")
        if not raw:
            return self.DEFAULT_MAX_VIDEO_SIZE_BYTES
        try:
            return int(raw)
        except (ValueError, TypeError):
            logger.warning(
                "CHAT_RECORDS_MAX_VIDEO_SIZE_BYTES 配置值无效: %s，使用默认值",
                repr(raw),
            )
            return self.DEFAULT_MAX_VIDEO_SIZE_BYTES
