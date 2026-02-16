"""Business logic services."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, cast

from django.db import transaction
from django.utils import timezone

from apps.chat_records.models import ChatRecordRecording, ExtractStatus
from apps.core.exceptions import NotFoundError, ValidationException
from apps.core.tasking import TaskContext

from .access_policy import ensure_can_access_project
from .wiring import get_task_submission_service


@dataclass(frozen=True)
class RecordingExtractParams:
    interval_seconds: float = 1.0
    strategy: str = "interval"
    dedup_threshold: int | None = None
    ocr_similarity_threshold: float | None = None
    ocr_min_new_chars: int | None = None


class RecordingExtractFacade:
    @transaction.atomic
    def submit(self, *, user: Any, recording_id: str, params: RecordingExtractParams) -> ChatRecordRecording:
        from apps.chat_records.services.video_frame_extract_service import VideoFrameExtractService

        try:
            recording = cast(
                ChatRecordRecording,
                ChatRecordRecording.objects.select_for_update().get(id=recording_id),
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
            extract_message="抽帧任务已提交",
            extract_error="",
            updated_at=timezone.now(),
        )

        task_timeout = 1800 if str(params.strategy or "").strip().lower() == "ocr" else None
        task_name = f"chat_records_extract_{recording.id}"
        get_task_submission_service().submit(
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
            recording = cast(
                ChatRecordRecording,
                ChatRecordRecording.objects.select_for_update().get(id=recording_id),
            )
        except ChatRecordRecording.DoesNotExist:
            raise NotFoundError(f"录屏 {recording_id} 不存在") from None
        ensure_can_access_project(user=user, project=recording.project)
        if recording.extract_status not in (ExtractStatus.PENDING, ExtractStatus.RUNNING):
            raise ValidationException("当前没有进行中的抽帧任务")

        ChatRecordRecording.objects.filter(id=recording.id).update(
            extract_cancel_requested=True,
            extract_message="已请求取消",
            updated_at=timezone.now(),
        )
        recording.refresh_from_db()
        return recording

    @transaction.atomic
    def reset(self, *, user: Any, recording_id: str) -> ChatRecordRecording:
        try:
            recording = cast(
                ChatRecordRecording,
                ChatRecordRecording.objects.select_for_update().get(id=recording_id),
            )
        except ChatRecordRecording.DoesNotExist:
            raise NotFoundError(f"录屏 {recording_id} 不存在") from None
        ensure_can_access_project(user=user, project=recording.project)
        ChatRecordRecording.objects.filter(id=recording.id).update(
            extract_status=ExtractStatus.FAILED,
            extract_cancel_requested=False,
            extract_error="已重置抽帧状态",
            extract_message="已重置",
            extract_finished_at=timezone.now(),
            updated_at=timezone.now(),
        )
        recording.refresh_from_db()
        return recording
