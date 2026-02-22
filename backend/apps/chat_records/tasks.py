"""Celery / Django-Q 任务入口。"""

from __future__ import annotations

import logging
from typing import Any

from django.utils import timezone

from apps.core.exceptions import ValidationException

logger = logging.getLogger("apps.chat_records")


def export_chat_record_task(task_id: str) -> Any:
    from apps.chat_records.models import ChatRecordExportTask, ExportStatus, ExportType
    from apps.chat_records.services.export_service import ExportService
    from apps.chat_records.services.export_task_service import ExportTaskService
    from apps.chat_records.services.export_types import ExportLayout

    try:
        task = ChatRecordExportTask.objects.select_related("project").get(id=task_id)
    except ChatRecordExportTask.DoesNotExist:
        logger.error("导出任务不存在", extra={"task_id": task_id})
        return {"task_id": task_id, "status": "failed", "error": "导出任务不存在"}

    export_task_svc = ExportTaskService.__new__(ExportTaskService)

    try:
        screenshots = list(task.project.screenshots.all().order_by("ordering", "created_at"))
        if not screenshots:
            raise ValidationException("没有截图,无法导出")

        layout = ExportLayout.from_payload(
            task.export_type,
            task.layout or {},
            default_header_text=task.project.name,
        )

        export_task_svc.update_export_progress(
            task_id=task_id,
            status=ExportStatus.RUNNING,
            progress=0,
            current=0,
            total=len(screenshots),
            message="开始生成文件",
        )

        def on_progress(current: int, total: int, message: str) -> Any:
            progress = int(current * 100 / total) if total else 0
            export_task_svc.update_export_progress(
                task_id=task_id,
                progress=progress,
                current=current,
                total=total,
                message=message,
            )

        export_service = ExportService()

        if task.export_type == ExportType.PDF:
            filename = f"梳理聊天记录_{task.project.id}.pdf"
            file_obj = export_service.export_pdf(
                project=task.project,
                screenshots=screenshots,
                layout=layout,
                filename=filename,
                progress_callback=on_progress,
            )
        else:
            filename = f"梳理聊天记录_{task.project.id}.docx"
            file_obj = export_service.export_docx(
                project=task.project,
                screenshots=screenshots,
                layout=layout,
                filename=filename,
                progress_callback=on_progress,
            )

        task.refresh_from_db()
        task.output_file.save(filename, file_obj, save=False)
        task.status = ExportStatus.SUCCESS
        task.progress = 100
        task.current = task.total
        task.message = "生成完成"
        task.finished_at = timezone.now()
        task.save(
            update_fields=[
                "output_file",
                "status",
                "progress",
                "current",
                "message",
                "finished_at",
                "updated_at",
            ]
        )

        return {"task_id": task_id, "status": "success", "export_type": task.export_type}
    except Exception as e:
        logger.error("导出失败", extra={"task_id": task_id, "error": str(e)}, exc_info=True)
        export_task_svc.update_export_progress(
            task_id=task_id,
            status=ExportStatus.FAILED,
            error=str(e),
            message="生成失败",
            finished_at=timezone.now(),
        )
        return {"task_id": task_id, "status": "failed", "error": str(e)}


