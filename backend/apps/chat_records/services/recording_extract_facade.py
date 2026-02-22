"""Business logic services."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime
from typing import Any

from django.db import transaction
from django.utils import timezone
from django.utils.translation import gettext_lazy as _

from apps.chat_records.models import ChatRecordRecording, ExtractStatus
from apps.core.exceptions import NotFoundError, ValidationException
from apps.core.tasking import TaskContext, TaskSubmissionService

from .access_policy import ensure_can_access_project

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class RecordingExtractParams:
    interval_seconds: float = 1.0
    strategy: str = "interval"
    dedup_threshold: int | None = None
    ocr_similarity_threshold: float | None = None
    ocr_min_new_chars: int | None = None


class RecordingExtractFacade:
    def __init__(self, *, task_submission_service: TaskSubmissionService) -> None:
        self._task_submission_service = task_submission_service

    @transaction.atomic
    def submit(self, *, user: Any, recording_id: str, params: RecordingExtractParams) -> ChatRecordRecording:
        from apps.chat_records.services.video_frame_extract_service import VideoFrameExtractService

        try:
            recording: ChatRecordRecording = (
                ChatRecordRecording.objects.select_for_update().get(id=recording_id)
            )
        except ChatRecordRecording.DoesNotExist:
            raise NotFoundError(f"录屏 {recording_id} 不存在") from None
        ensure_can_access_project(user=user, project=recording.project)
        if recording.extract_status in (ExtractStatus.PENDING, ExtractStatus.RUNNING):
            raise ValidationException("抽帧任务正在运行或排队中")

        VideoFrameExtractService().ensure_ffmpeg()

        ChatRecordRecording.objects.filter(id=recording.id).update(
            extract_status=ExtractStatus.PENDING,
            extract_progress=0,
            extract_current=0,
            extract_strategy=str(params.strategy or "interval"),
            extract_dedup_threshold=params.dedup_threshold,
            extract_ocr_similarity_threshold=params.ocr_similarity_threshold,
            extract_ocr_min_new_chars=params.ocr_min_new_chars,
            extract_cancel_requested=False,
            extract_message=_("抽帧任务已提交"),
            extract_error="",
            updated_at=timezone.now(),
        )

        task_timeout = 1800 if str(params.strategy or "").strip().lower() == "ocr" else None
        task_name = f"chat_records_extract_{recording.id}"
        self._task_submission_service.submit(
            "apps.chat_records.tasks.extract_recording_frames_task",
            args=(str(recording.id), float(params.interval_seconds or 1.0)),
            task_name=task_name,
            timeout=task_timeout,
            context=TaskContext(task_name=task_name, entity_id=str(recording.id)),
        )

        recording.refresh_from_db()
        return recording

    @transaction.atomic
    def request_cancel(self, *, user: Any, recording_id: str) -> ChatRecordRecording:
        try:
            recording: ChatRecordRecording = (
                ChatRecordRecording.objects.select_for_update().get(id=recording_id)
            )
        except ChatRecordRecording.DoesNotExist:
            raise NotFoundError(f"录屏 {recording_id} 不存在") from None
        ensure_can_access_project(user=user, project=recording.project)
        if recording.extract_status not in (ExtractStatus.PENDING, ExtractStatus.RUNNING):
            raise ValidationException("当前没有进行中的抽帧任务")

        ChatRecordRecording.objects.filter(id=recording.id).update(
            extract_cancel_requested=True,
            extract_message=_("已请求取消"),
            updated_at=timezone.now(),
        )
        recording.refresh_from_db()
        return recording

    @transaction.atomic
    def reset(self, *, user: Any, recording_id: str) -> ChatRecordRecording:
        try:
            recording: ChatRecordRecording = (
                ChatRecordRecording.objects.select_for_update().get(id=recording_id)
            )
        except ChatRecordRecording.DoesNotExist:
            raise NotFoundError(f"录屏 {recording_id} 不存在") from None
        ensure_can_access_project(user=user, project=recording.project)
        ChatRecordRecording.objects.filter(id=recording.id).update(
            extract_status=ExtractStatus.FAILED,
            extract_cancel_requested=False,
            extract_error="已重置抽帧状态",
            extract_message=_("已重置"),
            extract_finished_at=timezone.now(),
            updated_at=timezone.now(),
        )
        recording.refresh_from_db()
        return recording

    def update_extract_progress(
        self,
        *,
        recording_id: str,
        status: str | None = None,
        progress: int | None = None,
        current: int | None = None,
        total: int | None = None,
        message: str = "",
        error: str = "",
        started_at: datetime | None = None,
        finished_at: datetime | None = None,
        duration_seconds: float | None = None,
    ) -> None:
        """单次数据库操作更新抽帧任务的状态和进度。"""
        fields: dict[str, Any] = {"updated_at": timezone.now()}

        if status is not None:
            fields["extract_status"] = status
        if progress is not None:
            fields["extract_progress"] = progress
        if current is not None:
            fields["extract_current"] = current
        if total is not None:
            fields["extract_total"] = total
        if message:
            fields["extract_message"] = message
        if error:
            fields["extract_error"] = error
        if started_at is not None:
            fields["extract_started_at"] = started_at
        if finished_at is not None:
            fields["extract_finished_at"] = finished_at
        if duration_seconds is not None:
            fields["duration_seconds"] = duration_seconds

        rows: int = ChatRecordRecording.objects.filter(id=recording_id).update(**fields)
        if rows == 0:
            logger.warning("录屏 %s 不存在，跳过进度更新", recording_id)