def extract_recording_frames_task(
    recording_id: str,
    interval_seconds: float = 1.0,
) -> dict[str, Any]:
    import tempfile

    from django.db.models import Max

    from apps.chat_records.models import (
        ChatRecordRecording,
        ChatRecordScreenshot,
        ExtractStatus,
        ScreenshotSource,
    )
    from apps.chat_records.services.extract_helpers import DedupState, ExtractParams
    from apps.chat_records.services.frame_processing_service import FrameProcessingService
    from apps.chat_records.services.frame_selection_service import FrameSelectionService
    from apps.chat_records.services.video_frame_extract_service import VideoFrameExtractService
    from apps.core.interfaces import ServiceLocator
    from apps.core.tasking.runtime import CancellationToken, ProgressReporter, TaskRunContext

    fps = FrameProcessingService()

    try:
        recording = ChatRecordRecording.objects.select_related("project").get(id=recording_id)
    except ChatRecordRecording.DoesNotExist:
        logger.error("录屏不存在", extra={"recording_id": recording_id})
        return {"recording_id": recording_id, "status": "failed", "error": "录屏不存在"}

    params = ExtractParams.from_recording(recording, interval_seconds)
    run_ctx = TaskRunContext.from_django_q()
    soft_deadline = float(run_ctx.soft_deadline_monotonic)

    ChatRecordRecording.objects.filter(id=recording.id).update(
        extract_status=ExtractStatus.RUNNING,
        extract_started_at=timezone.now(),
        extract_finished_at=None,
        extract_error="",
        extract_progress=0,
        extract_current=0,
        extract_total=0,
        extract_message="准备抽帧",
        updated_at=timezone.now(),
    )

    service = VideoFrameExtractService()
    selection_service = FrameSelectionService()
    ocr_service = ServiceLocator.get_ocr_service() if params.strategy == "ocr" else None

    try:
        info = service.probe(recording.video.path)

        cancel_token = CancellationToken(
            lambda: bool(
                ChatRecordRecording.objects.filter(id=recording.id)
                .values_list("extract_cancel_requested", flat=True)
                .first()
            )
        )

        def _update_progress(progress: int, current: int, total: int, message: str) -> Any:
            ChatRecordRecording.objects.filter(id=recording.id).update(
                extract_progress=min(int(progress), 99),
                extract_current=int(current),
                extract_total=int(total),
                extract_message=message,
                updated_at=timezone.now(),
            )

        ffmpeg_reporter = ProgressReporter(update_fn=_update_progress, min_interval_seconds=0.5)
        write_reporter = ProgressReporter(update_fn=_update_progress, min_interval_seconds=0.5)

        with tempfile.TemporaryDirectory(prefix="chat_records_frames_") as tmpdir:
            total_estimate, should_cancel = fps.run_ffmpeg_phase(
                service, recording, info, params, cancel_token, ffmpeg_reporter, soft_deadline, tmpdir
            )

            frame_files = fps.collect_frame_files(tmpdir)
            total_files = len(frame_files)
            if total_files:
                ChatRecordRecording.objects.filter(id=recording.id).update(
                    extract_total=total_files, updated_at=timezone.now()
                )

            ChatRecordScreenshot.objects.filter(
                project_id=recording.project_id, source=ScreenshotSource.EXTRACT
            ).delete()

            base_ordering = (
                ChatRecordScreenshot.objects.filter(project_id=recording.project_id)
                .aggregate(v=Max("ordering"))
                .get("v")
                or 0
            )

            state = DedupState(
                existing_sha256=set(
                    ChatRecordScreenshot.objects.filter(project_id=recording.project_id)
                    .exclude(sha256="")
                    .values_list("sha256", flat=True)
                ),
            )
            window = 12 if params.dedup_threshold >= 20 else 6
            pixel_diff_threshold = 2.8 if params.dedup_threshold >= 20 else 0.0

            for index, path in enumerate(frame_files, start=1):
                if should_cancel():
                    raise ValidationException("抽帧已取消")
                state.processed_count += 1

                fps.process_single_frame(
                    path,
                    index,
                    recording,
                    info,
                    params,
                    state,
                    selection_service,
                    ocr_service,
                    soft_deadline,
                    base_ordering,
                    window,
                    pixel_diff_threshold,
                )

                progress = int(state.processed_count * 100 / total_files) if total_files else 100
                write_reporter.report_extra(
                    progress=min(progress, 99),
                    current=state.created_count,
                    total=total_files,
                    message="写入截图",
                    force=(state.processed_count == total_files),
                )

            fps.reorder_screenshots(recording.project_id)

        if params.strategy == "ocr":
            logger.info(
                "录屏抽帧 OCR 统计",
                extra={
                    "recording_id": recording_id,
                    "ocr_calls": int(state.ocr_calls),
                    "ocr_skipped": int(state.ocr_skipped),
                    "ocr_disabled": bool(state.ocr_disabled),
                },
            )
        ChatRecordRecording.objects.filter(id=recording.id).update(
            extract_status=ExtractStatus.SUCCESS,
            extract_progress=100,
            extract_current=state.created_count,
            extract_total=state.created_count,
            extract_message="抽帧完成",
            extract_finished_at=timezone.now(),
            updated_at=timezone.now(),
        )
        return {"recording_id": recording_id, "status": "success"}
    except Exception as e:
        logger.error("录屏抽帧失败", extra={"recording_id": recording_id, "error": str(e)}, exc_info=True)
        ChatRecordRecording.objects.filter(id=recording.id).update(
            extract_status=ExtractStatus.FAILED,
            extract_error=str(e),
            extract_message="抽帧失败",
            extract_finished_at=timezone.now(),
            updated_at=timezone.now(),
        )
        return {"recording_id": recording_id, "status": "failed", "error": str(e)}
